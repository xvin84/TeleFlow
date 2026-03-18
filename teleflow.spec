# -*- mode: python ; coding: utf-8 -*-
"""
TeleFlow PyInstaller spec.

Build (from project root):
  uv run pyinstaller teleflow.spec --clean

Or via GitHub Actions on tag push (see .github/workflows/build.yml).
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
SRC  = ROOT / "src" / "teleflow"

block_cipher = None

a = Analysis(
    [str(ROOT / "src" / "teleflow" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        # Locale files
        (str(SRC / "i18n" / "locales"), "teleflow/i18n/locales"),
    ],
    hiddenimports=[
        # Telethon crypto backends
        "telethon.crypto",
        "telethon.crypto.authkey",
        # APScheduler triggers
        "apscheduler.triggers.cron",
        "apscheduler.triggers.date",
        "apscheduler.triggers.interval",
        "apscheduler.datastores.sqlalchemy",
        # SQLAlchemy async
        "sqlalchemy.dialects.sqlite",
        "aiosqlite",
        # PyQt6 platform plugins
        "PyQt6.QtWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        # Optional: plyer and pystray
        "plyer",
        "plyer.platforms",
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="TeleFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # No console window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows icon (add teleflow.ico to project root if you have one)
    # icon="teleflow.ico",
)
