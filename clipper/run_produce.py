"""Orkestrasi produce: fetch → whisper → select → render paralel →
thumbnail → pool → notify (ringkasan + video).

Render dan thumbnail dijalankan paralel (ThreadPoolExecutor) untuk 3 clip
sekaligus. Operasi file & state tetap sequential setelah render selesai,
jadi aman dari race condition.

Setelah ringkasan, tiap klip MP4 dikirim ke Telegram via sendVideo
(kecuali SEND_CLIP_VIDEOS=0). Kegagalan kirim video bersifat best-effort
dan tidak menggagalkan pipeline.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import (clip_notify, clip_renderer, clip_selector, clip_thumbnail,
               clip_whisper, common, fetch_source, state)

MAX_PARALLEL_RENDERS = 3


def _render_one(info: dict, clip: dict, transcript: dict, mood: str) -> dict:
    r = clip_renderer.render(info, clip, transcript)
    t = clip_thumbnail.generate(info, clip, mood=mood)
    return {
        **clip,
        "video_path": r["video_path"],
        "thumbnail_path": t,
        "source_url": info["source_url"],
        "channel": info["channel"],
    }


def main() -> None:
    source_url = common.get_env("SOURCE_URL", required=True)
    common.info("produce_start", url=source_url)
    info = fetch_source.fetch(source_url)
    transcript = clip_whisper.transcribe(info["video_path"])
    clips = clip_selector.select()
    if not clips:
        common.fail("tidak ada clip yang lolos gate kualitas")

    mood = common.get_env("BGM_MOOD", required=False, default="penasaran")
    max_workers = min(MAX_PARALLEL_RENDERS, len(clips))
    common.info("render_parallel_start", n=len(clips), workers=max_workers)

    rendered: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_render_one, info, clip, transcript, mood): clip
            for clip in clips
        }
        for fut in as_completed(futures):
            clip = futures[fut]
            try:
                merged = fut.result()
                rendered.append(merged)
                common.info("render_parallel_ok", clip_id=clip["clip_id"])
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                common.warn("render_clip_failed",
                            clip_id=clip["clip_id"], err=str(exc)[:200])

    if not rendered:
        common.fail("semua clip gagal dirender")

    order = {c["clip_id"]: i for i, c in enumerate(clips)}
    rendered.sort(key=lambda c: order.get(c["clip_id"], 999))

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
                f"{info['source_url']}|{clip['start_sec']}|{clip['end_sec']}"
            ),
            "title": clip["text"][:90],
            "status": "scheduled",
            "date": common.today_iso(),
        })

    # Ringkasan dulu (teks + thumbnail klip pertama).
    clip_notify.produce_summary(source_url, rendered)

    # Kirim video per klip (best-effort, bisa dimatikan via SEND_CLIP_VIDEOS=0).
    if common.get_env("SEND_CLIP_VIDEOS", required=False, default="1") != "0":
        try:
            clip_notify.send_clip_videos(rendered)
        except Exception as exc:  # noqa: BLE001
            common.warn("telegram_send_clips_failed",
                        err=type(exc).__name__, detail=str(exc)[:200])

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
