# PyInstaller spec for the Restriction Limits desktop binary.
#
# Build with:
#   pyinstaller packaging/RestrictionLimits.spec
#
# The spec assumes the React app has already been built into
# `frontend/dist/` (run `npm run build` there first).
# The static assets are bundled inside the .exe so a single file is
# enough to ship on user laptops.

# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH).parent

block_cipher = None

datas = []
ui_dist = ROOT / "frontend" / "dist"
if ui_dist.exists():
    datas.append((str(ui_dist), "frontend/dist"))

a = Analysis(
    [str(ROOT / "backend" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols",
        "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "openpyxl", "pandas",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "tkinter", "PyQt5"],
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
    name="RestrictionLimits",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico") if (ROOT / "packaging" / "icon.ico").exists() else None,
)
