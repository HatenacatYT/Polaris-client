"""設定: 左カテゴリ／右内容。変更は即時に保存・反映される。"""
from __future__ import annotations
import platform
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, qVersion
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QScrollArea, QFrame, QComboBox, QCheckBox, QRadioButton,
                               QSlider, QLabel, QFileDialog, QColorDialog, QPlainTextEdit, QPushButton, QButtonGroup)

from .. import APP_NAME, __version__
from ..core.i18n import LANGUAGES, N_, tr
from ..core.jsonio import StorageError
from ..core.links import get_links, AUTHOR
from ..core.roblox import Detector
from ..core.store import AppSettings
from . import theme
from .background import BackgroundWidget
from .dialogs import choose, TextDialog, open_folder, open_url
from .pages import lbl, card, row, btn
from .widgets import AnimButton, SlideStack, ANIM

OSS_NOTICE = N_("""Polaris は次のオープンソースソフトウェアを利用しています。

・PySide6 / Qt for Python（Qt）— GNU LGPL v3 でライセンスされています。
  Qt のライセンスについては Qt Group の公式ライセンス情報を参照してください。
・Python — Python Software Foundation License

Polaris 自体のライセンスは未設定です（配布時に追記してください）。
Polaris は Roblox Corporation とは無関係の非公式ツールです。""")

FEATURES = N_("""【実装済み・自動テスト済み（Robloxをモックした単体テスト／画面を出さないGUIテスト）】
 Place ID/URL解析・検証 / JSON安全読み書き・破損復旧 / FastFlagプリセットの作成・編集・名前変更・削除・インポート/エクスポート
 バックアップ作成・復元・自動整理 / Roblox環境検出（未インストール・複数環境・更新後の再検出）
 ClientAppSettings.jsonへの適用（一時ファイル→検証→置換、失敗時ロールバック）/ 起動フロー / ログのマスキング
 言語切替・テーマ色・背景(MP4動画/アニメーション)・スプラッシュ・設定の保存と復元

【実装済み・Windows実機のRobloxでは未検証（要確認）】
 roblox://experiences/start?placeId=… による起動要求 / 「Robloxを通常起動」/ 値を文字列で書き出す形式の受理
 公式許可リストの自動取得（形式が変わると失敗します）/ WindowsでのMP4再生（コーデック依存）

【できないこと（仕様上の制限）】
 ・ゲームへ「実際に接続できたか」の確認 … 起動要求の送信とプロセス検出までしか判定できません
 ・公式許可リストに無いフラグの反映 … Robloxに無視されます
 ・プライベートサーバー等の参加権限の迂回 … 行いません""")


def features_text() -> str:
    return tr(FEATURES)


class Swatch(QPushButton):
    def __init__(self, key, color, checked_fn, parent=None):
        super().__init__(parent)
        self.key, self.color, self.checked_fn = key, color, checked_fn
        self.setFixedSize(40, 40); self.setCursor(Qt.PointingHandCursor); self.setFlat(True)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        sel = self.checked_fn()
        p.setPen(QPen(QColor(theme.TEXT), 2.5) if sel else Qt.NoPen); p.setBrush(QColor(self.color))
        p.drawEllipse(self.rect().adjusted(5, 5, -5, -5))
        if self.key == "custom":
            p.setPen(QColor(theme.on_accent() if QColor(self.color).lightness() > 170 else "#ffffff")); p.drawText(self.rect(), Qt.AlignCenter, tr("＋"))


class SettingsPage(QWidget):
    title = N_("設定")
    CATS = [N_("一般"), N_("テーマ・背景"), N_("リンク・情報")]

    def __init__(self, win):
        super().__init__()
        self.win, self.core, self._loading = win, win.core, False
        self._deb = QTimer(self); self._deb.setSingleShot(True); self._deb.timeout.connect(lambda: self._save(False))
        h = QHBoxLayout(self); h.setContentsMargins(24, 24, 24, 24); h.setSpacing(16)
        self.cats = QListWidget(); self.cats.setObjectName("cats"); self.cats.setFixedWidth(180)
        for c in self.CATS:
            self.cats.addItem(tr(c))
        self.stack = SlideStack()
        h.addWidget(self.cats); h.addWidget(self.stack, 1)
        for build in (self._general, self._appearance, self._about):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 8, 0); v.setSpacing(14); build(v); v.addStretch()
            sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame); sc.setWidget(w); self.stack.addWidget(sc)
        self.cats.currentRowChanged.connect(self._cat)
        self.cats.setCurrentRow(0)

    def _cat(self, i):
        if i >= 0:
            self.stack.slide_to(i)
        self._preview_active()

    def _preview_active(self):
        self.preview.set_active(self.isVisible() and self.cats.currentRow() == 1)

    def showEvent(self, e): super().showEvent(e); self._preview_active()
    def hideEvent(self, e): super().hideEvent(e); self.preview.set_active(False)

    # ---- 一般 ----
    def _general(self, v):
        v.addWidget(lbl(tr("一般"), "h1"))
        f, fv = card(tr("言語"))
        self.lang = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.currentIndexChanged.connect(self._lang)
        fv.addWidget(self.lang); v.addWidget(f)
        f, fv = card(tr("動作"))
        self.anim = QCheckBox(tr("アニメーションを有効にする")); self.confirm = QCheckBox(tr("適用前に変更内容の確認を表示する"))
        self.autoal = QCheckBox(tr("起動時に公式許可リストを自動確認する（通信あり）"))
        self.fmt = QComboBox(); self.fmt.addItem(tr("文字列（\"True\" / \"5\"）— Bloxstrap互換"), "string"); self.fmt.addItem(tr("JSONの型のまま（true / 5）"), "native")
        self.mode = QComboBox(); self.mode.addItem(tr("設定を適用して起動"), "apply_and_play"); self.mode.addItem(tr("設定なしで通常起動"), "play_only")
        for w in (self.anim, self.confirm, self.autoal):
            fv.addWidget(w)
        fv.addWidget(lbl(tr("Robloxへ書き出す値の形式（実機での挙動は未検証）"), "muted")); fv.addWidget(self.fmt)
        fv.addWidget(lbl(tr("ホームのプレイボタン／ライブラリのダブルクリックの起動方法"), "muted")); fv.addWidget(self.mode)
        v.addWidget(f)
        for w, sig in ((self.anim, self.anim.toggled), (self.confirm, self.confirm.toggled), (self.autoal, self.autoal.toggled),
                       (self.fmt, self.fmt.currentIndexChanged), (self.mode, self.mode.currentIndexChanged)):
            sig.connect(self._save_general)
        f, fv = card(tr("Roblox環境・データ"))
        self.pin = lbl("", "muted"); fv.addWidget(self.pin)
        fv.addLayout(row(btn(tr("Roblox環境を手動選択"), self.pick_env), btn(tr("手動選択を解除"), self.unpin),
                         btn(tr("データフォルダを開く"), lambda: open_folder(self.core.paths.root)), stretch=True))
        fv.addLayout(row(btn(tr("設定を初期化"), self.reset, "danger"), stretch=True))
        v.addWidget(f)

    def _save(self, msg=True):
        try:
            self.core.settings.save()
            if msg: self.win.toast.show(tr("設定を保存しました"), "ok", 1800)
            return True
        except StorageError as e:
            choose(self.win, tr("設定を保存できません"), tr("{0}\n\n変更はこのセッションでのみ有効です。権限・空き容量を確認してください。", e), [tr("閉じる")], "error")
            return False

    def _save_general(self, *_):
        if self._loading: return
        s = self.core.settings.data
        s.animations, s.confirm_before_apply, s.auto_check_allowlist = self.anim.isChecked(), self.confirm.isChecked(), self.autoal.isChecked()
        s.value_format, s.default_launch_mode = self.fmt.currentData(), self.mode.currentData()
        ANIM["on"] = s.animations
        self._save()

    def _lang(self, *_):
        if self._loading: return
        code = self.lang.currentData()
        if code != self.core.settings.data.language:
            self.core.settings.data.language = code
            if self._save(False):
                self.win.change_language(code)

    def pick_env(self):
        from PySide6.QtWidgets import QInputDialog
        c = [str(x) for x in self.core.detector.candidates()]
        if not c:
            self.win.toast.show(tr("有効なRoblox環境が見つかりません"), "warn"); return
        item, ok = QInputDialog.getItem(self.win, tr("Roblox環境の選択"), tr("使用する環境:"), c, 0, False)
        if ok:
            self.core.settings.data.pinned_version_dir = item; self._save(); self.win.redetect()

    def unpin(self):
        self.core.settings.data.pinned_version_dir = ""; self._save(); self.win.redetect()

    def reset(self):
        if choose(self.win, tr("設定の初期化"), tr("アプリ設定を初期値に戻します（ゲーム・プリセットは消えません）。言語・テーマ・背景も初期値に戻ります。"), [tr("初期化"), tr("キャンセル")], "warn") == 0:
            keep = (self.core.settings.data.active_preset, self.core.settings.data.selected_game_id)
            self.core.settings.data = AppSettings(active_preset=keep[0], selected_game_id=keep[1])
            ANIM["on"] = True
            if self._save(False):
                self.win.change_language("ja"); self.win.apply_appearance(); self.win.toast.show(tr("初期化しました"), "ok")

    # ---- テーマ・背景 ----
    def _appearance(self, v):
        v.addWidget(lbl(tr("テーマ・背景"), "h1"))
        f, fv = card(tr("テーマカラー"))
        sw = QHBoxLayout(); sw.setSpacing(6); self.swatches = []
        names = {"cyan": tr("シアンブルー"), "purple": tr("パープル"), "red": tr("レッド"), "green": tr("グリーン"), "navy": tr("ネイビー"), "custom": tr("カスタムカラー")}
        for key in ("cyan", "purple", "red", "green", "navy", "custom"):
            s = Swatch(key, theme.PRESET_COLORS.get(key) or self.core.settings.data.custom_color, lambda k=key: self.core.settings.data.accent == k)
            s.setToolTip(names[key]); s.setAccessibleName(names[key]); s.clicked.connect(lambda _=False, k=key: self._accent(k))
            sw.addWidget(s); self.swatches.append(s)
        sw.addStretch(); fv.addLayout(sw)
        self.accent_lbl = lbl("", "muted"); fv.addWidget(self.accent_lbl); v.addWidget(f)

        f, fv = card(tr("ホーム画面の背景"))
        self.rb_anim, self.rb_video = QRadioButton(tr("アニメーション背景（軽量）")), QRadioButton(tr("動画背景（MP4など）"))
        grp = QButtonGroup(self); grp.addButton(self.rb_anim); grp.addButton(self.rb_video)
        self.rb_anim.toggled.connect(self._bg_mode)
        fv.addWidget(self.rb_anim); fv.addWidget(self.rb_video)
        self.vbox = QWidget(); vb = QVBoxLayout(self.vbox); vb.setContentsMargins(24, 0, 0, 0)
        self.vname = lbl("", None); self.vstat = lbl("", "muted")
        vb.addWidget(self.vname); vb.addWidget(self.vstat)
        vb.addLayout(row(btn(tr("動画ファイルを選択…"), self.pick_video, "primary"), btn(tr("選択を解除"), self.clear_video), stretch=True))
        self.loop = QCheckBox(tr("動画をループ再生する（オフなら最後のフレームで停止）")); self.loop.toggled.connect(self._bg_values)
        vb.addWidget(self.loop)
        self.overlay, self.ov_l = self._slider(0, 90, tr("白いオーバーレイの濃さ")); vb.addLayout(self.overlay)
        fv.addWidget(self.vbox)
        self.abox = QWidget(); ab = QVBoxLayout(self.abox); ab.setContentsMargins(24, 0, 0, 0)
        self.parts, self.pt_l = self._slider(10, 150, tr("粒子の数")); self.speed, self.sp_l = self._slider(10, 200, tr("動きの速さ"))
        ab.addLayout(self.parts); ab.addLayout(self.speed); fv.addWidget(self.abox); v.addWidget(f)
        f, fv = card(tr("プレビュー"))
        self.preview = BackgroundWidget(); self.preview.setMinimumHeight(190); self.preview.setMaximumHeight(240)
        self.preview.video_error.connect(self._preview_error)
        fv.addWidget(self.preview); fv.addWidget(lbl(tr("動画は音声なしで再生されます。再生できない場合はアニメーション背景が表示されます。"), "muted")); v.addWidget(f)

    def _slider(self, lo, hi, label):
        row_ = QHBoxLayout(); l = QLabel(label); l.setMinimumWidth(130); s = QSlider(Qt.Horizontal); s.setRange(lo, hi); val = QLabel(""); val.setMinimumWidth(40)
        row_.addWidget(l); row_.addWidget(s, 1); row_.addWidget(val)
        s.valueChanged.connect(lambda x: (val.setText(str(x)), self._bg_values()))
        s.val_label = val
        return row_, s

    def _accent(self, key):
        s = self.core.settings.data
        if key == "custom":
            c = QColorDialog.getColor(QColor(s.custom_color), self.win, tr("カスタムカラーを選択"))
            if not c.isValid():
                return
            s.custom_color = c.name()
        s.accent = key
        if self._save():
            self.win.apply_appearance(); self.refresh()

    def _bg_mode(self, *_):
        if self._loading: return
        self.core.settings.data.bg_mode = "animated" if self.rb_anim.isChecked() else "video"
        if self._save(): self.win.apply_bg(); self._sync_bg()

    def _bg_values(self):
        if self._loading: return
        s = self.core.settings.data
        s.bg_overlay, s.bg_particles, s.bg_speed = self.overlay_s().value(), self.parts_s().value(), self.speed_s().value()
        s.bg_loop = self.loop.isChecked()
        self.win.apply_bg(); self._sync_bg(); self._deb.start(350)   # 操作中は即プレビュー、保存は操作が止まってから

    def overlay_s(self): return self.overlay.itemAt(1).widget()
    def parts_s(self): return self.parts.itemAt(1).widget()
    def speed_s(self): return self.speed.itemAt(1).widget()

    def pick_video(self):
        s = self.core.settings.data
        start = str(Path(s.bg_video_path).parent) if s.bg_video_path else ""
        path, _ = QFileDialog.getOpenFileName(self.win, tr("背景動画を選択"), start, tr("MP4動画 (*.mp4);;動画ファイル (*.mp4 *.m4v *.mov *.mkv *.webm *.avi);;すべて (*)"))
        if not path:
            return
        s.bg_video_path = str(Path(path)); s.bg_mode = "video"          # 以前の動画パスは上書き（モード切替では消さない）
        if self._save(): self.win.apply_bg(); self.refresh()

    def clear_video(self):
        self.core.settings.data.bg_video_path = ""
        if self._save(): self.win.apply_bg(); self.refresh()

    def _preview_error(self, msg):
        self.vstat.setText(f"<span style='color:#ff5c5c'>⚠ {msg}</span>")

    def _sync_bg(self):
        s = self.core.settings.data
        self.vbox.setVisible(s.bg_mode == "video"); self.abox.setVisible(s.bg_mode == "animated")
        self.preview.configure(s.bg_mode, s.bg_video_path, s.bg_overlay, s.bg_particles, s.bg_speed, s.bg_loop)
        self._preview_active()
        p = Path(s.bg_video_path) if s.bg_video_path else None
        self.vname.setText(tr("選択中の動画: {0}", p.name) if p else tr("動画ファイルが選択されていません"))
        self.vname.setToolTip(s.bg_video_path)
        self.vstat.setText("" if (p and p.is_file()) or not p else tr("<span style='color:#ff5c5c'>⚠ ファイルが見つかりません（移動・削除された可能性）。再度選択してください</span>"))

    # ---- リンク・情報 ----
    def _about(self, v):
        v.addWidget(lbl(tr("リンク・情報"), "h1"))
        f, fv = card(tr("バージョン情報"))
        import PySide6
        fv.addWidget(lbl(f"{APP_NAME} v{__version__}"))
        fv.addWidget(lbl(tr("Python {0}  ・  PySide6 {1}  ・  Qt {2}  ・  {3}", platform.python_version(), PySide6.__version__, qVersion(), platform.platform()), "muted"))
        fv.addWidget(lbl(tr("Roblox Corporation とは無関係の非公式ランチャーです。認証情報・Cookieの取得や保存は行いません。"), "muted")); v.addWidget(f)
        f, fv = card(tr("リンク"))
        links = get_links(self.core.paths.root)
        for key, label in (("youtube", tr("YouTubeチャンネル")), ("website", tr("公式サイト")), ("support", tr("サポート")), ("terms", tr("利用規約")), ("privacy", tr("プライバシーポリシー"))):
            if links.get(key):
                fv.addLayout(row(btn(label, lambda u=links[key]: open_url(u)), stretch=True))
            else:
                fv.addWidget(lbl(tr("{0}: 未設定", label), "muted"))
        fv.addLayout(row(btn(tr("オープンソースライセンス"), lambda: TextDialog(self.win, tr("オープンソースライセンス"), tr("利用しているソフトウェアとライセンス"), tr(OSS_NOTICE)).exec()), stretch=True))
        fv.addWidget(lbl(tr("リンクは polaris/core/links.py またはデータフォルダの links.json で設定できます。"), "muted")); v.addWidget(f)
        f, fv = card(tr("機能の状態（正直な一覧）"))
        t = QPlainTextEdit(features_text()); t.setReadOnly(True); t.setMinimumHeight(300); fv.addWidget(t); v.addWidget(f)
        v.addWidget(lbl(tr("製作者: {0}", AUTHOR or tr('未設定')), "muted"))

    # ---- 同期 ----
    def refresh(self):
        s = self.core.settings.data; self._loading = True
        self.lang.setCurrentIndex(max(0, self.lang.findData(s.language)))
        self.anim.setChecked(s.animations); self.confirm.setChecked(s.confirm_before_apply); self.autoal.setChecked(s.auto_check_allowlist)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(s.value_format))); self.mode.setCurrentIndex(max(0, self.mode.findData(s.default_launch_mode)))
        self.pin.setText(tr("手動選択した環境: ") + (s.pinned_version_dir or tr("なし（自動判定）")) + tr("\n※公式情報・プロトコル登録で判定できる場合はそちらを優先します。"))
        (self.rb_anim if s.bg_mode == "animated" else self.rb_video).setChecked(True); self.loop.setChecked(s.bg_loop)
        for sl, val in ((self.overlay_s(), s.bg_overlay), (self.parts_s(), s.bg_particles), (self.speed_s(), s.bg_speed)):
            sl.setValue(val); sl.val_label.setText(str(val))
        for sw in self.swatches:
            if sw.key == "custom": sw.color = s.custom_color
            sw.update()
        names = {"cyan": tr("シアンブルー"), "purple": tr("パープル"), "red": tr("レッド"), "green": tr("グリーン"), "navy": tr("ネイビー"), "custom": tr("カスタムカラー")}
        self.accent_lbl.setText(tr("選択中: {0}（{1}）", names[s.accent], theme.resolve(s)))
        self._loading = False
        self._sync_bg()
