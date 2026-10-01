import os
import shutil
import glob
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Discord Bot Token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Command Prefix (default: !)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

# Spotify API credentials (Optional - bot works without these too!)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

def find_ffmpeg() -> str:
    """
    Finds the ffmpeg executable.
    Checks PATH first, then common Windows locations (WinGet Gyan.FFmpeg, Chocolatey, local folder).
    """
    # 1. Check in system PATH
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        return ffmpeg_in_path

    # 2. Check local project folder
    local_ffmpeg = Path(__file__).parent / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    # 3. Check WinGet package location
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        winget_pattern = os.path.join(
            local_app_data,
            "Microsoft", "WinGet", "Packages",
            "*FFmpeg*", "**", "ffmpeg.exe"
        )
        matches = glob.glob(winget_pattern, recursive=True)
        if matches:
            return matches[0]

    # 4. Check Program Files / Chocolatey
    common_paths = [
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p

    # Fallback to plain command name
    return "ffmpeg"

FFMPEG_PATH = find_ffmpeg()
