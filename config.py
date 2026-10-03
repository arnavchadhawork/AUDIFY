import os
import subprocess
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

def find_ffmpeg() -> str:
    """
    Find a system FFmpeg executable, falling back to the bundled imageio binary.
    """
    configured_path = os.getenv("FFMPEG_PATH")
    if configured_path:
        configured_executable = shutil.which(configured_path)
        if configured_executable:
            return configured_executable
        if Path(configured_path).is_file():
            return str(Path(configured_path).resolve())
        raise FileNotFoundError("FFMPEG_PATH is set but does not point to an executable.")

    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        return str(Path(ffmpeg_in_path).resolve())

    executable_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    local_ffmpeg = Path(__file__).parent / executable_name
    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    # Windows package-manager locations
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if os.name == "nt" and local_app_data:
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
    if os.name == "nt":
        for path in common_paths:
            if os.path.exists(path):
                return path

    try:
        import imageio_ffmpeg
        bundled_ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    except (ImportError, OSError, RuntimeError) as error:
        raise RuntimeError(
            "FFmpeg was not found. Install the pinned imageio-ffmpeg dependency "
            "or configure FFMPEG_PATH, then redeploy."
        ) from error

    if bundled_ffmpeg.is_file():
        return str(bundled_ffmpeg)

    raise FileNotFoundError(
        f"imageio-ffmpeg returned a missing executable: {bundled_ffmpeg}"
    )

FFMPEG_PATH = find_ffmpeg()


def validate_ffmpeg() -> None:
    """Fail at startup if the selected FFmpeg binary cannot actually run."""
    try:
        subprocess.run(
            [FFMPEG_PATH, "-version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            f"FFmpeg executable could not run at {FFMPEG_PATH!r}. "
            "Install imageio-ffmpeg or set FFMPEG_PATH to a working binary."
        ) from error
