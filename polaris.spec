# PyInstaller spec (ASCII only on purpose: old PyInstaller reads specs with the locale encoding).
#   python -m PyInstaller --noconfirm --clean polaris.spec
# Default: ONE-FILE build  -> dist/Polaris.exe
# Set POLARIS_ONEDIR=1     -> folder build (dist/Polaris/Polaris.exe), starts faster because nothing is unpacked at launch.
import os
from PyInstaller.utils.hooks import collect_submodules

ONEDIR = os.environ.get("POLARIS_ONEDIR") == "1"

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("polaris/assets", "polaris/assets")],
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets"] + collect_submodules("polaris"),
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "tkinter"],
)
pyz = PYZ(a.pure)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Polaris", console=False, icon="polaris/assets/polaris.ico")
    coll = COLLECT(exe, a.binaries, a.datas, name="Polaris")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="Polaris", console=False, upx=False,
              icon="polaris/assets/polaris.ico")
