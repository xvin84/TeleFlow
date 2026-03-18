# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for TeleFlow.

Generate a fresh spec (don't run in CI — use this committed file):
    uv run pyinstaller --name TeleFlow --onefile \
        --add-data "src/teleflow/i18n/locales:teleflow/i18n/locales" \
        src/teleflow/__main__.py
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821  (SPECPATH injected by PyInstaller)

a = Analysis(
    [str(ROOT / "src" / "teleflow" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        # Locale JSON files must be bundled
        (str(ROOT / "src" / "teleflow" / "i18n" / "locales"), "teleflow/i18n/locales"),
    ],
    hiddenimports=[
        # qasync hooks are sometimes missed
        "qasync",
        # APScheduler 4.x uses anyio; make sure executors are included
        "anyio",
        "anyio._backends._asyncio",
        "apscheduler",
        "apscheduler.schedulers.async_",
        "apscheduler.triggers.cron",
        "apscheduler.triggers.interval",
        "apscheduler.triggers.date",
        # Telethon crypto backends
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.rsa",
        # pystray backends (Windows uses win32, Linux uses xorg)
        "pystray._win32",
        "pystray._xorg",
        "pystray._darwin",
        # PIL used by pystray icon
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        # plyer notification backends
        "plyer.platforms.win.notification",
        "plyer.platforms.linux.notification",
        # aiosqlite / sqlalchemy async
        "aiosqlite",
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.ext.asyncio",
        # bcrypt
        "bcrypt",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Don't bundle test frameworks
        "pytest",
        "mypy",
        "ruff",
        # Avoid pulling in tkinter
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
    console=False,      # GUI app — no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows: embed an icon if present
    icon="assets/icon.ico" if (ROOT / "assets" / "icon.ico").exists() else None,
)
