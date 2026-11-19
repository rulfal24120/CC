"""Unduh video sumber dari YouTube via yt-dlp.

Input : source_url (arg/env SOURCE_URL)
Output: build_clips/source/video.mp4 + build_clips/source/info.json
Gate  : YouTube saja, durasi <= MAX_SOURCE_MINUTES, ukuran <= MAX_SOURCE_MB.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import common

YT_RE = re.compile(r"^(https?://)?(www\.|m\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]{6,}")
SRC_DIR = Path("build_clips/source")


def _validate_url(url: str) -> None:
    if not YT_RE.match(url.strip()):
        common.fail(f"source_url bukan YouTube yang valid: {url}")


def _download(url: str, out_dir: Path) -> Path:
    video_path = out_dir / "video.mp4"
    if video_path.is_file() and video_path.stat().st_size > 0:
        common.info("fetch_skip_cache", path=str(video_path), size=video_path.stat().st_size)
        return video_path
    common.ensure_dir(out_dir)
    max_mb = common.get_env_int("MAX_SOURCE_MB", 2048)
    common.run([
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]",
        "--merge-output-format", "mp4",
        "--max-filesize", f"{max_mb}M",
        "--match-filter", f"duration < {common.get_env_int('MAX_SOURCE_MINUTES', 60) * 60 + 1}",
        "-o", str(video_path),
        url,
    ], timeout=1800, label="yt-dlp")
    if not video_path.is_file():
        common.fail("yt-dlp tidak menghasilkan file video")
    return video_path


def _probe(url: str) -> dict:
    proc = common.run(
        ["yt-dlp", "--no-playlist", "--dump-single-json", "--no-warnings", url],
        timeout=120, label="yt-dlp-meta",
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
        return  # kosong = semua diizinkan
    if channel.lower() not in lines:
        common.warn("channel_not_in_whitelist", channel=channel,
                    note="lanjut karena workflow_dispatch manual dianggap izin")


def fetch(source_url: str) -> dict:
    """Unduh sumber + return metadata."""
    _validate_url(source_url)
    out_dir = common.ensure_dir(SRC_DIR)
    info_file = out_dir / "info.json"
    if info_file.is_file():
        common.info("fetch_meta_cache", path=str(info_file))
        meta = common.read_json(info_file) or {}
        if meta.get("video_path") and Path(meta["video_path"]).is_file():
            return meta
    common.info("fetch_start", url=source_url)
    meta = _probe(source_url)
    duration = float(meta.get("duration") or 0)
    max_min = common.get_env_int("MAX_SOURCE_MINUTES", 60)
    if duration <= 0:
        common.fail("durasi sumber tidak terbaca")
    if duration > max_min * 60:
        common.fail(f"sumber {duration:.0f} dtk > batas {max_min} menit")
    _check_allowed_channel(meta.get("channel") or meta.get("uploader") or "")
    video_path = _download(source_url, out_dir)
    size_mb = video_path.stat().st_size / (1024 * 1024)
    result = {
        "source_url": source_url,
        "video_path": str(video_path),
        "title": meta.get("title") or "",
        "channel": meta.get("channel") or meta.get("uploader") or "",
        "uploader_url": meta.get("uploader_url") or "",
        "duration_sec": duration,
        "size_mb": round(size_mb, 2),
        "fetched_at": common.now_iso(),
    }
    common.write_json(info_file, result)
    common.info("fetch_ok", duration=f"{duration:.1f}s", size_mb=result["size_mb"])
    return result


def _main() -> None:
    url = common.get_env("SOURCE_URL", required=True)
    info = fetch(url)
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"fetch_source crash: {type(exc).__name__}: {exc}")
