import os
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file when running locally.
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")


def _is_working_ffmpeg(candidate: str) -> bool:
    """Return whether candidate can actually start and report its version."""
    try:
        result = subprocess.run(
            [candidate, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_ffmpeg() -> str:
    """Find a runnable FFmpeg binary across Render/Linux and local Windows."""
    candidates = []
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured:
        candidates.append(shutil.which(configured) or configured)

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        candidates.append(system_ffmpeg)

    # imageio-ffmpeg ships a platform-specific executable and works on Render
    # even when the host image does not provide FFmpeg on PATH.
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError, OSError):
        pass

    local_names = ("ffmpeg", "ffmpeg.exe")
    for name in local_names:
        local_binary = Path(__file__).parent / name
        if local_binary.is_file():
            candidates.append(str(local_binary))

    checked = set()
    for candidate in candidates:
        if candidate and candidate not in checked:
            checked.add(candidate)
            if _is_working_ffmpeg(candidate):
                return candidate

    raise RuntimeError(
        "FFmpeg is missing or cannot run. Install the imageio-ffmpeg dependency, "
        "or set FFMPEG_PATH to a working FFmpeg executable."
    )


FFMPEG_PATH = find_ffmpeg()