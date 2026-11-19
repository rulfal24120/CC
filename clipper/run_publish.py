"""Publish due clips (2/hari, 2 slot). Tidak dipakai di trial.

Aktifkan hanya setelah storage persisten (R2/S3) siap — lihat catatan di workflow.
"""

from __future__ import annotations

import json

from . import clip_notify, clip_publish, common, state


def main() -> None:
    slot = common.get_env_int("SLOT", 1)
    due = state.get_due_clips(slot)
    common.info("publish_due", slot=slot, n=len(due))
    if not due:
        return
    info = common.read_json("build_clips/source/info.json") or {}
    published: list[dict] = []
    for clip in due:
        try:
            result = clip_publish.publish(clip, info)
            state.mark_published(clip["clip_id"],
                                 result["youtube_url"], result["facebook_url"])
            state.append_history({
                "clip_id": clip["clip_id"],
                "source_url": clip.get("source_url", ""),
                "youtube_url": result["youtube_url"],
                "facebook_url": result["facebook_url"],
                "status": "published",
                "date": common.today_iso(),
            })
            clip_notify.send_text(
                f"<b>Published</b> <code>{clip['clip_id']}</code>\n"
                f"YouTube: {result['youtube_url'] or '-'}\n"
                f"Facebook: {result['facebook_url'] or '-'}"
            )
            published.append(result)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"
            common.error("publish_clip_failed", clip_id=clip["clip_id"],
                         err=reason)
            state.mark_failed(clip["clip_id"], reason)
            clip_notify.send_text(
                f"<b>Gagal publish</b> <code>{clip['clip_id']}</code>\n"
                f"{reason[:600]}"
            )
    print(json.dumps({"published": len(published)}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            clip_notify.fail_notification("publish", str(exc))
        except Exception:  # noqa: BLE001
            pass
        common.fail(f"run_publish crash: {type(exc).__name__}: {exc}")
