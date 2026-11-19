"""Render satu clip: cut, reframe vertikal, subtitle word-group, watermark.

Input : info.json, transcript.json, satu entri selected_clips.json
Output: output_clips/<clip_id>_master.mp4
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import common

OUT_DIR = Path("output_clips")
TMP_DIR = Path("build_clips/tmp")
SENT_END = re.compile(r"[.!?]+$")
WORDS_PER_GROUP = 3


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _group_words(words: list[dict], start: float, end: float) -> list[list[dict]]:
    """Ambil kata di [start, end], kelompokkan 3 kata, break di tanda baca."""
    inside = [w for w in words if w["end"] > start and w["start"] < end]
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in inside:
        cur.append(w)
        if SENT_END.search(w["text"]) or len(cur) >= WORDS_PER_GROUP:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _ass_time(sec: float) -> str:
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _build_ass(groups: list[list[dict]], start: float, duration: float,
               font_name: str) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,{font_name},70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,3,1,2,50,50,220,1
Style: Watermark,{font_name},40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,2,1,2,40,40,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    events.append(
        f"Dialogue: 0,{_ass_time(0)},{_ass_time(duration)},Watermark,,0,0,0,,Apaiya?"
    )
    for g in groups:
        s = max(0.0, g[0]["start"] - start)
        e = max(0.0, g[-1]["end"] - start) + 0.05
        if e <= s:
            continue
        text = " ".join(w["text"] for w in g).strip()
        if not text:
            continue
        events.append(
            f"Dialogue: 1,{_ass_time(s)},{_ass_time(e)},Subtitle,,0,0,0,,"
            f"{_escape_ass(text)}"
        )
    return header + "\n".join(events) + "\n"


def _find_font() -> str:
    for candidate in ("assets/fonts/Poppins-Bold.ttf",
                      "assets/fonts/Poppins-Regular.ttf"):
        if Path(candidate).is_file():
            return "Poppins"
    common.warn("font_missing", note="pakai fallback sans-serif")
    return "Sans"


def render(info: dict, clip: dict, transcript: dict) -> dict[str, Any]:
    common.ensure_dir(OUT_DIR)
    common.ensure_dir(TMP_DIR)
    clip_id = clip["clip_id"]
    start, end = float(clip["start_sec"]), float(clip["end_sec"])
    duration = end - start
    if duration <= 0:
        common.fail(f"durasi clip invalid: {clip_id}")
    groups = _group_words(transcript["words"], start, end)
    if not groups:
        common.fail(f"tidak ada kata dalam clip {clip_id}")
    font_name = _find_font()
    ass_path = TMP_DIR / f"{clip_id}.ass"
    ass_path.write_text(_build_ass(groups, start, duration, font_name), encoding="utf-8")
    out_path = OUT_DIR / f"{clip_id}_master.mp4"
    if out_path.is_file() and out_path.stat().st_size > 0:
        common.info("render_cache", clip_id=clip_id, path=str(out_path))
        return {"video_path": str(out_path)}

    filter_complex = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=28[bgblur];"
        "[fg]scale=1080:-2:force_original_aspect_ratio=decrease[fgscaled];"
        "[bgblur][fgscaled]overlay=(W-w)/2:(H-h)/2,"
        f"ass={ass_path.as_posix()}[vout]"
    )
    cmd = [
        common.ffmpeg_bin(), "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", info["video_path"],
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out_path),
    ]
    common.info("render_start", clip_id=clip_id, start=start, end=end)
    common.run(cmd, timeout=1200, label=f"render-{clip_id}")
    if not out_path.is_file():
        common.fail(f"render {clip_id} tidak menghasilkan file")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    common.info("render_ok", clip_id=clip_id, size_mb=round(size_mb, 2))
    return {"video_path": str(out_path)}


def _main() -> None:
    clip_id = common.get_env("CLIP_ID", required=True)
    info = common.read_json("build_clips/source/info.json")
    transcript = common.read_json("build_clips/transcript.json")
    clips = common.read_json("build_clips/selected_clips.json") or []
    clip = next((c for c in clips if c["clip_id"] == clip_id), None)
    if not clip:
        common.fail(f"clip_id {clip_id} tidak ada di selected_clips.json")
    print(json.dumps(render(info, clip, transcript), indent=2))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"clip_renderer crash: {type(exc).__name__}: {exc}")
