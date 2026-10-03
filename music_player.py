import asyncio
import functools
import logging
from typing import Optional, List, Dict, Any, Deque, Tuple
from collections import deque

import discord
import yt_dlp

from config import FFMPEG_PATH
import spotify_helper

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
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",  # bind to ipv4 since ipv6 can cause issues
}

# FFmpeg streaming options
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


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

            # Ensure song has a stream URL
            if not song_to_play.is_resolved:
                resolved = await self.resolve_song_audio(song_to_play)
                if not resolved:
                    if self.text_channel:
                        await self.text_channel.send(
                            f"❌ Could not resolve audio for **{song_to_play.title}**. Skipping..."
                        )
                    continue

            self.current = song_to_play
            self.history.append(song_to_play)

            # Ensure voice client is connected
            if not self.voice_client or not self.voice_client.is_connected():
                logger.warning("Voice client is not connected. Halting playback.")
                break

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
                    await self.text_channel.send(f"❌ Error playing **{song_to_play.title}**: {e}")
                self.play_next_song.set()

            # Wait until current track finishes playing or is skipped
            await self.play_next_song.wait()

    async def resolve_song_audio(self, song: Song) -> bool:
        """Extracts direct audio stream URL using yt-dlp."""
        query = song.query if song.query else song.title
        try:
            loop = asyncio.get_event_loop()
            ydl_opts = dict(YTDL_BASE_OPTS)
            ydl = yt_dlp.YoutubeDL(ydl_opts)

            # Extract info in separate executor thread so it doesn't freeze the bot
            info = await loop.run_in_executor(
                None,
                functools.partial(ydl.extract_info, query, download=False)
            )

            if "entries" in info and info["entries"]:
                info = info["entries"][0]

            if not info or "url" not in info:
                return False

            song.stream_url = info["url"]
            song.title = info.get("title", song.title)
            song.webpage_url = info.get("webpage_url", song.webpage_url)
            song.duration = info.get("duration", song.duration)
            song.thumbnail = info.get("thumbnail", song.thumbnail)
            song.is_resolved = True
            return True
        except Exception as e:
            logger.error(f"Failed to resolve audio for {song.title}: {e}")
            return False

    def create_now_playing_embed(self, song: Song) -> discord.Embed:
        """Creates a modern Discord embed for the currently playing song."""
        color = 0x1DB954 if song.source == "Spotify" else 0xFF0000
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
        embed.set_footer(text="Ad-Free Music Player • 100% Free Forever")
        return embed

    def skip(self):
        """Skips the currently playing song."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            return True
        return False

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
    Parses user input query.
    Detects Spotify (tracks, playlists, albums), YouTube playlists, or standard search.
    Returns: (list_of_songs, description_message)
    """
    query = query.strip()

    # 1. Spotify Detection
    if spotify_helper.is_spotify_url(query):
        sp_type, data = spotify_helper.extract_spotify_info(query)
        if sp_type == "track":
            song = Song(
                title=data,
                query=f"ytsearch:{data}",
                requester=requester,
                source="Spotify",
            )
            return [song], f"Spotify Track: **{data}**"

        elif sp_type in ("playlist", "album"):
            if not data or not data.get("tracks"):
                return [], f"Failed to extract tracks from Spotify {sp_type}."

            title = data.get("title", f"Spotify {sp_type.capitalize()}")
            songs = [
                Song(
                    title=track_query,
                    query=f"ytsearch:{track_query}",
                    requester=requester,
                    source="Spotify",
                )
                for track_query in data["tracks"]
            ]
            return songs, f"Spotify {sp_type.capitalize()} **{title}** ({len(songs)} tracks)"

    # 2. YouTube Playlist Detection
    if ("youtube.com/playlist" in query or "list=" in query) and "watch?v=" not in query:
        loop = asyncio.get_event_loop()
        ydl = yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True})
        try:
            info = await loop.run_in_executor(
                None,
                functools.partial(ydl.extract_info, query, download=False)
            )
            entries = info.get("entries", [])
            playlist_title = info.get("title", "YouTube Playlist")
            songs = []
            for entry in entries:
                if not entry:
                    continue
                e_title = entry.get("title") or "YouTube Song"
                e_url = entry.get("url") or entry.get("webpage_url")
                if e_url and not e_url.startswith("http"):
                    e_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                songs.append(
                    Song(
                        title=e_title,
                        query=e_url if e_url else e_title,
                        webpage_url=e_url if e_url else "",
                        duration=int(entry.get("duration") or 0),
                        thumbnail=entry.get("thumbnail") or "",
                        requester=requester,
                        source="YouTube",
                    )
                )
            if songs:
                return songs, f"YouTube Playlist **{playlist_title}** ({len(songs)} tracks)"
        except Exception as e:
            logger.error(f"Error extracting YouTube playlist: {e}")

    # 3. Direct URL or YouTube Search
    is_direct_url = query.startswith("http://") or query.startswith("https://")
    search_query = query if is_direct_url else f"ytsearch:{query}"

    loop = asyncio.get_event_loop()
    ydl = yt_dlp.YoutubeDL(YTDL_BASE_OPTS)
    try:
        info = await loop.run_in_executor(
            None,
            functools.partial(ydl.extract_info, search_query, download=False)
        )
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        if not info:
            return [], "No results found."

        song = Song(
            title=info.get("title", query),
            query=info.get("url", search_query),
            webpage_url=info.get("webpage_url", query),
            stream_url=info.get("url", ""),
            duration=int(info.get("duration") or 0),
            thumbnail=info.get("thumbnail") or "",
            requester=requester,
            source="YouTube",
        )
        song.is_resolved = bool(song.stream_url)
        return [song], f"**{song.title}**"

    except Exception as e:
        logger.error(f"Error searching song: {e}")
        return [], f"Failed to search: {str(e)}"
