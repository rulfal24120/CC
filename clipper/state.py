"""Manajemen state: publish_pool.json dan history_clips.json.

Trial: fungsi pool tidak dipakai oleh run_produce, hanya history untuk dedup.
Publish: fungsi pool dipakai oleh run_publish saat diaktifkan nanti.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import common

STATE_DIR = Path("state")
POOL_FILE = STATE_DIR / "publish_pool.json"
HISTORY_FILE = Path("history_clips.json")

PUBLISH_PER_DAY = 2
MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Publish pool (tidak dipakai di trial, disiapkan untuk publish nanti)
# ---------------------------------------------------------------------------

def load_pool() -> list[dict[str, Any]]:
    return common.read_json(POOL_FILE, default=[]) or []


def save_pool(pool: list[dict[str, Any]]) -> None:
    common.write_json(POOL_FILE, pool)


def allocate_slots(
    pool: list[dict[str, Any]],
    n: int,
    per_day: int = PUBLISH_PER_DAY,
    start_date: date | None = None,
) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter(
        c["scheduled_date"] for c in pool if c.get("status") == "scheduled"
    )
    d = start_date or date.today()
    slots: list[tuple[str, int]] = []
    while len(slots) < n:
        while counts[d.isoformat()] < per_day and len(slots) < n:
            slot_num = counts[d.isoformat()] + 1
            slots.append((d.isoformat(), slot_num))
            counts[d.isoformat()] += 1
        if len(slots) >= n:
            break
        d = d + timedelta(days=1)
    return slots


def add_clips_to_pool(clips: list[dict[str, Any]]) -> list[tuple[str, int]]:
    pool = load_pool()
    slots = allocate_slots(pool, len(clips))
    for clip, (date_iso, slot_num) in zip(clips, slots):
        clip = dict(clip)
        clip["status"] = "scheduled"
        clip["scheduled_date"] = date_iso
        clip["slot"] = slot_num
        clip["attempts"] = 0
        pool.append(clip)
        common.info("pool_added", clip_id=clip.get("clip_id"),
                    date=date_iso, slot=slot_num)
    save_pool(pool)
    return slots


def get_due_clips(current_slot: int, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    today_iso = today.isoformat()
    due = []
    for c in load_pool():
        if c.get("status") != "scheduled":
            continue
        if c.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        sd = c.get("scheduled_date", "9999-12-31")
        slot = int(c.get("slot", 99))
        if sd < today_iso or (sd == today_iso and slot <= current_slot):
            due.append(c)
    due.sort(key=lambda c: (c.get("scheduled_date", ""), c.get("slot", 99)))
    return due[:PUBLISH_PER_DAY]


def mark_published(clip_id: str, youtube_url: str, facebook_url: str) -> None:
    pool = load_pool()
    for c in pool:
        if c.get("clip_id") == clip_id:
            c["status"] = "published"
            c["youtube_url"] = youtube_url
            c["facebook_url"] = facebook_url
            c["published_at"] = common.now_iso()
    save_pool(pool)


def mark_failed(clip_id: str, reason: str) -> None:
    pool = load_pool()
    for c in pool:
        if c.get("clip_id") == clip_id:
            c["attempts"] = int(c.get("attempts", 0)) + 1
            c["last_error"] = reason[:500]
            if c["attempts"] >= MAX_ATTEMPTS:
                c["status"] = "failed"
                common.error("pool_failed_permanent", clip_id=clip_id,
                             reason=reason[:200])
    save_pool(pool)


def remove_from_pool(clip_id: str) -> None:
    pool = [c for c in load_pool() if c.get("clip_id") != clip_id]
    save_pool(pool)


# ---------------------------------------------------------------------------
# History (dipakai trial untuk dedup)
# ---------------------------------------------------------------------------

def load_history() -> list[dict[str, Any]]:
    return common.read_json(HISTORY_FILE, default=[]) or []


def append_history(entry: dict[str, Any]) -> None:
    history = load_history()
    history.append(entry)
    common.write_json(HISTORY_FILE, history)


def is_duplicate_hash(clip_hash: str) -> bool:
    for h in load_history():
        if h.get("clip_hash") == clip_hash:
            return True
    for c in load_pool():
        if c.get("clip_hash") == clip_hash and c.get("status") != "failed":
            return True
    return False


def is_duplicate_source(source_url: str, start_sec: float, end_sec: float) -> bool:
    for h in load_history():
        if h.get("source_url") != source_url:
            continue
        hs, he = h.get("start_sec", 0), h.get("end_sec", 0)
        if start_sec < he and end_sec > hs:
            return True
    return False
