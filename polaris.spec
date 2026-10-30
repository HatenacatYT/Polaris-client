# PyInstaller spec — `pyinstaller --noconfirm --clean polaris.spec` で dist/Polaris/Polaris.exe を生成
# onedir 形式: onefile だと起動のたびに展開が走り、スプラッシュが出るまで時間がかかるため
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("polaris/assets", "polaris/assets")],
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets"] + collect_submodules("polaris"),
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Polaris", console=False, icon="polaris/assets/polaris.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Polaris")
