"""Utilitas bersama untuk mesin cliper Apaiya?.

Isi: logging, env, retry, subprocess runner, JSON I/O, hash, waktu.
Tidak ada dependency eksternal — hanya stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_MIN_LEVEL = _LEVELS.get(os.getenv("CLIP_LOG_LEVEL", "INFO").upper(), 20)


def log(level: str, msg: str, **fields: Any) -> None:
    """Cetak log terstruktur ke stdout. Format: [LEVEL] ISO_TS msg k=v ..."""
    if _LEVELS.get(level.upper(), 20) < _MIN_LEVEL:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extras = " ".join(f"{k}={v}" for k, v in fields.items())
    line = f"[{level.upper()}] {ts} {msg}"
    if extras:
        line += f" {extras}"
    print(line, flush=True)


def info(msg: str, **fields: Any) -> None:
    log("INFO", msg, **fields)


def warn(msg: str, **fields: Any) -> None:
    log("WARN", msg, **fields)


def error(msg: str, **fields: Any) -> None:
    log("ERROR", msg, **fields)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def get_env(name: str, required: bool = True, default: str | None = None) -> str:
    """Ambil env var. Kalau required dan kosong → exit 1 dengan pesan jelas."""
    val = os.getenv(name, default)
    if required and (val is None or val.strip() == ""):
        error("env_missing", name=name)
        sys.exit(1)
    return val if val is not None else ""


def get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        warn("env_bad_int", name=name, raw=raw, using=default)
        return default


def get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        warn("env_bad_float", name=name, raw=raw, using=default)
        return default


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def retry(
    attempts: int = 3,
    delays: Iterable[float] = (8, 16, 32),
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    label: str = "call",
) -> Callable:
    """Decorator retry dengan delay bertingkat. Delay dipakai berurutan."""
    delay_list = list(delays)

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001
                    last_exc = exc
                    if i == attempts - 1:
                        break
                    delay = delay_list[i] if i < len(delay_list) else delay_list[-1]
                    warn(
                        "retry",
                        label=label,
                        attempt=i + 1,
                        total=attempts,
                        delay=delay,
                        err=type(exc).__name__,
                        msg=str(exc)[:200],
                    )
                    time.sleep(delay)
            error("retry_exhausted", label=label, attempts=attempts, err=repr(last_exc))
            raise last_exc  # type: ignore[misc]
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# Subprocess
# ---------------------------------------------------------------------------

def run(
    cmd: list[str],
    cwd: str | Path | None = None,
    check: bool = True,
    timeout: int | None = None,
    label: str = "",
) -> subprocess.CompletedProcess:
    """Jalankan perintah, log apa yang dicoba dan hasilnya."""
    info("run", label=label or cmd[0], cmd=" ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True,
            text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        error("run_not_found", label=label, cmd=cmd[0], err=str(exc))
        raise
    except subprocess.TimeoutExpired as exc:
        error("run_timeout", label=label, timeout=timeout)
        raise exc
    if proc.stdout.strip():
        print(proc.stdout.strip(), flush=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr, flush=True)
    if check and proc.returncode != 0:
        error("run_failed", label=label, code=proc.returncode, cmd=" ".join(cmd))
        raise RuntimeError(f"{label or cmd[0]} exited {proc.returncode}")
    info("run_ok", label=label or cmd[0], code=proc.returncode)
    return proc


def ffmpeg_bin() -> str:
    """Cek ffmpeg ada di PATH. Exit 1 kalau tidak ada."""
    for name in ("ffmpeg", "ffmpeg-static"):
        for path in os.getenv("PATH", "").split(os.pathsep):
            candidate = Path(path) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    error("ffmpeg_missing")
    sys.exit(1)


# ---------------------------------------------------------------------------
# File & JSON
# ---------------------------------------------------------------------------

def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        error("json_decode", path=str(p), err=str(exc))
        return default


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    info("json_written", path=str(p))


# ---------------------------------------------------------------------------
# Hash & waktu
# ---------------------------------------------------------------------------

def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fail(reason: str) -> None:
    """Tulis alasan gagal ke build_clips/failed_reason.txt lalu exit 1."""
    ensure_dir("build_clips")
    Path("build_clips/failed_reason.txt").write_text(reason, encoding="utf-8")
    error("fail", reason=reason[:200])
    sys.exit(1)
