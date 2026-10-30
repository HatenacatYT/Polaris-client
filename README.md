# Polaris — Roblox カスタムランチャー（Windows / Python + PySide6）

非公式のRobloxランチャーです。Place IDを登録して「プレイ」を押すだけで、公式の起動URI
`roblox://experiences/start?placeId=<ID>` によりそのゲームへの接続を要求します。
白基調の丸みのあるUI、MP4動画／アニメーション背景、FastFlagsプリセット管理、バックアップ/復元、日本語/英語に対応します。

## インストールと起動（Windows 10/11）
1. Python 3.11 以降をインストール（「Add python.exe to PATH」推奨）
2. `run.bat` をダブルクリック（初回のみ仮想環境の作成と `pip install -r requirements.txt` を自動実行）
   - 手動: `py -3 -m venv .venv` → `.venv\Scripts\pip install -r requirements.txt` → `.venv\Scripts\python main.py`
3. データは `%APPDATA%\Polaris\` に保存されます（設定・ゲーム・プリセット・バックアップ・ログ）。管理者権限は不要です。

> 動画背景には QtMultimedia が必要です。`requirements.txt` は完全版の `PySide6`（Addons を含む）を指定しています。

## GitHub でビルドする
このリポジトリをそのまま GitHub に push すると `.github/workflows/build.yml` が動きます。

| トリガー | 動作 |
|---|---|
| Pull Request / push (main, master) | Windows 上で Python 3.11/3.12 のテスト → PyInstaller ワンファイルビルド → 15秒間の起動スモークテスト → `Polaris.exe` と `Polaris-windows.zip` を Artifact として保存 |
| `v*` タグの push（例 `git tag v2.0.0 && git push --tags`） | 上記に加え **GitHub Release** を自動作成して `Polaris.exe` と zip を添付 |
| Actions タブの *Run workflow* | 手動ビルド |

成果物は **ワンファイルの `Polaris.exe`**（GitHub Actions の Artifact / Release に添付）です。

ローカルでEXE化する場合:
- `build_exe.bat` → **`dist\Polaris.exe`（ワンファイル）**
- `build_exe_onedir.bat` → `dist\Polaris\Polaris.exe`（フォルダごと配布。起動が速い）
- 手動: `python -m PyInstaller --noconfirm --clean polaris.spec`（フォルダ版は環境変数 `POLARIS_ONEDIR=1` を付ける）

ワンファイル版は起動のたびに一時フォルダへ展開するため、初回起動や低速ディスクではスプラッシュ表示まで数秒かかることがあります。

### ビルド時の文字コードエラーについて
日本語Windows（cp932）や英語環境のCI（cp1252）で次のエラーが出ないよう、ビルド用ファイルは**ASCIIのみ**にしています
（`*.bat` / `polaris.spec` / `requirements*.txt` / `build.yml`。テストで検査）。`.bat` はCRLF、ビルド時は `PYTHONUTF8=1` を設定します。
これらのファイルに日本語を書き足さないでください（pip・PyInstaller・cmd.exe がロケールの文字コードで読むため）。ソースコード（.py）と画面の日本語は影響を受けません。

## 使い方
- **ホーム**: 下部中央にゲーム名（クリックで切替）→ **▶プレイ** / **FastFlags**。右上の歯車で設定へ。起動中は二重起動できません。
- **ゲームライブラリ**: Place ID または `https://www.roblox.com/games/<ID>/…` で追加。メモ・お気に入り・プリセット指定・「ホームの選択ゲームにする」。
- **FastFlags**: 保存済みプリセットの一覧。項目をクリックすると 使用する／編集する／名前を変更する／複製／エクスポート／削除。
  新規作成は空でもJSON貼り付けでも可。同名は「上書き／別名」を確認。「使用中のプリセットをRobloxへ適用」で設定ファイルへ書き込み（適用前に差分確認とバックアップ）。
- **設定**: 左のカテゴリ（一般／テーマ・背景／リンク・情報）。変更は即保存・即反映。
  - 言語: 日本語 / English（即時切替）。翻訳は `polaris/core/i18n_en.py` に集約、未翻訳は日本語へフォールバック。
  - テーマカラー: シアンブルー / パープル / レッド / グリーン / ネイビー / カスタム（カラーピッカー）。
  - 背景: 「動画」または「アニメーション」。動画は MP4 を選択（無音）。**ループ再生は設定でON/OFF**（OFFなら最後のフレームで停止）。
    動画パスは保存され、アニメーションに切り替えても保持されます。ファイルが無い/再生できない場合はアニメーション背景に自動で切り替わり通知します。
- **リンク**: `polaris/core/links.py` か、データフォルダの `links.json`（`{"youtube": "https://…"}` など）で設定。未設定の項目は「未設定」と表示します（架空のURLは使いません）。

### 動画のコーデックについて
H.264(AVC) + AAC の MP4 を推奨します。再生できない場合は形式・コーデック非対応か破損の可能性があり、エラー通知の後アニメーション背景に切り替わります。
負荷を抑えるため、ホームを離れた時・最小化中は一時停止します。

## Robloxの検出とFastFlags（重要）
- バージョンフォルダ名は固定せず、`RobloxPlayerBeta.exe` を実際に含むフォルダだけを候補にします。複数ある場合は ①公式の最新バージョン名 ②`roblox-player` 登録 ③ユーザー選択 の順で判定し、更新日時は根拠にしません。判断できなければ選択を求めます。
- 設定ファイルは `<版フォルダ>\ClientSettings\ClientAppSettings.json`。Roblox更新で版フォルダが変わるとホーム/FastFlagsに「再適用が必要」と表示します。
- Roblox は公式許可リストにあるフラグだけを受け付け、それ以外は無視します。リストはアプリに埋め込まず公式投稿から取得（取得失敗・24時間超過は「未確認」）。
- **「設定ファイルへの保存完了」と「Roblox内で反映された」は別です。** 後者はランチャーから確認できません。

## テスト
`run_tests.bat` または `python -m pytest`（`QT_QPA_PLATFORM=offscreen` で画面なし実行）。Robloxをモックしたテストで、実機への適用テストは自動化していません。

## 構成
```
main.py / polaris/main.py     起動（スプラッシュ → メイン）
polaris/core/                 GUI非依存のロジック（検出・適用・バックアップ・翻訳・設定）
polaris/ui/                   画面（home / fastflags / settings_page / pages / main_window / background / splash / widgets / theme）
polaris/assets/               ロゴ・アイコン（提供画像から生成）
tests/  tools/                テスト／翻訳キー収集
.github/workflows/build.yml   CI（テスト・ビルド・リリース）　polaris.spec  PyInstaller設定（ワンファイル/フォルダ切替）
```

## 既知の制限事項・未検証事項
- 開発環境にWindows実機とRobloxが無いため、次は**実機で未検証**です: `roblox://` による起動 / 「Robloxを通常起動」/ 文字列値の書き出し形式の受理 /
  公式許可リストの自動抽出（形式が変わると失敗）/ WindowsでのMP4再生（コーデック依存）/ GitHub Actions上での実行（本環境ではLinuxで同等のビルド・起動のみ確認）。
- ゲームへ実際に接続できたかは確認できません（起動要求の送信とプロセス検出まで）。プライベートサーバー等の参加権限は迂回しません。認証情報・Cookieは扱いません。
- 枠なしウィンドウのため、Windowsの標準タイトルバー機能の一部（Aero Peekの挙動など）は異なる場合があります。移動・リサイズ・スナップはOS標準APIを使用しています。
- Bloxstrap等が `roblox://` を引き継いでいる環境では、そちらが起動を処理します。
