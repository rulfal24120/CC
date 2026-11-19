"""Unduh video sumber: YouTube (yt-dlp) atau Google Drive (gdown).

Input : SOURCE_URL (env) — auto-detect host
        YTDLP_COOKIES_FILE (opsional, hanya untuk YouTube)
        YTDLP_VERBOSE=1 (opsional)
Output: build_clips/source/video.<ext> + info.json

Gate  : host didukung, bukan folder Drive, durasi <= MAX_SOURCE_MINUTES,
        ukuran <= MAX_SOURCE_MB, bukan live YouTube.

YouTube : cookies + Deno + impersonate chrome + PO Token Provider.
          Strategi fallback multi-player-client (android, ios, tv_embedded,
          mweb) untuk melewati bot-check yang memblokir client web.
Drive   : gdown (tidak butuh cookies / bot-check).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import common

SRC_DIR = Path("build_clips/source")

YOUTUBE_HOSTS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}
DRIVE_HOSTS = {"drive.google.com"}

POT_HOST = "127.0.0.1"
POT_PORT = 4416

# Regex file ID Google Drive
DRIVE_FILE_PATTERNS = [
    re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]{10,})"),
    re.compile(r"drive\.google\.com/uc\?(?:export=download&)?id=([a-zA-Z0-9_-]{10,})"),
    re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]{10,})"),
]

# Urutan client yang dicoba untuk YouTube. Client mobile/tv biasanya lebih
# tahan terhadap bot-check datacenter IP dibanding client web.
YOUTUBE_CLIENT_STRATEGIES = [
    ("android", "android"),
    ("ios", "ios"),
    ("tv_embedded,tv", "tv_embedded"),
    ("mweb", "mweb"),
]


# ---------------------------------------------------------------------------
# Deteksi & validasi
# ---------------------------------------------------------------------------

def _normalized_host(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        common.fail(f"source_url tidak bisa diparse: {url}")
    if parsed.scheme not in ("http", "https"):
        common.fail(f"source_url harus http/https: {url}")
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    return host


def _detect_source_type(url: str) -> str:
    host = _normalized_host(url)
    if host in YOUTUBE_HOSTS:
        return "youtube"
    if host in DRIVE_HOSTS:
        return "drive"
    common.fail(
        f"host tidak didukung: {host}. "
        "Didukung: youtube.com, youtu.be, drive.google.com"
    )
    raise RuntimeError("unreachable")


def _validate_drive_url(url: str) -> str:
    if "/drive/folders/" in url:
        common.fail(
            "URL folder Google Drive tidak didukung. "
            "Bagikan file tunggal (bukan folder) dan gunakan link file."
        )
    for pat in DRIVE_FILE_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    common.fail(
        "URL Google Drive tidak dikenali. Format yang didukung: "
        "https://drive.google.com/file/d/FILE_ID/view atau "
        "https://drive.google.com/uc?id=FILE_ID"
    )
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def _ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        common.warn("ffprobe_missing")
        return 0.0
    proc = common.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=False, timeout=60, label="ffprobe",
    )
    try:
        return float((proc.stdout or "").strip())
    except (ValueError, TypeError):
        common.warn("ffprobe_parse_failed", raw=(proc.stdout or "")[:100])
        return 0.0


def _fetch_drive(source_url: str, out_dir: Path) -> dict:
    file_id = _validate_drive_url(source_url)
    common.info("drive_start", file_id=file_id)

    try:
        import gdown  # noqa: PLC0415
    except ImportError as exc:
        common.fail(f"gdown tidak terpasang: {exc}")

    for old in out_dir.glob("video.*"):
        if old.is_file():
            old.unlink()
    for old in out_dir.glob("_drive_temp*"):
        if old.is_file():
            old.unlink()

    temp = out_dir / "_drive_temp"
    direct_url = f"https://drive.google.com/uc?id={file_id}"
    common.info("drive_download", url=direct_url)
    try:
        out = gdown.download(direct_url, str(temp), quiet=False, fuzzy=True)
    except Exception as exc:  # noqa: BLE001
        common.fail(f"gdown gagal: {type(exc).__name__}: {exc}")

    if not out:
        common.fail(
            "gdown tidak menghasilkan file. Kemungkinan: file private, "
            "kuota Drive terlampaui, atau file bukan video."
        )

    downloaded = Path(out)
    if not downloaded.is_file():
        candidates = list(out_dir.glob("_drive_temp*"))
        if not candidates:
            common.fail("gdown tidak menghasilkan file di folder sumber")
        downloaded = candidates[0]

    ext = downloaded.suffix.lower() or ".mp4"
    if ext not in {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}:
        common.warn("drive_unusual_extension", ext=ext)

    video_path = out_dir / f"video{ext}"
    if video_path.exists():
        video_path.unlink()
    downloaded.rename(video_path)

    size_mb = video_path.stat().st_size / (1024 * 1024)
    max_mb = common.get_env_int("MAX_SOURCE_MB", 2048)
    if size_mb > max_mb:
        video_path.unlink(missing_ok=True)
        common.fail(f"ukuran Drive {size_mb:.1f}MB > batas {max_mb}MB")

    duration = _ffprobe_duration(video_path)
    max_min = common.get_env_int("MAX_SOURCE_MINUTES", 60)
    if duration > 0 and duration > max_min * 60:
        video_path.unlink(missing_ok=True)
        common.fail(f"durasi Drive {duration:.0f} dtk > batas {max_min} menit")

    title = downloaded.stem or "Google Drive video"
    result = {
        "source_url": source_url,
        "source_type": "drive",
        "file_id": file_id,
        "video_path": str(video_path),
        "title": title,
        "channel": "Google Drive",
        "uploader_url": "",
        "duration_sec": duration,
        "size_mb": round(size_mb, 2),
        "fetched_at": common.now_iso(),
    }
    common.write_json(out_dir / "info.json", result)
    common.info("drive_ok", duration=f"{duration:.1f}s",
                size_mb=result["size_mb"], title=title)
    return result


# ---------------------------------------------------------------------------
# YouTube (dengan PO Token Provider + multi-client fallback)
# ---------------------------------------------------------------------------

def _pot_provider_ready(timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((POT_HOST, POT_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def _cookies_arg() -> list[str]:
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    if not cookie_file:
        return []
    p = Path(cookie_file)
    if not p.is_file():
        common.warn("cookies_file_missing", path=cookie_file)
        return []
    common.info("using_cookies", path=str(p))
    return ["--cookies", str(p)]


def _pot_args() -> list[str]:
    if not _pot_provider_ready():
        common.warn("pot_provider_unreachable", host=POT_HOST, port=POT_PORT)
        return []
    common.info("using_pot_provider", url=f"http://{POT_HOST}:{POT_PORT}")
    return [
        "--extractor-args",
        f"youtubepot-bgutilhttp:base_url=http://{POT_HOST}:{POT_PORT}",
    ]


def _verbose_arg() -> list[str]:
    return ["-v"] if os.getenv("YTDLP_VERBOSE", "").strip() == "1" else []


def _base_args() -> list[str]:
    return [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--force-ipv4",
        *_verbose_arg(),
        *_cookies_arg(),
        "--impersonate", "chrome",
        "--js-runtimes", "deno",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "--socket-timeout", "30",
        *_pot_args(),
    ]


def _run_ytdlp(extra_args: list[str], label: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = [*_base_args(), *extra_args]
    return common.run(cmd, timeout=timeout, label=label, check=False)


def _is_bot_check(stderr: str) -> bool:
    low = (stderr or "").lower()
    return ("sign in to confirm you" in low
            or "not a bot" in low
            or "login_required" in low)


def _is_cookie_invalid(stderr: str) -> bool:
    low = (stderr or "").lower()
    return ("cookies are no longer valid" in low
            or "cookie" in low and "expired" in low)


def _probe_youtube(url: str) -> tuple[dict | None, str]:
    """Coba setiap strategi client. Return (metadata, error_hint)."""
    last_hint = ""
    for client_arg, label in YOUTUBE_CLIENT_STRATEGIES:
        common.info("ytdlp_try_client", client=label)
        proc = _run_ytdlp(
            ["--extractor-args", f"youtube:player_client={client_arg}",
             "--dump-single-json", url],
            label=f"yt-dlp-meta-{label}",
            timeout=180,
        )
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout), ""
            except json.JSONDecodeError as exc:
                last_hint = f"JSON decode error: {exc}"
                continue

        stderr = proc.stderr or ""
        if _is_cookie_invalid(stderr):
            return None, "cookies_invalid"
        if _is_bot_check(stderr):
            last_hint = "bot_check"
            continue
        last_hint = (stderr or "unknown error")[:300]

    return None, last_hint


def _check_allowed_channel(channel: str) -> None:
    p = Path("allowed_channels.txt")
    if not p.is_file():
        return
    lines = [ln.strip().lower() for ln in p.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return
    if channel.lower() not in lines:
        common.warn("channel_not_in_whitelist", channel=channel)


def _download_youtube(url: str, out_dir: Path) -> Path:
    video_path = out_dir / "video.mp4"
    if video_path.is_file() and video_path.stat().st_size > 0:
        common.info("fetch_skip_cache", path=str(video_path),
                    size=video_path.stat().st_size)
        return video_path

    common.ensure_dir(out_dir)
    max_mb = common.get_env_int("MAX_SOURCE_MB", 2048)
    max_min = common.get_env_int("MAX_SOURCE_MINUTES", 60)

    last_hint = ""
    for client_arg, label in YOUTUBE_CLIENT_STRATEGIES:
        common.info("ytdlp_download_try", client=label)
        cmd_extra = [
            "--extractor-args", f"youtube:player_client={client_arg}",
            "-f", "bv*[height<=1080]+ba/b[height<=1080]",
            "--merge-output-format", "mp4",
            "--max-filesize", f"{max_mb}M",
            "--match-filter", f"duration < {max_min * 60 + 1}",
            "-o", str(video_path),
            url,
        ]
        proc = _run_ytdlp(cmd_extra, label=f"yt-dlp-download-{label}",
                         timeout=1800)
        if proc.returncode == 0 and video_path.is_file():
            return video_path

        stderr = proc.stderr or ""
        if _is_cookie_invalid(stderr):
            common.fail(
                "Cookie YouTube sudah tidak valid (expired/rotated). "
                "Ekspor ulang cookies dari browser dan perbarui secret "
                "YOUTUBE_COOKIES_B64."
            )
        last_hint = (stderr or "unknown")[:300]

    common.fail(
        f"yt-dlp gagal setelah mencoba {len(YOUTUBE_CLIENT_STRATEGIES)} client. "
        f"Error terakhir: {last_hint}. "
        "Jika masalah berlanjut, IP runner kemungkinan diblokir permanen; "
        "gunakan Google Drive sebagai sumber atau proxy residensial."
    )
    raise RuntimeError("unreachable")


def _fetch_youtube(source_url: str, out_dir: Path) -> dict:
    common.info("fetch_start", source="youtube", url=source_url)
    meta, hint = _probe_youtube(source_url)
    if meta is None:
        if hint == "cookies_invalid":
            common.fail(
                "Cookie YouTube sudah tidak valid. Perbarui secret "
                "YOUTUBE_COOKIES_B64 dengan cookies baru dari browser."
            )
        common.fail(
            f"Bot-check YouTube masih aktif meski PO Token berjalan. "
            f"Hint: {hint}. "
            "Coba: (1) perbarui cookies, (2) gunakan Google Drive, "
            "atau (3) jalankan di IP residensial."
        )

    if meta.get("is_live"):
        common.fail("sumber masih live; tunggu selesai dan coba lagi")

    duration = float(meta.get("duration") or 0)
    max_min = common.get_env_int("MAX_SOURCE_MINUTES", 60)
    if duration <= 0:
        common.fail("durasi sumber tidak terbaca")
    if duration > max_min * 60:
        common.fail(f"sumber {duration:.0f} dtk > batas {max_min} menit")

    channel = meta.get("channel") or meta.get("uploader") or ""
    _check_allowed_channel(channel)

    video_path = _download_youtube(source_url, out_dir)
    size_mb = video_path.stat().st_size / (1024 * 1024)
    result = {
        "source_url": source_url,
        "source_type": "youtube",
        "video_path": str(video_path),
        "title": meta.get("title") or "",
        "channel": channel,
        "uploader_url": meta.get("uploader_url") or "",
        "duration_sec": duration,
        "size_mb": round(size_mb, 2),
        "fetched_at": common.now_iso(),
    }
    common.write_json(out_dir / "info.json", result)
    common.info("fetch_ok", source="youtube",
                duration=f"{duration:.1f}s", size_mb=result["size_mb"])
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def fetch(source_url: str) -> dict:
    _detect_source_type(source_url)
    out_dir = common.ensure_dir(SRC_DIR)
    info_file = out_dir / "info.json"

    if info_file.is_file():
        meta = common.read_json(info_file) or {}
        if (meta.get("source_url") == source_url
                and meta.get("video_path")
                and Path(meta["video_path"]).is_file()):
            common.info("fetch_meta_cache", path=str(info_file))
            return meta

    stype = _detect_source_type(source_url)
    if stype == "youtube":
        return _fetch_youtube(source_url, out_dir)
    if stype == "drive":
        return _fetch_drive(source_url, out_dir)
    common.fail(f"source_type tidak dikenal: {stype}")
    raise RuntimeError("unreachable")


def _main() -> None:
    url = common.get_env("SOURCE_URL", required=True)
    print(json.dumps(fetch(url), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"fetch_source crash: {type(exc).__name__}: {exc}")
