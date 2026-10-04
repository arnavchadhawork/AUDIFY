import asyncio
import base64
import functools
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, List, Dict, Any, Deque, Tuple
from collections import deque

import discord
import yt_dlp

from config import (
    COMMAND_PREFIX,
    FFMPEG_PATH,
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_MARKET,
)

logger = logging.getLogger(__name__)

# yt-dlp configuration for audio streaming
YTDL_BASE_OPTS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "opus",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "no_color": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",  # bind to ipv4 since ipv6 can cause issues
}

# FFmpeg streaming options
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def normalize_query(query: str) -> str:
    """Accept plain URLs and URLs copied from Markdown-formatted chat logs."""
    query = query.strip()
    for command in (f"{COMMAND_PREFIX}play ", "/play "):
        if query.lower().startswith(command.lower()):
            query = query[len(command):].strip()
            break
    markdown_url = re.fullmatch(r"\[([^\]]+)\]\((https?://[^)]+)\)", query)
    if markdown_url:
        return markdown_url.group(2)
    if query.startswith("<") and query.endswith(">"):
        return query[1:-1].strip()
    return query


def _friendly_source_error(error: Exception) -> str:
    message = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    if "sign in to confirm" in message.lower() or "not a bot" in message.lower():
        return "YouTube is blocking requests from this server. Try again later; FFmpeg settings will not fix this."
    return message


def _first_entry(info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not info:
        return None
    if "entries" not in info:
        return info
    return next((entry for entry in info["entries"] if entry), None)


def _spotify_url_parts(query: str) -> Optional[Tuple[str, str]]:
    parsed = urllib.parse.urlsplit(query)
    if parsed.hostname not in ("open.spotify.com", "www.open.spotify.com"):
        return None

    parts = [part for part in parsed.path.split("/") if part]
    while parts and (parts[0] == "embed" or parts[0].startswith("intl-")):
        parts.pop(0)
    if (
        len(parts) < 2
        or parts[0] not in ("track", "album", "playlist")
        or not re.fullmatch(r"[A-Za-z0-9]+", parts[1])
    ):
        raise ValueError("Use a Spotify track, album, or playlist link.")
    return parts[0], parts[1]


def _spotify_api_json(url: str, headers: Dict[str, str], data: Optional[bytes] = None) -> Dict[str, Any]:
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(response_body).get("error", {}).get("message")
        except (json.JSONDecodeError, AttributeError):
            message = None
        detail = f": {message}" if message else ""
        raise RuntimeError(f"Spotify API request failed (HTTP {error.code}){detail}") from error


def _spotify_access_token() -> str:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError(
            "Spotify links need SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in the .env file."
        )

    credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode("utf-8")
    authorization = base64.b64encode(credentials).decode("ascii")
    token_data = _spotify_api_json(
        "https://accounts.spotify.com/api/token",
        {
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("ascii"),
    )
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("Spotify did not return an access token.")
    return access_token


def _spotify_track_query(track: Dict[str, Any]) -> Optional[Tuple[str, str, int, str]]:
    if not track or track.get("is_local") or not track.get("name"):
        return None
    artists = [
        artist.get("name", "")
        for artist in (track.get("artists") or [])
        if artist and artist.get("name")
    ]
    title = track["name"]
    search = f"{title} {' '.join(artists)}".strip()
    spotify_url = (track.get("external_urls") or {}).get("spotify", "")
    duration = int(track.get("duration_ms") or 0) // 1000
    return title, search, duration, spotify_url


def _load_spotify_metadata(kind: str, spotify_id: str) -> Tuple[str, List[Tuple[str, str, int, str]]]:
    access_token = _spotify_access_token()
    path = f"https://api.spotify.com/v1/{kind}s/{spotify_id}"
    query_params = {"market": SPOTIFY_MARKET} if SPOTIFY_MARKET else {}
    if query_params:
        path = f"{path}?{urllib.parse.urlencode(query_params)}"

    headers = {"Authorization": f"Bearer {access_token}"}
    metadata = _spotify_api_json(path, headers)
    if kind == "track":
        track = _spotify_track_query(metadata)
        return metadata.get("name", "Spotify track"), [track] if track else []

    collection = metadata.get("tracks", {})
    playlist_name = metadata.get("name") or f"Spotify {kind}"
    tracks: List[Tuple[str, str, int, str]] = []
    while collection:
        for item in collection.get("items", []):
            track_data = item.get("track") if kind == "playlist" else item
            track = _spotify_track_query(track_data)
            if track:
                tracks.append(track)

        next_url = collection.get("next")
        if not next_url:
            break
        next_parts = urllib.parse.urlsplit(next_url)
        if next_parts.scheme != "https" or next_parts.hostname != "api.spotify.com":
            raise RuntimeError("Spotify returned an unexpected pagination URL.")
        collection = _spotify_api_json(next_url, headers)

    return playlist_name, tracks


async def _extract_youtube(query: str) -> Optional[Dict[str, Any]]:
    """Extract one YouTube result or URL using yt-dlp."""
    loop = asyncio.get_running_loop()

    def extract(search_query: str) -> Optional[Dict[str, Any]]:
        ydl = yt_dlp.YoutubeDL(dict(YTDL_BASE_OPTS))
        return _first_entry(ydl.extract_info(search_query, download=False))

    return await loop.run_in_executor(None, functools.partial(extract, query))


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "Live / Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class Song:
    """Represents a song queued or playing."""
    def __init__(
        self,
        title: str,
        query: str,
        webpage_url: str = "",
        stream_url: str = "",
        duration: int = 0,
        thumbnail: str = "",
        requester: str = "Unknown",
        source: str = "YouTube",
    ):
        self.title = title
        self.query = query
        self.webpage_url = webpage_url
        self.stream_url = stream_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.source = source
        self.is_resolved = bool(stream_url)

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration)


class GuildPlayer:
    """Manages audio playback, queue, and voice connection for a specific Guild."""

    def __init__(self, bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.abc.Messageable] = None

        self.queue: Deque[Song] = deque()
        self.current: Optional[Song] = None
        self.history: List[Song] = []

        # Playback settings
        self.volume: float = 0.5  # 50% default volume
        self.loop_mode: str = "off"  # "off", "one", "all"

        # Concurrency / synchronization
        self.play_next_song = asyncio.Event()
        self.voice_connected = asyncio.Event()
        self.skip_requested = False
        self.audio_player_task: Optional[asyncio.Task] = None
        self.idle_task: Optional[asyncio.Task] = None

        # Start background loop for this guild
        self.audio_player_task = bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Main loop that continuously pulls songs from the queue and plays them."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.play_next_song.clear()

            # Handle looping
            if self.loop_mode == "one" and self.current:
                # Keep playing the same song
                song_to_play = self.current
            elif self.loop_mode == "all" and self.current and not self.queue:
                # Re-queue history or current song if looping all
                self.queue.append(self.current)
                song_to_play = self.queue.popleft()
            elif self.queue:
                if self.loop_mode == "all" and self.current:
                    self.queue.append(self.current)
                song_to_play = self.queue.popleft()
            else:
                self.current = None
                # Start idle timer to disconnect if inactive for 3 minutes
                self.reset_idle_timer()
                await self.play_next_song.wait()
                continue

            # Cancel idle timer if active
            self.cancel_idle_timer()
            self.current = song_to_play
            self.skip_requested = False

            # Ensure song has a stream URL
            if not song_to_play.is_resolved:
                resolved = await self.resolve_song_audio(song_to_play)
                if self.current is not song_to_play:
                    continue
                if self.skip_requested:
                    self.skip_requested = False
                    self.current = None
                    continue
                if not resolved:
                    self.current = None
                    if self.text_channel:
                        await self.text_channel.send(
                            f"❌ Could not resolve audio for **{song_to_play.title}**. Skipping..."
                        )
                    continue

            # Ensure voice client is connected
            if not self.voice_client or not self.voice_client.is_connected():
                logger.warning("Voice client is disconnected; preserving the track until reconnection.")
                self.queue.appendleft(song_to_play)
                self.current = None
                self.voice_connected.clear()
                while not self.voice_connected.is_set():
                    try:
                        await asyncio.wait_for(self.voice_connected.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        voice_client = self.voice_client
                        if voice_client and voice_client.is_connected():
                            self.voice_connected.set()
                continue

            self.history.append(song_to_play)

            try:
                # Create FFmpeg audio source
                audio_source = discord.FFmpegPCMAudio(
                    song_to_play.stream_url,
                    executable=FFMPEG_PATH,
                    **FFMPEG_OPTIONS,
                )
                transformed_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

                def after_callback(error):
                    if error:
                        logger.error(f"Playback error in guild {self.guild.id}: {error}")
                    self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

                self.voice_client.play(transformed_source, after=after_callback)

                # Send Now Playing embed
                if self.text_channel and self.loop_mode != "one":
                    embed = self.create_now_playing_embed(song_to_play)
                    await self.text_channel.send(embed=embed)

            except Exception as e:
                logger.error(f"Failed to play audio: {e}")
                if self.text_channel:
                    if "ffmpeg was not found" in str(e).lower():
                        error_message = (
                            "❌ FFmpeg is unavailable on this host. Install `imageio-ffmpeg` "
                            "or provide a valid `FFMPEG_PATH`, then redeploy."
                        )
                    else:
                        error_message = f"❌ Error playing **{song_to_play.title}**: {e}"
                    await self.text_channel.send(error_message)
                self.play_next_song.set()

            # Wait until current track finishes playing or is skipped
            await self.play_next_song.wait()

    async def resolve_song_audio(self, song: Song) -> bool:
        """Extracts direct audio stream URL using yt-dlp."""
        query = normalize_query(song.query if song.query else song.title)
        try:
            info = await _extract_youtube(query)

            if not info or "url" not in info:
                return False

            song.stream_url = info["url"]
            song.title = info.get("title", song.title)
            song.webpage_url = info.get("webpage_url", song.webpage_url)
            song.duration = info.get("duration", song.duration)
            song.thumbnail = info.get("thumbnail", song.thumbnail)
            song.source = "YouTube"
            song.is_resolved = True
            return True
        except Exception as e:
            logger.error(f"Failed to resolve audio for {song.title}: {e}")
            return False

    def create_now_playing_embed(self, song: Song) -> discord.Embed:
        """Creates a modern Discord embed for the currently playing song."""
        color = 0xFF0000
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"**[{song.title}]({song.webpage_url if song.webpage_url else 'https://youtube.com'})**",
            color=color,
        )
        embed.add_field(name="⏱️ Duration", value=song.duration_str, inline=True)
        embed.add_field(name="👤 Requested by", value=song.requester, inline=True)
        embed.add_field(name="🔊 Volume", value=f"{int(self.volume * 100)}%", inline=True)

        loop_status = {
            "off": "Disabled",
            "one": "🔂 Current Track",
            "all": "🔁 Entire Queue",
        }.get(self.loop_mode, "Disabled")
        embed.add_field(name="🔄 Loop", value=loop_status, inline=True)
        embed.add_field(name="🌐 Source", value=song.source, inline=True)
        embed.add_field(name="📜 In Queue", value=f"{len(self.queue)} songs", inline=True)

        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        embed.set_footer(text="YouTube audio via yt-dlp")
        return embed

    def skip(self):
        """Skip the current song, including while resolving or paused."""
        if not self.current:
            return False

        if self.voice_client and (
            self.voice_client.is_playing() or self.voice_client.is_paused()
        ):
            self.voice_client.stop()
            return True

        self.skip_requested = True
        return True

    def handle_voice_disconnect(self):
        """Preserve the current track and wait for the next voice connection."""
        self.voice_connected.clear()
        voice_client = self.voice_client
        self.voice_client = None

        if self.current:
            self.current.is_resolved = False
            self.queue.appendleft(self.current)
            self.current = None

        if voice_client and (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            voice_client.stop()

    def pause(self) -> bool:
        """Pauses the current playback."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resumes playback if paused."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    def set_volume(self, volume: float):
        """Sets playback volume between 0.0 and 1.0."""
        self.volume = max(0.0, min(1.0, volume))
        if self.voice_client and self.voice_client.source:
            if hasattr(self.voice_client.source, "volume"):
                self.voice_client.source.volume = self.volume

    def stop(self):
        """Clears queue, stops playback, and prepares for disconnect."""
        self.queue.clear()
        self.loop_mode = "off"
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def reset_idle_timer(self):
        """Starts an inactivity timer to auto-leave if idle for 3 minutes."""
        self.cancel_idle_timer()
        self.idle_task = self.bot.loop.create_task(self._idle_timeout(180))

    def cancel_idle_timer(self):
        """Cancels any running idle timer."""
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()
            self.idle_task = None

    async def _idle_timeout(self, seconds: int):
        try:
            await asyncio.sleep(seconds)
            if self.voice_client and self.voice_client.is_connected() and not self.current:
                if self.text_channel:
                    await self.text_channel.send("👋 Left voice channel due to inactivity.")
                await self.voice_client.disconnect()
        except asyncio.CancelledError:
            pass

    def cleanup(self):
        """Cleans up tasks when leaving guild or destroying player."""
        if self.audio_player_task:
            self.audio_player_task.cancel()
        self.cancel_idle_timer()


class MusicManager:
    """Manages players across all connected Discord guilds."""

    def __init__(self, bot):
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}

    def get_player(self, guild: discord.Guild) -> GuildPlayer:
        """Retrieves or creates a GuildPlayer for the given guild."""
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(self.bot, guild)
        return self.players[guild.id]

    def remove_player(self, guild_id: int):
        """Destroys and removes player for guild."""
        if guild_id in self.players:
            self.players[guild_id].cleanup()
            del self.players[guild_id]


async def process_input_query(query: str, requester: str) -> Tuple[List[Song], str]:
    """
    Accepts Spotify or YouTube URLs, YouTube playlist URLs, or one plain-text search.
    Returns: (list_of_songs, description_message)
    """
    query = normalize_query(query)

    try:
        spotify_parts = _spotify_url_parts(query)
    except ValueError as error:
        return [], str(error)
    if spotify_parts:
        kind, spotify_id = spotify_parts
        loop = asyncio.get_running_loop()
        try:
            playlist_name, spotify_tracks = await loop.run_in_executor(
                None,
                functools.partial(_load_spotify_metadata, kind, spotify_id),
            )
            songs = [
                Song(
                    title=title,
                    query=search_query,
                    webpage_url=spotify_url,
                    duration=duration,
                    requester=requester,
                    source="Spotify",
                )
                for title, search_query, duration, spotify_url in spotify_tracks
            ]
            if not songs:
                return [], f"No playable tracks were found in Spotify {kind}: **{playlist_name}**."
            if kind == "track":
                return songs, f"Spotify track **{playlist_name}**"
            return songs, f"Spotify {kind} **{playlist_name}** ({len(songs)} tracks)"
        except Exception as error:
            error_message = _friendly_source_error(error)
            logger.error("Error loading Spotify %s: %s", kind, error_message)
            return [], f"Could not load Spotify {kind}: {error_message}"

    # Playlists are accepted only as YouTube URLs; text searches add one song.
    query_lower = query.lower()
    is_youtube_playlist = (
        query.startswith(("http://", "https://"))
        and ("youtube.com/playlist" in query_lower or "list=" in query_lower)
    )
    if is_youtube_playlist:
        loop = asyncio.get_running_loop()
        playlist_source = "YouTube"
        ydl = yt_dlp.YoutubeDL(
            {"extract_flat": True, "quiet": True, "ignoreerrors": False, "no_color": True}
        )
        try:
            info = await loop.run_in_executor(
                None,
                functools.partial(ydl.extract_info, query, download=False)
            )
            entries = info.get("entries", []) if info else []
            playlist_title = info.get("title", f"{playlist_source} Playlist")
            songs = []
            for entry in entries:
                if not entry:
                    continue
                e_title = entry.get("title") or f"{playlist_source} Track"
                e_url = entry.get("url") or entry.get("webpage_url")
                if (
                    playlist_source == "YouTube"
                    and e_url
                    and not e_url.startswith("http")
                    and entry.get("id")
                ):
                    e_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                songs.append(
                    Song(
                        title=e_title,
                        query=e_url if e_url and e_url.startswith("http") else e_title,
                        webpage_url=e_url if e_url else "",
                        duration=int(entry.get("duration") or 0),
                        thumbnail=entry.get("thumbnail") or "",
                        requester=requester,
                        source=playlist_source,
                    )
                )
            if songs:
                return songs, f"{playlist_source} Playlist **{playlist_title}** ({len(songs)} tracks)"
        except Exception as e:
            error_message = _friendly_source_error(e)
            logger.error("Error extracting %s playlist: %s", playlist_source, error_message)
            return [], f"Could not load the {playlist_source} playlist: {error_message}"
        return [], f"Could not load the {playlist_source} playlist. Check that its link is public and playable."

    # Direct YouTube URL or YouTube search
    is_direct_url = query.startswith(("http://", "https://"))
    search_query = query if is_direct_url else f"ytsearch1:{query}"
    try:
        info = await _extract_youtube(search_query)

        if not info:
            return [], "No YouTube results found."

        song = Song(
            title=info.get("title", query),
            query=info.get("webpage_url", query),
            webpage_url=info.get("webpage_url", query),
            duration=int(info.get("duration") or 0),
            thumbnail=info.get("thumbnail") or "",
            requester=requester,
            source="YouTube",
        )
        return [song], f"**{song.title}**"

    except Exception as e:
        error_text = _friendly_source_error(e)
        logger.error("Error searching YouTube: %s", error_text)
        return [], f"YouTube could not provide playable audio: {error_text}"
