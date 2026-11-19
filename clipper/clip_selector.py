"""Pilih 3-5 segmen 40-60 dtk paling berpotensi viral.

Input : build_clips/transcript.json
Output: build_clips/selected_clips.json
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import common, state

TRANSCRIPT = Path("build_clips/transcript.json")
SELECTED = Path("build_clips/selected_clips.json")

SENT_END = re.compile(r"[.!?]+$")
QUESTION_WORDS = ("apa", "kenapa", "mengapa", "bagaimana", "siapa", "kapan", "di mana")
CONTRAST_WORDS = ("tapi", "padahal", "ternyata", "anehnya", "buktinya", "nyatanya", "justru")
EMOTION_WORDS = ("kaget", "gila", "wow", "wih", "luar biasa", "mengerikan", "menakjubkan",
                 "mengejutkan", "aneh", "seram")


@dataclass
class Sentence:
    start: float
    end: float
    text: str


@dataclass
class Candidate:
    start: float
    end: float
    text: str
    heuristic: float
    llm: float = 0.0
    final: float = 0.0
    reason: str = ""
    sentences: list[Sentence] = field(default_factory=list)


def _build_sentences(words: list[dict]) -> list[Sentence]:
    sents: list[list[dict]] = [[]]
    for w in words:
        sents[-1].append(w)
        if SENT_END.search(w["text"]):
            sents.append([])
    out: list[Sentence] = []
    for group in sents:
        if not group:
            continue
        out.append(Sentence(
            start=group[0]["start"], end=group[-1]["end"],
            text=" ".join(w["text"] for w in group),
        ))
    return out


def _heuristic_score(text: str) -> float:
    low = text.lower()
    score = 0.0
    if "?" in text:
        score += 2.0
    if re.search(r"\d", text):
        score += 1.5
    if any(w in low for w in CONTRAST_WORDS):
        score += 1.5
    if any(w in low for w in EMOTION_WORDS):
        score += 1.0
    if any(low.startswith(w) for w in QUESTION_WORDS + CONTRAST_WORDS):
        score += 1.0
    return min(score, 10.0)


def _enumerate_candidates(sents: list[Sentence]) -> list[Candidate]:
    min_sec = common.get_env_int("MIN_CLIP_SEC", 40)
    max_sec = common.get_env_int("MAX_CLIP_SEC", 60)
    out: list[Candidate] = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            start, end = sents[i].start, sents[j].end
            dur = end - start
            if dur < min_sec:
                continue
            if dur > max_sec:
                break
            text = " ".join(s.text for s in sents[i:j + 1])
            out.append(Candidate(
                start=start, end=end, text=text,
                heuristic=_heuristic_score(text),
                sentences=sents[i:j + 1],
            ))
    return out


def _gemini_score(candidates: list[Candidate]) -> None:
    if not candidates:
        return
    api_key = common.get_env("GEMINI_API_KEY", required=True)
    model = common.get_env("GEMINI_CLIP_MODEL", required=False, default="gemini-2.5-flash")
    import requests  # noqa: PLC0415
    payload = {
        "contents": [{
            "parts": [{"text": _build_prompt(candidates)}],
        }],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    common.info("gemini_score_start", model=model, n=len(candidates))
    try:
        r = requests.post(url, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw)
        scores = {int(s["index"]): s for s in parsed.get("scores", [])}
    except Exception as exc:  # noqa: BLE001
        common.warn("gemini_score_failed", err=type(exc).__name__, msg=str(exc)[:200])
        return
    for idx, s in scores.items():
        if 0 <= idx < len(candidates):
            candidates[idx].llm = float(s.get("score", 0))
            candidates[idx].reason = str(s.get("reason", ""))[:200]
    common.info("gemini_score_ok", scored=len(scores))


def _build_prompt(candidates: list[Candidate]) -> str:
    lines = [
        "Kamu memilih segmen video untuk dijadikan Reels/Shorts berpotensi viral.",
        "Setiap kandidat adalah 40-60 detik. Nilai 0-10 berdasarkan:",
        "- Hook menarik di 3 detik pertama",
        "- Ada pertanyaan / kontradiksi / angka / emosi",
        "- Bisa berdiri sendiri tanpa konteks sebelumnya",
        "- Bukan bagian iklan atau promosi",
        "",
        "Kandidat:",
    ]
    for i, c in enumerate(candidates):
        snippet = c.text[:280].replace("\n", " ")
        lines.append(f"[{i}] ({c.end - c.start:.1f}s) {snippet}")
    lines += [
        "",
        'Balas JSON murni: {"scores": [{"index": 0, "score": 8.5, "reason": "..."}]}',
    ]
    return "\n".join(lines)


def _select_top(candidates: list[Candidate]) -> list[Candidate]:
    min_score = common.get_env_float("MIN_CLIP_SCORE", 7.0)
    target = common.get_env_int("TARGET_CLIPS", 5)
    for c in candidates:
        c.final = 0.5 * c.heuristic + 0.5 * c.llm if c.llm else c.heuristic
    candidates.sort(key=lambda c: c.final, reverse=True)
    chosen: list[Candidate] = []
    for c in candidates:
        if c.final < min_score:
            continue
        if any(not (c.end <= x.start or c.start >= x.end) for x in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= target:
            break
    return chosen


def select() -> list[dict[str, Any]]:
    transcript = common.read_json(TRANSCRIPT)
    if not transcript or not transcript.get("words"):
        common.fail("transcript kosong; jalankan clip_whisper dulu")
    sents = _build_sentences(transcript["words"])
    candidates = _enumerate_candidates(sents)
    common.info("candidates", count=len(candidates))
    if not candidates:
        common.fail("tidak ada kandidat segmen 40-60 dtk")
    # Kirim top 20 heuristic ke LLM untuk hemat token
    candidates.sort(key=lambda c: c.heuristic, reverse=True)
    _gemini_score(candidates[:20])
    chosen = _select_top(candidates)
    if not chosen:
        common.fail("tidak ada segmen lolos threshold skor")
    chosen.sort(key=lambda c: c.start)
    result = []
    for i, c in enumerate(chosen, 1):
        words = []
        for s in c.sentences:
            pass
        result.append({
            "clip_id": f"clip_{common.now_iso().replace('-', '').replace(':', '')[:15]}_{i:02d}",
            "start_sec": round(c.start, 2),
            "end_sec": round(c.end, 2),
            "duration_sec": round(c.end - c.start, 2),
            "text": c.text,
            "heuristic_score": round(c.heuristic, 2),
            "llm_score": round(c.llm, 2),
            "final_score": round(c.final, 2),
            "reason": c.reason,
        })
    common.write_json(SELECTED, result)
    common.info("selected", n=len(result),
                scores=[r["final_score"] for r in result])
    return result


def _main() -> None:
    print(json.dumps(select(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        _main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        common.fail(f"clip_selector crash: {type(exc).__name__}: {exc}")
