"""Generate thumbnail per clip dari frame sumber (sebelum overlay).

Input : info.json, clip (start_sec, text, clip_id)
Output: output_clips/<clip_id>_thumb.jpg  (1080x1920, teks KAPITAL)
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from . import common

OUT_DIR = Path("output_clips")
TMP_DIR = Path("build_clips/tmp")

PALETTE = {
    "penasaran": ((255, 215, 0), (204, 153, 0)),
    "misterius": ((255, 140, 0), (204, 102, 0)),
    "teknologi": ((0, 229, 255), (0, 136, 170)),
    "inspiratif": ((255, 255, 255), (230, 57, 70)),
    "santai_edukatif": ((255, 255, 255), (42, 157, 143)),
    "serius": ((255, 255, 255), (157, 2, 8)),
    "netral": ((255, 255, 255), (52, 58, 64)),
}


def _pick_text(clip: dict, max_words: int = 7) -> str:
    text = re.sub(r"[^\w\s?!]", " ", clip.get("text", "")).strip()
    words = text.split()
    if len(words) > max_words:
        words = words[:max_words]
    return " ".join(words).upper()


def _extract_frame(info: dict, clip: dict, dest: Path) -> None:
    t = float(clip["start_sec"]) + 1.0
    common.run([
        common.ffmpeg_bin(), "-y",
        "-ss", f"{t:.2f}", "-i", info["video_path"],
        "-vframes", "1", "-q:v", "2",
        str(dest),
    ], timeout=120, label="extract-thumb")


def _compose(src: Path, text: str, out: Path, mood: str) -> None:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: PLC0415

    W, H = 1080, 1920
    img = Image.open(src).convert("RGB")
    # reframe vertical
    iw, ih = img.size
    target_ratio = W / H
    if iw / ih < target_ratio:
        new_h = int(iw / target_ratio)
        img = img.resize((iw, new_h))
    else:
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih)).resize((W, H))
    # zoom 1.15
    zw = int(W / 1.15)
    zh = int(H / 1.15)
    img = img.resize((zw, zh)).resize((W, H))
    # kontras + saturasi
    from PIL import ImageEnhance
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Color(img).enhance(1.2)

    # gradient gelap dari bawah
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        if y > H * 0.45:
            grad.putpixel((0, y), int(200 * (y - H * 0.45) / (H * 0.55)))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, grad.resize((W, H)).filter(ImageFilter.GaussianBlur(4)))

    draw = ImageDraw.Draw(img)
    text_rgb, border_rgb = PALETTE.get(mood, PALETTE["netral"])

    # teks
    try:
        font = ImageFont.truetype("assets/fonts/Poppins-Bold.ttf", 110)
        sig_font = ImageFont.truetype("assets/fonts/Poppins-Bold.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
        sig_font = font

    lines = _wrap(draw, text, font, W - 140)
    lh = 130
    y = H - 200 - lh * (len(lines) - 1)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((70 + 4, y + 6), line, fill=(0, 0, 0), font=font)
        draw.text((70, y), line, fill=text_rgb, font=font)
        y += lh

    # border tipis kiri bawah
    draw.rectangle([60, H - 220 - lh * (len(lines) - 1) - 30, 70,
                    H - 200 - lh * (len(lines) - 1) + lh * len(lines)],
                   fill=border_rgb)

    # signature kiri atas
    draw.rectangle([40, 40, 260, 100], fill=(0, 0, 0))
    draw.text((55, 52), "Apaiya?", fill=(255, 255, 255), font=sig_font)

    img.save(out, "JPEG", quality=88)
    common.info("thumb_saved", path=str(out))


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] > max_width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [text]


def generate(info: dict, clip: dict, mood: str = "penasaran") -> str:
    common.ensure_dir(OUT_DIR)
    common.ensure_dir(TMP_DIR)
    clip_id = clip["clip_id"]
    raw = TMP_DIR / f"{clip_id}_thumb_src.jpg"
    out = OUT_DIR / f"{clip_id}_thumb.jpg"
    _extract_frame(info, clip, raw)
    _compose(raw, _pick_text(clip), out, mood)
    return str(out)


def _main() -> None:
    clip_id = common.get_env("CLIP_ID", required=True)
    info = common.read_json("build_clips/source/info.json")
    clips = common.read_json("build_clips/selected_clips.json") or []
    clip = next((c for c in clips if c["clip_id"] == clip_id), None)
    if not clip:
        common.fail(f"clip_id {clip_id} tidak ada")
    print(generate(info, clip))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"clip_thumbnail crash: {type(exc).__name__}: {exc}")
