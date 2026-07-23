# PyInstaller spec for dcad. Must be built ON WINDOWS (run
# `pyinstaller dcad.spec` from a Windows machine/venv) -- OCCT and Qt are
# compiled native binaries, so a build only produces an executable for the
# OS it was built on. See README.md "Packaging as an executable".
#
# Usage (from an activated venv with requirements.txt + pyinstaller installed):
#   pyinstaller dcad.spec
# Output: dist\dcad\dcad.exe (a folder build -- keeps startup fast; see
# README for the single-file --onefile tradeoff).

from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files

block_cipher = None

# OCP loads most of its OCCT bindings as separate compiled submodules
# (OCP.TopoDS, OCP.BRepBuilderAPI, ...) rather than through one top-level
# import, so PyInstaller's static import scanner won't find them on its
# own -- collect_submodules pulls in every one explicitly. Likewise its
# .pyd/.dll files (the actual OCCT shared libraries) need collect_dynamic_libs
# rather than relying on auto-detection.
hidden_imports = collect_submodules("OCP") + collect_submodules("PySide6")
binaries = collect_dynamic_libs("OCP")
datas = collect_data_files("OCP")

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dcad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app: no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="dcad",
)
