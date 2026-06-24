from pathlib import Path

PROJECT_ROOT = Path.cwd()

from PyInstaller.utils.hooks import collect_dynamic_libs

cv2_binaries = collect_dynamic_libs("cv2")

a = Analysis(
    [str(PROJECT_ROOT / "src/ocr_from2xlsx/__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=cv2_binaries,
    datas=[
        (str(PROJECT_ROOT / "VERSION"), "."),
        (str(PROJECT_ROOT / "src/ocr_from2xlsx/assets/shutter.wav"), "ocr_from2xlsx/assets"),
    ],
    hiddenimports=["tkinter", "cv2"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Native splash shown during PyInstaller bootstrap (before Python/Tk start), so the
# user sees a loading window immediately instead of thinking the exe did nothing.
splash = Splash(
    str(PROJECT_ROOT / "build" / "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(26, 130),
    text_size=9,
    text_color="white",
    text_default="loading components...",
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ocr-from2xlsx",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
