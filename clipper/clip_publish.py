"""Upload video + thumbnail ke Zernio (YouTube private + Facebook reel).

Tidak dipakai di trial. Disiapkan untuk diaktifkan nanti.
Input : satu entri pool (clip) + info
Output: {"youtube_url": "...", "facebook_url": "..."}
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import common

ZER_BASE = "https://api.zernio.com"
POLL_MAX = 36
POLL_INTERVAL = 5


def _desc(clip: dict, info: dict) -> str:
    start = int(clip["start_sec"])
    mm, ss = divmod(start, 60)
    src_channel = info.get("channel") or "sumber asli"
    src_url = info.get("source_url", "")
    return (
        f"{clip.get('text', '')[:200]}\n\n"
        f"Sumber: {src_channel} ({src_url}) mulai menit {mm}:{ss:02d}\n\n"
        f"#apaiya #edukasi #shorts"
    )


def _post(path: str, payload: dict, api_key: str) -> dict:
    import requests  # noqa: PLC0415
    r = requests.post(f"{ZER_BASE}{path}", json=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }, timeout=60)
    r.raise_for_status()
    return r.json()


def _put_file(url: str, path: Path, content_type: str) -> None:
    import requests  # noqa: PLC0415
    with path.open("rb") as f:
        r = requests.put(url, data=f,
                         headers={"Content-Type": content_type}, timeout=600)
    r.raise_for_status()


def _poll_status(post_id: str, api_key: str) -> dict:
    import requests  # noqa: PLC0415
    for i in range(POLL_MAX):
        try:
            r = requests.get(f"{ZER_BASE}/v1/posts/{post_id}",
                             headers={"Authorization": f"Bearer {api_key}"},
                             timeout=30)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") in ("published", "failed", "partial"):
                    return data
        except Exception as exc:  # noqa: BLE001
            common.warn("poll_err", attempt=i + 1, err=str(exc)[:120])
        time.sleep(POLL_INTERVAL)
    return {"status": "pending"}


def publish(clip: dict, info: dict) -> dict[str, Any]:
    api_key = common.get_env("ZER_API_KEY", required=True)
    yt_id = common.get_env("ZER_ID_YT", required=True)
    fb_id = common.get_env("ZER_ID_FB", required=True)

    video_path = Path(clip["video_path"])
    thumb_path = Path(clip.get("thumbnail_path", ""))
    if not video_path.is_file():
        raise RuntimeError(f"video tidak ada: {video_path}")

    common.info("publish_presign", clip_id=clip["clip_id"])
    presign = _post("/v1/media/presign", {
        "filename": video_path.name,
        "contentType": "video/mp4",
    }, api_key)
    upload_url = presign.get("uploadUrl")
    public_url = presign.get("publicUrl")
    if not upload_url or not public_url:
        raise RuntimeError(f"presign response invalid: {presign}")

    common.info("publish_upload", clip_id=clip["clip_id"])
    _put_file(upload_url, video_path, "video/mp4")

    thumb_url = None
    if thumb_path.is_file():
        try:
            tp = _post("/v1/media/presign", {
                "filename": thumb_path.name, "contentType": "image/jpeg",
            }, api_key)
            _put_file(tp["uploadUrl"], thumb_path, "image/jpeg")
            thumb_url = tp.get("publicUrl")
        except Exception as exc:  # noqa: BLE001
            common.warn("thumb_upload_fail", err=str(exc)[:200])

    body: dict[str, Any] = {
        "platforms": [
            {"platform": "youtube", "accountId": yt_id,
             "options": {"visibility": "private", "categoryId": 27}},
            {"platform": "facebook", "accountId": fb_id,
             "options": {"contentType": "reel"}},
        ],
        "media": [{"url": public_url, "type": "video"}],
        "caption": _desc(clip, info),
    }
    if thumb_url:
        body["thumbnail"] = {"url": thumb_url}

    common.info("publish_create", clip_id=clip["clip_id"])
    post = _post("/v1/posts", body, api_key)
    post_id = post.get("id") or post.get("postId")
    if not post_id:
        raise RuntimeError(f"create post response invalid: {post}")

    final = _poll_status(post_id, api_key)
    urls = {"youtube_url": "", "facebook_url": ""}
    for p in final.get("platforms", []) or final.get("results", []) or []:
        name = (p.get("platform") or "").lower()
        if name == "youtube":
            urls["youtube_url"] = p.get("url") or p.get("postUrl") or ""
        elif name == "facebook":
            urls["facebook_url"] = p.get("url") or p.get("postUrl") or ""
    if final.get("status") == "pending":
        common.warn("publish_pending", post_id=post_id,
                    note="FB kemungkinan selesai di sisi Zernio")
    common.info("publish_ok", clip_id=clip["clip_id"],
                yt=bool(urls["youtube_url"]), fb=bool(urls["facebook_url"]))
    return {**urls, "post_id": post_id,
            "status": final.get("status", "unknown")}


def _main() -> None:
    clip_id = common.get_env("CLIP_ID", required=True)
    from . import state  # noqa: PLC0415
    clip = next((c for c in state.load_pool() if c["clip_id"] == clip_id), None)
    if not clip:
        common.fail(f"clip_id {clip_id} tidak ada di pool")
    info = common.read_json("build_clips/source/info.json") or {}
    print(json.dumps(publish(clip, info), indent=2))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"clip_publish crash: {type(exc).__name__}: {exc}")
