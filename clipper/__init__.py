"""Paket mesin cliper Apaiya? — pipeline clip-repurposing.

Modul-modul di sini hanya dipakai oleh workflow clip_*.yml.
Pipeline lama di scripts/ tidak disentuh.

Kompatibilitas gdown
--------------------
gdown 6.0.0 menghapus keyword argument ``fuzzy`` dari ``gdown.download``.
Beberapa pemanggilan lama di package ini masih memakai
``gdown.download(url, output, fuzzy=True)``, sehingga muncul:

    TypeError: download() got an unexpected keyword argument 'fuzzy'

Shim di bawah ini membuat ``gdown.download`` toleran terhadap kwarg ``fuzzy``
baik di gdown 5.x maupun 6.x. Kalau versi gdown yang terpasang masih punya
parameter ``fuzzy``, shim tidak melakukan apa-apa. Kalau tidak ada, kwarg
``fuzzy`` dibuang secara diam-diam sebelum memanggil implementasi aslinya.
"""

from __future__ import annotations

import inspect as _inspect


def _install_gdown_fuzzy_shim() -> None:
    """Buat ``gdown.download`` toleran terhadap kwarg lama ``fuzzy``."""
    try:
        import gdown
    except Exception:
        # gdown belum ter-install; biarkan import gagal di pemanggil.
        return

    original = getattr(gdown, "download", None)
    if original is None or getattr(original, "_clipper_fuzzy_shim", False):
        # Tidak ada fungsi download, atau shim sudah terpasang.
        return

    try:
        sig = _inspect.signature(original)
    except (TypeError, ValueError):
        sig = None

    # Kalau signature gdown masih punya parameter 'fuzzy', tidak perlu shim.
    if sig is not None and "fuzzy" in sig.parameters:
        return

    def download(*args, **kwargs):
        # gdown 6.x menolak kwarg 'fuzzy' -> buang.
        kwargs.pop("fuzzy", None)
        return original(*args, **kwargs)

    # Metadata, supaya repr/log tetap mirip fungsi aslinya.
    download._clipper_fuzzy_shim = True  # type: ignore[attr-defined]
    try:
        download.__wrapped__ = original  # type: ignore[attr-defined]
    except Exception:
        pass
    download.__doc__ = getattr(original, "__doc__", None)
    download.__name__ = getattr(original, "__name__", "download")
    download.__module__ = getattr(original, "__module__", "gdown")

    gdown.download = download


_install_gdown_fuzzy_shim()

__version__ = "0.1.0"
