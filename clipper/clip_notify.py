"""Notifikasi Telegram (teks + thumbnail + video klip).

Perubahan vs versi lama:
- Tambah send_video(): kirim file MP4 ke chat via sendVideo (multipart).
  Batas 50 MB per file (batas bot Telegram standar). Kalau > 50 MB,
  fallback ke teks saja, pipeline TIDAK gagal.
- Tambah send_clip_videos(): iterasi list clip yang sudah dirender, kirim
  video per clip dengan caption berisi clip_id, durasi, skor, dan cuplikan.
- Semua fungsi kirim bersifat best-effort: gagal kirim = warn, bukan fail.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import common

TG = "https://api.telegram.org"

# Batas bot Telegram standar. Untuk file lebih besar butuh Bot API server
# lokal, di luar cakupan trial ini.
TELEGRAM_MAX_UPLOAD_MB = 50


def _api(method: str, payload: dict) -> dict:
    import requests  # noqa: PLC0415
    token = common.get_env("TELEGRAM_BOT_TOKEN", required=True)
    r = requests.post(f"{TG}/bot{token}/{method}", json=payload, timeout=30)
    if r.status_code >= 400:
        common.warn("telegram_fail", method=method, status=r.status_code,
                    body=r.text[:200])
    return r.json() if r.content else {}


def _chat() -> str:
    return common.get_env("TELEGRAM_CHAT_ID", required=True)


# ---------------------------------------------------------------------------
# Kirim teks & foto
# ---------------------------------------------------------------------------

def send_text(text: str) -> None:
    _api("sendMessage", {"chat_id": _chat(), "text": text[:4000],
                         "parse_mode": "HTML", "disable_web_page_preview": True})


def send_photo(path: str, caption: str) -> None:
    import requests  # noqa: PLC0415
    p = Path(path)
    if not p.is_file():
        send_text(caption)
        return
    token = common.get_env("TELEGRAM_BOT_TOKEN", required=True)
    with p.open("rb") as f:
        r = requests.post(f"{TG}/bot{token}/sendPhoto",
                          data={"chat_id": _chat(), "caption": caption[:1000],
                                "parse_mode": "HTML"},
                          files={"photo": f}, timeout=60)
    if r.status_code >= 400:
        common.warn("telegram_photo_fail", status=r.status_code)
        send_text(caption)


# ---------------------------------------------------------------------------
# Kirim video (MP4 hasil render)
# ---------------------------------------------------------------------------

def send_video(path: str, caption: str = "",
               max_mb: int = TELEGRAM_MAX_UPLOAD_MB) -> bool:
    """Kirim satu file video ke Telegram. Return True kalau berhasil.

    Best-effort: kalau gagal atau terlalu besar, kirim caption sebagai teks
    dan return False. Tidak pernah raise.
    """
    import requests  # noqa: PLC0415
    p = Path(path)
    if not p.is_file():
        common.warn("telegram_video_missing", path=str(p))
        if caption:
            send_text(caption)
        return False

    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        common.warn("telegram_video_too_large",
                    path=str(p), size_mb=round(size_mb, 2), limit_mb=max_mb)
        if caption:
            send_text(caption + f"\n(file {size_mb:.1f} MB, terlalu besar "
                                f"untuk bot Telegram)")
        return False

    token = common.get_env("TELEGRAM_BOT_TOKEN", required=True)
    try:
        with p.open("rb") as f:
            r = requests.post(
                f"{TG}/bot{token}/sendVideo",
                data={
                    "chat_id": _chat(),
                    "caption": caption[:1000],
                    "parse_mode": "HTML",
                    "supports_streaming": "true",
                },
                files={"video": f},
                timeout=180,
            )
    except Exception as exc:  # noqa: BLE001
        common.warn("telegram_video_err", path=str(p),
                    err=type(exc).__name__, detail=str(exc)[:200])
        if caption:
            send_text(caption)
        return False

    if r.status_code >= 400:
        common.warn("telegram_video_fail", status=r.status_code,
                    body=r.text[:200])
        if caption:
            send_text(caption)
        return False

    common.info("telegram_video_ok", path=str(p), size_mb=round(size_mb, 2))
    return True


def _clip_caption(clip: dict) -> str:
    cid = str(clip.get("clip_id", "?"))
    dur = clip.get("duration_sec", 0)
    score = clip.get("final_score", clip.get("score", 0))
    text = (clip.get("text") or "")[:200].replace("\n", " ")
    return (
        f"<b>Clip siap</b> <code>{cid}</code>\n"
        f"Durasi: {dur}s | Skor: {score}\n\n"
        f"{text}"
    )


def send_clip_videos(clips: list[dict]) -> int:
    """Kirim semua klip yang punya video_path. Return jumlah yang terkirim."""
    sent = 0
    for c in clips:
        path = c.get("video_path")
        if not path:
            continue
        try:
            if send_video(path, _clip_caption(c)):
                sent += 1
        except Exception as exc:  # noqa: BLE001
            common.warn("telegram_send_clip_err",
                        clip_id=c.get("clip_id"),
                        err=type(exc).__name__,
                        detail=str(exc)[:200])
    common.info("telegram_clips_sent", total=len(clips), sent=sent)
    return sent


# ---------------------------------------------------------------------------
# Notifikasi tingkat pipeline
# ---------------------------------------------------------------------------

def produce_summary(source_url: str, clips: list[dict]) -> None:
    lines = ["<b>Apaiya? Clipper</b>",
             f"Sumber: {source_url}",
             f"Clip siap dijadwalkan: <b>{len(clips)}</b>", ""]
    for c in clips:
        lines.append(f"• <code>{c['clip_id']}</code> "
                     f"({c['duration_sec']}s, skor {c['final_score']})")
        lines.append(f"  tayang {c['scheduled_date']} slot {c['slot']}")
    lines.append("\nPublish otomatis 2/hari (12:00 & 19:00 WIB).")
    text = "\n".join(lines)
    if clips and clips[0].get("thumbnail_path"):
        send_photo(clips[0]["thumbnail_path"], text)
    else:
        send_text(text)


def publish_result(clip: dict, result: dict) -> None:
    lines = [
        f"<b>Published</b> <code>{clip['clip_id']}</code>",
        f"YouTube (private): {result.get('youtube_url') or '-'}",
        f"Facebook (public): {result.get('facebook_url') or '-'}",
    ]
    text = "\n".join(lines)
    if clip.get("thumbnail_path"):
        send_photo(clip["thumbnail_path"], text)
    else:
        send_text(text)


def publish_failed(clip: dict, reason: str) -> None:
    send_text(f"<b>Gagal publish</b> <code>{clip['clip_id']}</code>\n"
              f"{reason[:600]}")


def fail_notification(stage: str, reason: str) -> None:
    log_url = common.get_env("GH_RUN_URL", required=False, default="")
    send_text(f"<b>Pipeline gagal</b> di <code>{stage}</code>\n"
              f"{reason[:600]}\n{log_url}")
