import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.media.errors import InvalidMediaError, MediaToolError

_STDERR_TAIL = 2000

@dataclass(frozen=True)
class AudioInfo:
    duration_s: float

def _tail(text: str) -> str:
    return text.strip()[-_STDERR_TAIL:]

def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise MediaToolError(f"{cmd[0]} not found in PATH") from e
    except subprocess.TimeoutExpired as e:
        raise MediaToolError(f"{cmd[0]} timed out after {timeout}s") from e

def probe_audio(src: Path, timeout: float = 30) -> AudioInfo:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type:format=duration",
         "-of", "json",
         str(src),
    ]
    p = _run(cmd, timeout)
    if p.returncode != 0:
        raise InvalidMediaError(_tail(p.stderr) or "ffprobe failed")

    data = json.loads(p.stdout or "{}")
    if not data.get("streams"):
        raise InvalidMediaError("no audio stream")
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, ValueError):
        raise InvalidMediaError("unknown duration") from None
    return AudioInfo(duration_s=duration)

def to_wav_16k_mono(src: Path, dst: Path, timeout: float = 900) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vn", "-map", "0:a:0",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        "-f", "wav",
        str(tmp),
    ]
    try:
        p = _run(cmd, timeout)
        if p.returncode != 0:
            raise InvalidMediaError(_tail(p.stderr) or f"ffmpeg exit code {p.returncode}")
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst
