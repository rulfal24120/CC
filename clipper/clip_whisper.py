"""Transkripsi word-level audio video sumber dengan faster-whisper INT8.

Input : build_clips/source/video.mp4
Output: build_clips/transcript.json

Perbaikan kecepatan vs openai-whisper:
- Engine: faster-whisper (CTranslate2) menggantikan openai-whisper (PyTorch).
  Di CPU, INT8 ~4-7x lebih cepat untuk akurasi setara.
- vad_filter=True: lewati segmen hening, hemat 5-15%.
- beam_size=3: sedikit lebih cepat dari default 5, kualitas hampir sama.
- Model Systran/faster-whisper-small (~150 MB) vs openai 461 MB.

Output tetap kompatibel: {"language", "duration", "words": [{start, end, text}]}.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import common

SRC_AUDIO = Path("build_clips/source/audio.wav")
TRANSCRIPT = Path("build_clips/transcript.json")
MODEL_SIZE = "small"
COMPUTE_TYPE = "int8"
BEAM_SIZE = 3


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


def _load_model():
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except ImportError as exc:
        common.fail(
            f"faster-whisper tidak terpasang: {exc}. "
            "Tambahkan `faster-whisper>=1.0.3` ke requirements_clips.txt"
        )
    common.info("whisper_load", engine="faster-whisper",
                model=MODEL_SIZE, compute_type=COMPUTE_TYPE)
    return WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)


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
    model = _load_model()

    common.info("whisper_transcribe_start", audio=str(audio_path),
                beam=BEAM_SIZE, vad=True)
    segments, info_obj = model.transcribe(
        str(audio_path),
        language="id",
        beam_size=BEAM_SIZE,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
    )

    words: list[dict] = []
    last_end = 0.0
    for seg in segments:
        for w in (seg.words or []):
            text = (w.word or "").strip()
            if not text:
                continue
            start = float(w.start)
            end = float(w.end)
            if end <= start:
                continue
            words.append({"start": start, "end": end, "text": text})
            last_end = end

    if not words:
        common.fail("whisper tidak menghasilkan kata apa pun")

    payload = {
        "language": getattr(info_obj, "language", "id") or "id",
        "duration": float(getattr(info_obj, "duration", 0.0) or last_end),
        "words": words,
    }
    common.write_json(TRANSCRIPT, payload)
    common.info("whisper_ok", words=len(words),
                duration=f"{payload['duration']:.1f}s",
                engine="faster-whisper")
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
