"""Transkripsi word-level audio video sumber dengan Whisper small.

Input : build_clips/source/video.mp4
Output: build_clips/transcript.json
"""

from __future__ import annotations

import json
from pathlib import Path

from . import common

SRC_AUDIO = Path("build_clips/source/audio.wav")
TRANSCRIPT = Path("build_clips/transcript.json")


def _extract_audio(video_path: Path) -> Path:
    if SRC_AUDIO.is_file() and SRC_AUDIO.stat().st_size > 0:
        common.info("whisper_audio_cache", path=str(SRC_AUDIO))
        return SRC_AUDIO
    common.ensure_dir(SRC_AUDIO.parent)
    common.run([
        common.ffmpeg_bin(), "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(SRC_AUDIO),
    ], timeout=600, label="ffmpeg-audio")
    return SRC_AUDIO


def transcribe(video_path: str | Path) -> dict:
    video_path = Path(video_path)
    if not video_path.is_file():
        common.fail(f"video sumber tidak ada: {video_path}")
    if TRANSCRIPT.is_file():
        cached = common.read_json(TRANSCRIPT)
        if cached and cached.get("words"):
            common.info("whisper_cache", words=len(cached["words"]))
            return cached

    audio_path = _extract_audio(video_path)
    common.info("whisper_load", model="small")
    try:
        import whisper  # noqa: PLC0415
    except ImportError as exc:
        common.fail(f"openai-whisper tidak terpasang: {exc}")

    model = whisper.load_model("small")
    common.info("whisper_transcribe_start", audio=str(audio_path))
    result = model.transcribe(
        str(audio_path), language="id", word_timestamps=True, verbose=False,
    )
    words = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []) or []:
            text = (w.get("word") or "").strip()
            if not text:
                continue
            words.append({
                "start": float(w["start"]),
                "end": float(w["end"]),
                "text": text,
            })
    if not words:
        common.fail("whisper tidak menghasilkan kata apa pun")
    payload = {
        "language": result.get("language", "id"),
        "duration": float(result.get("duration") or words[-1]["end"]),
        "words": words,
    }
    common.write_json(TRANSCRIPT, payload)
    common.info("whisper_ok", words=len(words), duration=f"{payload['duration']:.1f}s")
    return payload


def _main() -> None:
    info = common.read_json("build_clips/source/info.json")
    if not info or not info.get("video_path"):
        common.fail("jalankan fetch_source dulu")
    data = transcribe(info["video_path"])
    print(json.dumps({"words": len(data["words"]), "duration": data["duration"]}))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"clip_whisper crash: {type(exc).__name__}: {exc}")
