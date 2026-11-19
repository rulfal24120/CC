"""Pilih 3-5 segmen 40-60 dtk paling berpotensi viral.

Input : build_clips/transcript.json
Output: build_clips/selected_clips.json

Perbaikan utama (vs versi sebelumnya):
1. _build_sentences memakai transcript["segments"] jika tersedia; jika
   hanya ada "words" dengan tanda baca minim (khas Whisper Indonesia),
   pecah berdasarkan batas durasi/jumlah kata, bukan hanya tanda baca.
2. _chunk_long memecah kalimat yang terlalu panjang (> 15 dtk) supaya
   enumerasi kandidat selalu punya bahan.
3. _enumerate_with_fallback: kalau rentang env (MIN_CLIP_SEC..MAX_CLIP_SEC)
   menghasilkan 0 kandidat, longgarkan bertahap sebelum menyerah.
4. _gemini_score: fallback chain model (GEMINI_MODEL_CHAIN) + parser JSON
   toleran markdown fence.
5. _select_top: kalau tak ada yang lolos MIN_CLIP_SCORE, ambil top-N
   terbaik (bisa dimatikan dengan ALLOW_FALLBACK_SELECTION=0).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import common, state  # noqa: F401  (state dipertahankan untuk kompat)

TRANSCRIPT = Path("build_clips/transcript.json")
SELECTED = Path("build_clips/selected_clips.json")

SENT_END = re.compile(r"[.!?]+$")
QUESTION_WORDS = ("apa", "kenapa", "mengapa", "bagaimana", "siapa", "kapan", "di mana")
CONTRAST_WORDS = ("tapi", "padahal", "ternyata", "anehnya", "buktinya", "nyatanya", "justru")
EMOTION_WORDS = ("kaget", "gila", "wow", "wih", "luar biasa", "mengerikan", "menakjubkan",
                 "mengejutkan", "aneh", "seram")

MAX_SENT_SEC = 8.0
MAX_SENT_WORDS = 20
CHUNK_SEC = 15.0
DEFAULT_GEMINI_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]


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


# ---------------------------------------------------------------------------
# Pembentukan kalimat
# ---------------------------------------------------------------------------

def _chunk_long(sents: list[Sentence], max_len: float = CHUNK_SEC) -> list[Sentence]:
    """Pecah kalimat yang lebih panjang dari max_len dtk jadi beberapa bagian."""
    out: list[Sentence] = []
    for s in sents:
        dur = s.end - s.start
        if dur <= max_len or dur <= 0:
            out.append(s)
            continue
        words = s.text.split()
        if not words:
            out.append(s)
            continue
        n = int(dur / max_len) + 1
        per = max(1, len(words) // n)
        for i in range(n):
            a = i * per
            b = (i + 1) * per if i < n - 1 else len(words)
            text = " ".join(words[a:b])
            if not text:
                continue
            step = dur / n
            out.append(Sentence(s.start + i * step, s.start + (i + 1) * step, text))
    return out


def _build_sentences(transcript: dict) -> list[Sentence]:
    # Prioritas 1: segments (Whisper biasanya beri batas kalimat alami)
    segs = transcript.get("segments") or []
    if isinstance(segs, list) and segs:
        out: list[Sentence] = []
        for s in segs:
            try:
                a, b = float(s["start"]), float(s["end"])
            except (KeyError, TypeError, ValueError):
                continue
            t = str(s.get("text", "")).strip()
            if t:
                out.append(Sentence(a, b, t))
        if out:
            out = _chunk_long(out)
            common.info("sentences_built", source="segments+chunk", count=len(out))
            return out

    # Prioritas 2: words
    words = transcript.get("words") or []
    if not words:
        common.warn("sentences_built", source="none", note="words kosong")
        return []

    # Coba pecah berdasarkan tanda baca
    groups: list[list[dict]] = [[]]
    for w in words:
        groups[-1].append(w)
        if SENT_END.search(str(w.get("text", ""))):
            groups.append([])
    groups = [g for g in groups if g]

    if len(groups) > 5:
        out = []
        for g in groups:
            try:
                a, b = float(g[0]["start"]), float(g[-1]["end"])
            except (KeyError, TypeError, ValueError):
                continue
            t = " ".join(str(x.get("text", "")) for x in g)
            if t:
                out.append(Sentence(a, b, t))
        out = _chunk_long(out)
        common.info("sentences_built", source="words+punct+chunk", count=len(out))
        return out

    # Fallback: tanda baca minim -> pecah per durasi/jumlah kata
    common.warn(
        "sentences_built",
        source="words+duration",
        punct_groups=len(groups),
        note="tanda baca minim; fallback ke batas durasi/jumlah kata",
    )
    out_fb: list[Sentence] = []
    buf: list[dict] = []

    def flush() -> None:
        if not buf:
            return
        try:
            a = float(buf[0]["start"])
            b = float(buf[-1]["end"])
        except (KeyError, TypeError, ValueError):
            buf.clear()
            return
        t = " ".join(str(x.get("text", "")) for x in buf)
        if t:
            out_fb.append(Sentence(a, b, t))
        buf.clear()

    for w in words:
        buf.append(w)
        try:
            dur = float(buf[-1]["end"]) - float(buf[0]["start"])
        except (KeyError, TypeError, ValueError):
            dur = 0.0
        if dur >= MAX_SENT_SEC or len(buf) >= MAX_SENT_WORDS:
            flush()
    flush()
    out_fb = _chunk_long(out_fb)
    common.info("sentences_built", source="words+duration+chunk", count=len(out_fb))
    return out_fb


# ---------------------------------------------------------------------------
# Skor heuristik
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Enumerasi kandidat
# ---------------------------------------------------------------------------

def _enumerate_candidates(sents: list[Sentence], min_sec: int, max_sec: int) -> list[Candidate]:
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


def _enumerate_with_fallback(sents: list[Sentence]) -> list[Candidate]:
    base_min = common.get_env_int("MIN_CLIP_SEC", 40)
    base_max = common.get_env_int("MAX_CLIP_SEC", 60)
    ladder = [
        (base_min, base_max),
        (max(5, base_min // 2), max(base_max, base_max * 2)),
        (5, 180),
        (3, 99999),
    ]
    seen: set[tuple[int, int]] = set()
    for lo, hi in ladder:
        if (lo, hi) in seen:
            continue
        seen.add((lo, hi))
        cands = _enumerate_candidates(sents, lo, hi)
        common.info("candidates_try", min_sec=lo, max_sec=hi, count=len(cands))
        if cands:
            return cands
    return []


# ---------------------------------------------------------------------------
# Gemini scoring
# ---------------------------------------------------------------------------

def _gemini_chain() -> list[str]:
    primary = common.get_env("GEMINI_CLIP_MODEL", required=False, default="").strip()
    extra_raw = common.get_env("GEMINI_MODEL_CHAIN", required=False, default="").strip()
    extra = [m.strip() for m in extra_raw.split(",") if m.strip()]
    chain = ([primary] if primary else []) + extra + DEFAULT_GEMINI_CHAIN
    seen: set[str] = set()
    out: list[str] = []
    for m in chain:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _build_prompt(candidates: list[Candidate]) -> str:
    durs = [c.end - c.start for c in candidates]
    lo = min(durs) if durs else 0
    hi = max(durs) if durs else 0
    lines = [
        "Kamu memilih segmen video untuk dijadikan Reels/Shorts berpotensi viral.",
        f"Setiap kandidat berdurasi {lo:.0f}-{hi:.0f} detik. Nilai 0-10 berdasarkan:",
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


def _gemini_score(candidates: list[Candidate]) -> None:
    if not candidates:
        return
    api_key = common.get_env("GEMINI_API_KEY", required=True)
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        common.warn("gemini_skip", reason="requests tidak terpasang")
        return
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(candidates)}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    last_err: Exception | None = None
    for model in _gemini_chain():
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        common.info("gemini_try", model=model, n=len(candidates))
        try:
            r = requests.post(url, json=payload, timeout=90)
            r.raise_for_status()
            data = r.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(_strip_fences(raw))
            scores = {int(s["index"]): s for s in parsed.get("scores", [])}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            common.warn(
                "gemini_fail",
                model=model,
                err=type(exc).__name__,
                msg=str(exc)[:200],
            )
            continue
        for idx, s in scores.items():
            if 0 <= idx < len(candidates):
                candidates[idx].llm = float(s.get("score", 0))
                candidates[idx].reason = str(s.get("reason", ""))[:200]
        common.info("gemini_ok", model=model, scored=len(scores))
        return
    common.warn(
        "gemini_all_failed",
        chain=_gemini_chain(),
        last_err=type(last_err).__name__ if last_err else "none",
        msg=str(last_err)[:200] if last_err else "",
    )


# ---------------------------------------------------------------------------
# Seleksi akhir
# ---------------------------------------------------------------------------

def _select_top(candidates: list[Candidate]) -> list[Candidate]:
    min_score = common.get_env_float("MIN_CLIP_SCORE", 7.0)
    target = common.get_env_int("TARGET_CLIPS", 5)
    allow_fb = common.get_env(
        "ALLOW_FALLBACK_SELECTION", required=False, default="1"
    ).strip() != "0"

    for c in candidates:
        c.final = 0.5 * c.heuristic + 0.5 * c.llm if c.llm else c.heuristic
    candidates.sort(key=lambda c: c.final, reverse=True)

    def _add(pool: list[Candidate], threshold: float, n: int) -> list[Candidate]:
        out: list[Candidate] = []
        for c in pool:
            if c.final < threshold:
                continue
            if any(not (c.end <= x.start or c.start >= x.end) for x in out):
                continue
            out.append(c)
            if len(out) >= n:
                break
        return out

    chosen = _add(candidates, min_score, target)
    if chosen:
        common.info("selected_strict", count=len(chosen), min_score=min_score)
        return chosen

    if allow_fb and candidates:
        common.warn("selected_fallback", min_score=min_score, target=target)
        chosen = _add(candidates, 0.0, target)
        common.info("selected_fallback_done", count=len(chosen))
        return chosen

    return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def select() -> list[dict[str, Any]]:
    transcript = common.read_json(TRANSCRIPT)
    if not transcript:
        common.fail("transcript kosong; jalankan clip_whisper dulu")
    if not transcript.get("words") and not transcript.get("segments"):
        common.fail("transcript tidak punya words/segments")

    sents = _build_sentences(transcript)
    if not sents:
        common.fail("tidak ada kalimat terbentuk dari transcript")

    candidates = _enumerate_with_fallback(sents)
    common.info("candidates", count=len(candidates))
    if not candidates:
        common.fail("tidak ada kandidat segmen setelah semua fallback")

    candidates.sort(key=lambda c: c.heuristic, reverse=True)
    _gemini_score(candidates[:20])
    chosen = _select_top(candidates)
    if not chosen:
        common.fail("tidak ada segmen lolos threshold skor")

    chosen.sort(key=lambda c: c.start)
    result: list[dict[str, Any]] = []
    for i, c in enumerate(chosen, 1):
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
