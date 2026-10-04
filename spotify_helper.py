import re
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
import requests

from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

logger = logging.getLogger(__name__)

# Regular expressions for Spotify URLs
SPOTIFY_TRACK_REGEX = re.compile(r"https?://open\.spotify\.com(?:/[a-zA-Z-]+)?/track/([a-zA-Z0-9]+)")
SPOTIFY_PLAYLIST_REGEX = re.compile(r"https?://open\.spotify\.com(?:/[a-zA-Z-]+)?/playlist/([a-zA-Z0-9]+)")
SPOTIFY_ALBUM_REGEX = re.compile(r"https?://open\.spotify\.com(?:/[a-zA-Z-]+)?/album/([a-zA-Z0-9]+)")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Optional Spotipy client
_sp_client = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        _sp_client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET
            )
        )
        logger.info("Spotify API credentials loaded successfully.")
    except Exception as e:
        logger.warning(f"Could not initialize Spotify API client: {e}. Falling back to metadata extraction.")


def is_spotify_url(url: str) -> bool:
    """Returns True if the URL is a Spotify track, playlist, or album."""
    if not isinstance(url, str):
        return False
    return bool(
        SPOTIFY_TRACK_REGEX.search(url)
        or SPOTIFY_PLAYLIST_REGEX.search(url)
        or SPOTIFY_ALBUM_REGEX.search(url)
    )


def extract_spotify_info(url: str) -> Tuple[str, Any]:
    """
    Parses a Spotify URL.
    Returns a tuple of (type, data):
      - ('track', 'Song Title Artist Name')
      - ('playlist', {'title': 'Playlist Name', 'tracks': ['Song 1 Artist', 'Song 2 Artist', ...]})
      - ('album', {'title': 'Album Name', 'tracks': ['Song 1 Artist', 'Song 2 Artist', ...]})
      - ('unknown', None)
    """
    track_match = SPOTIFY_TRACK_REGEX.search(url)
    if track_match:
        track_id = track_match.group(1)
        query = _get_track_query(url, track_id)
        return ("track", query)

    playlist_match = SPOTIFY_PLAYLIST_REGEX.search(url)
    if playlist_match:
        playlist_id = playlist_match.group(1)
        data = _get_playlist_or_album(f"https://open.spotify.com/playlist/{playlist_id}", "playlist", playlist_id)
        return ("playlist", data)

    album_match = SPOTIFY_ALBUM_REGEX.search(url)
    if album_match:
        album_id = album_match.group(1)
        data = _get_playlist_or_album(f"https://open.spotify.com/album/{album_id}", "album", album_id)
        return ("album", data)

    return ("unknown", None)


def _get_track_query(url: str, track_id: str) -> str:
    """Extracts track name and artist from a track URL or ID."""
    # 1. Try Spotipy if available
    if _sp_client:
        try:
            track = _sp_client.track(track_id)
            title = track.get("name", "")
            artists = ", ".join([a["name"] for a in track.get("artists", [])])
            if title:
                return f"{title} {artists}".strip()
        except Exception as e:
            logger.debug(f"Spotipy track lookup error: {e}")

    # 2. Try scraping Spotify track page
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code == 200:
            # Pattern: <title>Song Title - song and lyrics by Artist | Spotify</title>
            match = re.search(
                r"<title>(.+?)\s*-\s*song\s*(?:and\s*lyrics)?\s*by\s*(.+?)\s*\|\s*Spotify</title>",
                resp.text,
                re.IGNORECASE
            )
            if match:
                title = match.group(1).strip()
                artist = match.group(2).strip()
                return f"{title} {artist}".strip()
            
            # Alternative og:title pattern
            og_match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
            if og_match:
                title = og_match.group(1).strip()
                desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', resp.text)
                desc = desc_match.group(1).strip() if desc_match else ""
                # desc often has "Artist · Song · Year"
                artist = desc.split("·")[0].strip() if "·" in desc else ""
                return f"{title} {artist}".strip()
    except Exception as e:
        logger.debug(f"Track page scraping error: {e}")

    # 3. Fallback to Spotify oEmbed API
    try:
        oembed_resp = requests.get(
            "https://open.spotify.com/oembed",
            params={"url": f"https://open.spotify.com/track/{track_id}"},
            timeout=10
        )
        if oembed_resp.status_code == 200:
            data = oembed_resp.json()
            title = data.get("title", "")
            if title:
                return title
    except Exception as e:
        logger.debug(f"Spotify oEmbed error: {e}")

    return f"spotify track {track_id}"


def _get_playlist_or_album(url: str, entity_type: str, entity_id: str) -> Dict[str, Any]:
    """Extracts track names and artists from a playlist or album."""
    # 1. Try Spotipy if available
    if _sp_client:
        try:
            if entity_type == "playlist":
                results = _sp_client.playlist(entity_id)
                name = results.get("name", "Spotify Playlist")
                tracks = []
                for item in results.get("tracks", {}).get("items", []):
                    track = item.get("track")
                    if track and track.get("name"):
                        t_name = track["name"]
                        t_artists = ", ".join([a["name"] for a in track.get("artists", [])])
                        tracks.append(f"{t_name} {t_artists}".strip())
                if tracks:
                    return {"title": name, "tracks": tracks}
            elif entity_type == "album":
                results = _sp_client.album(entity_id)
                name = results.get("name", "Spotify Album")
                artist_name = ", ".join([a["name"] for a in results.get("artists", [])])
                tracks = []
                for track in results.get("tracks", {}).get("items", []):
                    if track and track.get("name"):
                        t_name = track["name"]
                        tracks.append(f"{t_name} {artist_name}".strip())
                if tracks:
                    return {"title": name, "tracks": tracks}
        except Exception as e:
            logger.debug(f"Spotipy {entity_type} lookup error: {e}")

    # 2. Scrape from Spotify embed page (No API key needed!)
    try:
        embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
        resp = requests.get(embed_url, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code == 200:
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text)
            if match:
                data = json.loads(match.group(1))
                entity = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("state", {})
                    .get("data", {})
                    .get("entity", {})
                )
                title = entity.get("title") or entity.get("name") or f"Spotify {entity_type.capitalize()}"
                raw_tracks = entity.get("trackList", [])
                tracks = []
                for item in raw_tracks:
                    t_title = item.get("title", "")
                    t_subtitle = item.get("subtitle", "")
                    if t_title:
                        query = f"{t_title} {t_subtitle}".strip()
                        tracks.append(query)
                if tracks:
                    return {"title": title, "tracks": tracks}
    except Exception as e:
        logger.debug(f"Embed scraping error for {entity_type}: {e}")

    # 3. Fallback: return single track if possible
    return {"title": f"Spotify {entity_type.capitalize()}", "tracks": []}
