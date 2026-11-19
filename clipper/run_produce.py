"""Orkestrasi produce: fetch → whisper → select → render → thumbnail → pool."""
from __future__ import annotations

import json

from . import (clip_notify, clip_renderer, clip_selector, clip_thumbnail,
               clip_whisper, common, fetch_source, state)


def main() -> None:
    source_url = common.get_env("SOURCE_URL", required=True)
    common.info("produce_start", url=source_url)
    info = fetch_source.fetch(source_url)
    transcript = clip_whisper.transcribe(info["video_path"])
    clips = clip_selector.select()
    if not clips:
        common.fail("tidak ada clip yang lolos gate kualitas")
    mood = common.get_env("BGM_MOOD", required=False, default="penasaran")
    rendered: list[dict] = []
    for clip in clips:
        try:
            r = clip_renderer.render(info, clip, transcript)
            t = clip_thumbnail.generate(info, clip, mood=mood)
            merged = {**clip,
                      "video_path": r["video_path"],
                      "thumbnail_path": t,
                      "source_url": info["source_url"],
                      "channel": info["channel"]}
            rendered.append(merged)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            common.warn("render_clip_failed", clip_id=clip["clip_id"],
                        err=str(exc)[:200])
    if not rendered:
        common.fail("semua clip gagal dirender")
    slots = state.add_clips_to_pool(rendered)
    for clip, (d, s) in zip(rendered, slots):
        clip["scheduled_date"] = d
        clip["slot"] = s
        state.append_history({
            "clip_id": clip["clip_id"],
            "source_url": info["source_url"],
            "channel": info["channel"],
            "start_sec": clip["start_sec"],
            "end_sec": clip["end_sec"],
            "clip_hash": common.sha256_str(
                f"{info['source_url']}|{clip['start_sec']}|{clip['end_sec']}"),
            "title": clip["text"][:90],
            "status": "scheduled",
            "date": common.today_iso(),
        })
    clip_notify.produce_summary(source_url, rendered)
    print(json.dumps({"queued": len(rendered), "slots": slots}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        try:
            clip_notify.fail_notification("produce", str(exc))
        except Exception:  # noqa: BLE001
            pass
        common.fail(f"run_produce crash: {type(exc).__name__}: {exc}")
