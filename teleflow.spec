# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for TeleFlow.

Regenerate from scratch (only if you need to reset):
    uv run pyinstaller --name TeleFlow --onefile \
        --add-data "src/teleflow/i18n/locales:teleflow/i18n/locales" \
        src/teleflow/__main__.py
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules  # noqa: F821

ROOT = Path(SPECPATH)  # noqa: F821  (SPECPATH is injected by PyInstaller)

# ── collect_all: grabs binaries + datas + hiddenimports for dynamic packages ──
# These packages use runtime imports that static analysis misses.

_qasync       = collect_all("qasync")
_anyio        = collect_all("anyio")
_apscheduler  = collect_all("apscheduler")
_telethon     = collect_all("telethon")
_plyer        = collect_all("plyer")
_pystray      = collect_all("pystray")
_sqlalchemy   = collect_all("sqlalchemy")

def _merge(*collected):
    datas, binaries, hiddenimports = [], [], []
    for d, b, h in collected:
        datas      += d
        binaries   += b
        hiddenimports += h
    return datas, binaries, hiddenimports

extra_datas, extra_binaries, extra_hidden = _merge(
    _qasync, _anyio, _apscheduler, _telethon,
    _plyer, _pystray, _sqlalchemy,
)

a = Analysis(
    [str(ROOT / "src" / "teleflow" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=extra_binaries,
    datas=[
        # Locale JSON files
        (str(ROOT / "src" / "teleflow" / "i18n" / "locales"), "teleflow/i18n/locales"),
        *extra_datas,
    ],
    hiddenimports=[
        *extra_hidden,
        # anyio backends
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        # cryptography
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.rsa",
        "cryptography.hazmat.bindings._rust",
        # PIL
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        # aiosqlite
        "aiosqlite",
        # bcrypt
        "bcrypt",
        # sqlalchemy dialects
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.ext.asyncio",
        # sniffio (anyio dependency)
        "sniffio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "mypy",
        "ruff",
        "tkinter",
        "_tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TeleFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX disabled: known issues on Linux
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no terminal window on Windows/Linux
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico" if (ROOT / "assets" / "icon.ico").exists() else None,
)
