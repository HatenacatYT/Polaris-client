# Polaris — Roblox カスタムランチャー（Windows / Python + PySide6）

非公式のRobloxランチャーです。Place ID登録 → 「プレイ」だけで、公式の起動URI `roblox://experiences/start?placeId=<ID>` を使って
そのゲームへの接続を要求します。FastFlag管理・自動適用・バックアップ/復元・Roblox更新後の再検出を備えます。

## インストールと起動（Windows 10/11）
1. Python 3.11 をインストール（https://www.python.org/ ・「Add python.exe to PATH」推奨）
2. `run.bat` をダブルクリック（仮想環境は作らず、現在のユーザー領域へ依存ライブラリをインストールして起動）
3. 手動の場合: `py -3.11 -m pip install --user -r requirements.txt` → `py -3.11 main.py`

データは `%APPDATA%\Polaris\` に保存されます（`app_settings.json` `games.json` `fastflags.json` `presets.json` `allowlist.json` `state.json` `backups\` `logs\`）。
管理者権限は不要です。

## 使い方
- **ゲームライブラリ**: 「＋ゲームを追加」→ Place ID か `https://www.roblox.com/games/<ID>/…` を入力 →（任意で名前取得）→ 行を選び **▶プレイ**。
  - 「プレイ（設定を適用）」= FastFlagを適用してから起動 / 「設定なしで起動」= 適用せず起動。
  - ゲームごとにプリセット、メモ、お気に入り、適用ON/OFF、起動後プロセス確認を設定できます。
- **FastFlagエディター**: 追加・編集（セルを直接編集）・削除・一括編集・検索・カテゴリ・お気に入り・有効/無効・JSON入出力・検証。
  値は `true / 12 / "文字列"` のJSONとして解釈され、解釈できなければ文字列になります（`True` は文字列）。
- **プリセット管理**: 作成・複製・削除・JSON編集・エディターへの読込・インポート/エクスポート。初期状態は空です。
- **バックアップ・復元**: 適用前に自動バックアップ。一覧・復元（確認あり）・削除・保存先変更・自動整理（既定はオフ）。
- **ログ・診断**: ログ表示、診断ログのエクスポート（認証情報・ユーザー名はマスク）。
- 適用前には変更差分の確認ダイアログが出ます（設定で無効化可）。

## Robloxの検出（バージョンフォルダ名は固定しません）
`%LOCALAPPDATA%\Roblox\Versions` などの下で **`RobloxPlayerBeta.exe` を実際に含むフォルダ**だけを候補にします。
候補が複数ある場合の判定順: ①公式の最新バージョン名(clientsettingscdn) ②`roblox-player` プロトコル登録 ③ユーザーが選んだ環境。
**更新日時は根拠にしません**。判断できない場合は推測せず、選択を求めます。起動/適用のたびに再検出するため、更新後も新しい場所へ追従します。

## FastFlagについて（重要）
- 設定ファイルは `<Robloxの版フォルダ>\ClientSettings\ClientAppSettings.json` です。Roblox更新で版フォルダが変わると設定は引き継がれないため、
  ホームに「再適用が必要」と表示し、起動時にも再適用します。
- Robloxは **公式の許可リスト**に載ったフラグだけを受け付け、リスト外は無視されます（ペナルティなし）。
  情報源: Roblox DevForum「Allowlist for local client configuration via Fast Flags」（2025-09-29）。
  リストは随時変わるため **アプリには埋め込まず**、公式投稿の1つ目の投稿から取得（自動抽出）します。
  取得失敗・24時間超過のリストは「未確認」扱いで、最新として扱いません。許可リストをファイルから読み込むこともできます。
- 「書き込み成功」と「ゲーム内で反映された」は別です。後者はランチャーから確認できません。
- 効果が検証されていないフラグを「FPSが上がる」とは扱いません。保護機能の回避・コード注入・メモリ改変は実装していません。

## テスト
`run_tests.bat`（または `python -m pytest`）。Robloxの実環境に依存しないモックテストです（この改良版で実行した結果: 38 passed / 2 skipped）。
GUIテストはオフスクリーン描画で、ページ連打・ワーカー終了処理を含みます。**実機のRobloxへの適用テストは自動化していません。**

## 外観設定
設定ページでアクセントカラー（紫・青・シアン・ローズ・アンバー・カスタム色）を選べます。ホーム画面にはPNG/JPG/WebP/BMP画像を背景として指定でき、設定は `%APPDATA%\Polaris\app_settings.json` に保存されます。起動時にはPolarisロゴのスプラッシュを表示し、メイン画面をフェードインします。

## EXE化
`build_exe.bat`（Python 3.11・仮想環境なし・PyInstaller）→ `dist\Polaris.exe`。ビルドに必要な依存関係は現在のPython環境へインストールされます。

## 既知の制限事項・未検証事項
- **作成環境にWindowsとRobloxが無いため、実機での起動確認は未実施です。** 以下は実機での確認が必要です:
  `os.startfile("roblox://…")` による起動 / 「Robloxを通常起動」（`RobloxPlayerLauncher.exe` の直接起動）/
  値を文字列で書き出す形式がRobloxに受理されること / 公式許可リストの自動抽出（投稿の形式が変わると失敗）。
- ゲームへ実際に接続できたかは確認できません（起動要求の送信とRobloxプロセスの検出まで）。
- プライベートサーバー等の参加権限は迂回しません。ログイン・Cookie・トークンは取得も保存もしません。
- Bloxstrap等が `roblox://` の処理を引き継いでいる環境では、そちらが起動を処理します。
- ゲーム名の自動取得は公開API（通信あり）に依存し、非公開ゲームでは失敗します（手入力可）。
- Windows以外では起動要求を送れません（開発・テスト用にのみ動作）。

## ホーム背景動画

設定 → 外観 →「背景動画・画像を選択」から MP4 などの動画、または画像を選択できます。動画はホーム画面の背景で自動ループ再生され、音声はミュートされます。Qt Multimedia を含む `PySide6` が必要です（`requirements.txt` 更新済み）。

ホーム画面は中央のゲーム選択・プレイボタン・FastFlagsボタンを中心にしたレイアウトです。右上の歯車から設定を開けます。

## GitHub Actions（Windows EXE 自動ビルド）

`.github/workflows/build.yml` を含めて GitHub に push すると、`main` への push / Pull Request / Actions 画面からの手動実行で、Windows 上のテストと EXE ビルドが自動実行されます。

1. リポジトリのルートに `.github/workflows/build.yml` があることを確認します。
2. 変更を `main` に push します。
3. GitHub の **Actions → Polaris Windows Build** を開き、実行結果を確認します。
4. 成功した実行を開き、Artifacts の **Polaris-Windows-Python311** から `Polaris.exe` を取得します。Artifact は 14 日で期限切れになります。

テストが失敗した場合は EXE ビルドを止める設定です。CI の成功は自動テストとパッケージ作成の成功を示しますが、Roblox 実機での起動や FastFlag の反映を保証するものではありません。
