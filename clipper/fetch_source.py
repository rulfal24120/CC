"""Unduh video sumber YouTube via yt-dlp dengan PO Token Provider.

Input : SOURCE_URL (env), YTDLP_COOKIES_FILE (opsional),
        YTDLP_VERBOSE (opsional, "1" untuk log verbose)
Output: build_clips/source/video.mp4 + info.json

Strategi anti-bot-check:
1. Cookies (YOUTUBE_COOKIES_B64)
2. Deno sebagai JS runtime
3. --impersonate chrome (curl-cffi)
4. PO Token Provider (bgutil-ytdlp-pot-provider) di http://127.0.0.1:4416
5. player_client=mweb,tv,web_safari memicu permintaan PO Token
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import common

SRC_DIR = Path("build_clips/source")
ALLOWED_HOSTS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}
POT_HOST = "127.0.0.1"
POT_PORT = 4416


def _validate_url(url: str) -> None:
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
    if host not in ALLOWED_HOSTS:
        common.fail(f"source_url bukan host YouTube: {host or url}")


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
    """Konfigurasi PO Token Provider.

    player_client=mweb,tv,web_safari memicu permintaan PO Token.
    fetch_pot=always memaksa token diambil untuk klien yang butuh.
    """
    if not _pot_provider_ready():
        common.warn("pot_provider_unreachable", host=POT_HOST, port=POT_PORT)
        return []
    common.info("using_pot_provider", url=f"http://{POT_HOST}:{POT_PORT}")
    return [
        "--extractor-args",
        "youtube:player_client=mweb,tv,web_safari;fetch_pot=always",
        "--extractor-args",
        f"youtubepot-bgutilhttp:base_url=http://{POT_HOST}:{POT_PORT}",
    ]


def _verbose_arg() -> list[str]:
    if os.getenv("YTDLP_VERBOSE", "").strip() == "1":
        return ["-v"]
    return []


def _base_args() -> list[str]:
    return [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        *_verbose_arg(),
        *_cookies_arg(),
        "--impersonate", "chrome",
        "--js-runtimes", "deno",
        *_pot_args(),
    ]


def _run_ytdlp(extra_args: list[str], label: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = [*_base_args(), *extra_args]
    return common.run(cmd, timeout=timeout, label=label, check=False)


def _is_bot_check(stderr: str) -> bool:
    low = (stderr or "").lower()
    return "sign in to confirm you" in low or "not a bot" in low


def _probe(url: str) -> dict:
    proc = _run_ytdlp(["--dump-single-json", url],
                      label="yt-dlp-meta", timeout=180)
    if proc.returncode != 0:
        if _is_bot_check(proc.stderr):
            common.fail(
                "Bot-check muncul meski PO Token Provider aktif. "
                "Jalankan ulang dengan YTDLP_VERBOSE=1 untuk melihat apakah "
                "baris 'Generating a gvs PO Token' muncul. Jika tidak muncul, "
                "IP runner sudah diblokir YouTube di tahap awal — perlu proxy "
                "residensial atau jalankan di luar GitHub Actions."
            )
        common.fail(
            f"yt-dlp-meta gagal (exit {proc.returncode}): "
            f"{(proc.stderr or '')[:300]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        common.fail(f"metadata youtube tidak valid: {exc}")


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


def _download(url: str, out_dir: Path) -> Path:
    video_path = out_dir / "video.mp4"
    if video_path.is_file() and video_path.stat().st_size > 0:
        common.info("fetch_skip_cache", path=str(video_path),
                    size=video_path.stat().st_size)
        return video_path

    common.ensure_dir(out_dir)
    max_mb = common.get_env_int("MAX_SOURCE_MB", 2048)
    max_min = common.get_env_int("MAX_SOURCE_MINUTES", 60)

    cmd_extra = [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]",
        "--merge-output-format", "mp4",
        "--max-filesize", f"{max_mb}M",
        "--match-filter", f"duration < {max_min * 60 + 1}",
        "-o", str(video_path),
        url,
    ]
    proc = _run_ytdlp(cmd_extra, label="yt-dlp-download", timeout=1800)

    if proc.returncode != 0:
        if _is_bot_check(proc.stderr):
            common.fail(
                "Bot-check muncul saat download. "
                "Coba hapus cookies (andalkan PO token murni) atau "
                "periksa log container bgutil-provider."
            )
        common.fail(
            f"yt-dlp download gagal (exit {proc.returncode}): "
            f"{(proc.stderr or '')[:300]}"
        )
    if not video_path.is_file():
        common.fail("yt-dlp tidak menghasilkan file video")
    return video_path


def fetch(source_url: str) -> dict:
    _validate_url(source_url)
    out_dir = common.ensure_dir(SRC_DIR)
    info_file = out_dir / "info.json"
    if info_file.is_file():
        meta = common.read_json(info_file) or {}
        if meta.get("video_path") and Path(meta["video_path"]).is_file():
            common.info("fetch_meta_cache", path=str(info_file))
            return meta

    common.info("fetch_start", url=source_url)
    meta = _probe(source_url)

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

    video_path = _download(source_url, out_dir)
    size_mb = video_path.stat().st_size / (1024 * 1024)
    result = {
        "source_url": source_url,
        "video_path": str(video_path),
        "title": meta.get("title") or "",
        "channel": channel,
        "uploader_url": meta.get("uploader_url") or "",
        "duration_sec": duration,
        "size_mb": round(size_mb, 2),
        "fetched_at": common.now_iso(),
    }
    common.write_json(info_file, result)
    common.info("fetch_ok", duration=f"{duration:.1f}s",
                size_mb=result["size_mb"])
    return result


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
