@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul || (echo Python 3.11 以降をインストールしてください: https://www.python.org/ & pause & exit /b 1)
if not exist .venv (
  echo 初回セットアップ中...
  py -3 -m venv .venv || (echo 仮想環境の作成に失敗しました & pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || (echo 依存ライブラリのインストールに失敗しました & pause & exit /b 1)
)
start "" .venv\Scripts\pythonw.exe main.py
