"""Notifikasi Telegram (teks + thumbnail opsional)."""
from __future__ import annotations

import json
from pathlib import Path

from . import common

TG = "https://api.telegram.org"


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


def produce_summary(source_url: str, clips: list[dict]) -> None:
    lines = [f"<b>Apaiya? Clipper</b>",
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
