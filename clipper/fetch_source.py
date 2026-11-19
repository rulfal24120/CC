"""Unduh video sumber YouTube via yt-dlp.

Input : SOURCE_URL (env), YTDLP_COOKIES_FILE (opsional)
Output: build_clips/source/video.mp4 + info.json

Strategi anti-bot-check (berlapis):
1. Cookies dari YOUTUBE_COOKIES_B64 (workflow menyiapkan cookies.txt)
2. Deno sebagai JS runtime (wajib sejak yt-dlp 2025.11.12)
3. player_client=tv,mweb (paling jarang diblokir)
4. --impersonate chrome (butuh curl-cffi)
5. Fallback otomatis ke tv,web_safari lalu default
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import common

SRC_DIR = Path("build_clips/source")
ALLOWED_HOSTS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}

# Urutan percobaan player_client. None = pakai default yt-dlp.
_EXTRACTOR_CANDIDATES: list[str | None] = [
    "youtube:player_client=tv,mweb",
    "youtube:player_client=tv,web_safari",
    None,
]
_WORKING_EXTRACTOR: str | None = None


def _validate_url(url: str) -> None:
    """Validasi ringan: host harus YouTube. Path bebas (watch/live/shorts/embed)."""
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


def _cookies_arg() -> list[str]:
    """Kembalikan ['--cookies', path] jika YTDLP_COOKIES_FILE tersedia."""
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    if not cookie_file:
        return []
    p = Path(cookie_file)
    if not p.is_file():
        common.warn("cookies_file_missing", path=cookie_file)
        return []
    common.info("using_cookies", path=str(p))
    return ["--cookies", str(p)]


def _base_args() -> list[str]:
    """Argumen dasar yang selalu dipakai: cookies, impersonate, JS runtime."""
    return [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        *_cookies_arg(),
        "--impersonate", "chrome",
        "--js-runtimes", "deno",
    ]


def _extractor_arg(extractor: str | None) -> list[str]:
    if not extractor:
        return []
    return ["--extractor-args", extractor]


def _run_ytdlp(extra_args: list[str], label: str, timeout: int) -> subprocess.CompletedProcess:
    """Jalankan yt-dlp tanpa raise; caller memutuskan berdasarkan stderr/returncode."""
    cmd = [*_base_args(), *extra_args]
    return common.run(cmd, timeout=timeout, label=label, check=False)


def _is_bot_check(stderr: str) -> bool:
    low = (stderr or "").lower()
    return "sign in to confirm you" in low or "not a bot" in low


def _probe(url: str) -> dict:
    """Ambil metadata. Coba beberapa player_client sampai ada yang lolos."""
    global _WORKING_EXTRACTOR
    candidates: list[str | None] = []
    if _WORKING_EXTRACTOR:
        candidates.append(_WORKING_EXTRACTOR)
    for c in _EXTRACTOR_CANDIDATES:
        if c not in candidates:
            candidates.append(c)

    last_err = ""
    for ext in candidates:
        label = f"yt-dlp-meta[{ext or 'default'}]"
        common.info("probe_attempt", extractor=ext or "default")
        proc = _run_ytdlp(
            [*_extractor_arg(ext), "--dump-single-json", url],
            label=label,
            timeout=120,
        )
        if proc.returncode == 0:
            try:
                meta = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                last_err = f"metadata tidak valid: {exc}"
                continue
            _WORKING_EXTRACTOR = ext
            common.info("probe_ok", extractor=ext or "default")
            return meta

        last_err = (proc.stderr or "")[:300]
        if _is_bot_check(proc.stderr):
            common.warn("bot_check_retry", extractor=ext or "default")
            continue
        # Error non-bot (private, unavailable, dsb.) — coba kandidat berikutnya
        common.warn("probe_failed_non_bot", extractor=ext or "default",
                    err=last_err)

    common.fail(
        "Semua percobaan yt-dlp kena bot-check atau gagal. "
        "Langkah berikutnya: pasang PO Token Provider "
        "(https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) "
        f"atau perbarui cookies. Error terakhir: {last_err}"
    )
    raise RuntimeError("unreachable")


def _check_allowed_channel(channel: str) -> None:
    p = Path("allowed_channels.txt")
    if not p.is_file():
        return
    lines = [ln.strip().lower() for ln in p.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return
    if channel.lower() not in lines:
        common.warn("channel_not_in_whitelist", channel=channel,
                    note="trial mode: lanjut dengan peringatan")


def _download(url: str, out_dir: Path) -> Path:
    """Unduh video menggunakan extractor yang berhasil saat probe."""
    video_path = out_dir / "video.mp4"
    if video_path.is_file() and video_path.stat().st_size > 0:
        common.info("fetch_skip_cache", path=str(video_path),
                    size=video_path.stat().st_size)
        return video_path

    common.ensure_dir(out_dir)
    max_mb = common.get_env_int("MAX_SOURCE_MB", 2048)
    max_min = common.get_env_int("MAX_SOURCE_MINUTES", 60)

    cmd_extra = [
        *_extractor_arg(_WORKING_EXTRACTOR),
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
                "Bot-check muncul saat download meski metadata berhasil. "
                "Coba naikkan ke PO Token Provider "
                "(https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)."
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
        "extractor_used": _WORKING_EXTRACTOR or "default",
    }
    common.write_json(info_file, result)
    common.info("fetch_ok", duration=f"{duration:.1f}s",
                size_mb=result["size_mb"],
                extractor=result["extractor_used"])
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
