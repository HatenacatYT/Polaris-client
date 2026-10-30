"""ホーム背景。動画(MP4等)と軽量アニメーションの2モード。画面が非表示の間は停止する。"""
from __future__ import annotations
from ..core.i18n import tr, N_
import logging
import math
import random
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QSizeF, Signal, QVariantAnimation, QPointF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen, QPolygonF
from PySide6.QtWidgets import QWidget, QGraphicsView, QGraphicsScene, QFrame

from . import theme
from .theme import BG

log = logging.getLogger("polaris.bg")


class _Shade(QWidget):
    """動画の上に重ねる暗い半透明オーバーレイ＋下部グラデーション（文字・ボタンの視認性確保）。"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.alpha, self.video = 0.45, False

    def paintEvent(self, e):
        p = QPainter(self)
        if self.video:
            p.fillRect(self.rect(), QColor(255, 255, 255, int(255 * self.alpha)))   # 白基調に合わせた明るいオーバーレイ
        g = QLinearGradient(0, self.height() * 0.45, 0, self.height())
        g.setColorAt(0, QColor(255, 255, 255, 0)); g.setColorAt(1, QColor(255, 255, 255, 190))
        p.fillRect(self.rect(), g)


class BackgroundWidget(QWidget):
    video_error = Signal(str)   # 動画を再生できない時（1回の configure につき1回）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode, self.path, self.overlay, self.count, self.speed, self.loop = "animated", "", 30, 60, 50, True
        self._ended = False
        self.video_state = "none"      # none / loading / ok / failed
        self._active, self._player, self._view, self._scene, self._item, self._audio = False, None, None, None, None, None
        self._t0, self._last, self._parts = time.monotonic(), 0.0, []
        self._clock = QVariantAnimation(self)
        self._clock.setStartValue(0.0); self._clock.setEndValue(1.0); self._clock.setDuration(1000); self._clock.setLoopCount(-1)
        self._clock.valueChanged.connect(self._tick)
        self._shade = _Shade(self)
        self._regen()

    # ---- 設定 ----
    def configure(self, mode: str, path: str, overlay: int, count: int, speed: int, loop: bool = True):
        changed_video = (mode, path) != (self.mode, self.path) or self.video_state == "none"
        self.mode, self.path, self.overlay, self.speed = mode, path or "", overlay, speed
        loop_changed, self.loop = (loop != self.loop), loop
        if count != self.count or not self._parts:
            self.count = count; self._regen()
        self._shade.alpha, self._shade.video = overlay / 100.0, (mode == "video")
        if mode == "video":
            if changed_video:
                self._start_video()
        else:
            self._stop_video(); self.video_state = "none"
        if loop_changed and self._player is not None:
            self._apply_loop()
        self._sync(); self._shade.update(); self.update()

    def _apply_loop(self):
        from PySide6.QtMultimedia import QMediaPlayer
        self._player.setLoops(QMediaPlayer.Loops.Infinite if self.loop else QMediaPlayer.Loops.Once)
        if self.loop and self._ended:      # 再生済みで止まっていた場合はループONで再開
            self._ended = False; self._player.setPosition(0)

    def set_active(self, active: bool):
        self._active = active
        self._sync()

    def _sync(self):
        animated_visible = self.mode == "animated" or self.video_state == "failed"
        if self._active and animated_visible:
            if self._clock.state() != QVariantAnimation.Running: self._clock.start()
        else:
            self._clock.stop()
        if self._player is not None:
            from PySide6.QtMultimedia import QMediaPlayer
            if self._active and self.video_state in ("loading", "ok") and not self._ended:
                if self._player.playbackState() != QMediaPlayer.PlayingState: self._player.play()
            else:
                self._player.pause()

    # ---- 動画 ----
    def _fail(self, msg: str):
        if self.video_state == "failed":
            return
        log.error("bg_video_error %s", msg)
        self._stop_video(); self.video_state = "failed"
        self._sync(); self.update(); self.video_error.emit(msg)

    def _stop_video(self):
        if self._player is not None:
            self._player.stop(); self._player.setSource(QUrl())
        if self._view is not None:
            self._view.hide()

    def _start_video(self):
        self._stop_video()
        if not self.path or not Path(self.path).is_file():
            self.video_state = "none"
            self._fail(tr("動画ファイルが見つかりません: {0}").format(self.path or tr("（未選択）"))); return
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
        except ImportError as e:
            self.video_state = "none"; self._fail(tr("QtMultimedia が利用できません（PySide6 をインストールしてください）: {0}", e)); return
        if self._player is None:
            self._scene = QGraphicsScene(self)
            self._item = QGraphicsVideoItem(); self._item.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)  # 中央基準で全面を埋める
            self._scene.addItem(self._item)
            self._view = QGraphicsView(self._scene, self)
            self._view.setFrameShape(QFrame.NoFrame); self._view.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._view.setBackgroundBrush(QColor(BG)); self._view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
            self._player = QMediaPlayer(self)  # 音声出力は作らない＝背景動画は常に無音（音声デバイスが無くても安全）
            self._player.setVideoOutput(self._item)
            self._player.setLoops(QMediaPlayer.Loops.Infinite if self.loop else QMediaPlayer.Loops.Once)
            self._player.errorOccurred.connect(lambda err, msg: self._fail(tr("動画を再生できません: {0}", msg)))
            self._player.mediaStatusChanged.connect(self._status)
        self._layout(); self._view.show(); self._shade.raise_()
        self.video_state = "loading"; self._ended = False
        self._player.setLoops(QMediaPlayer.Loops.Infinite if self.loop else QMediaPlayer.Loops.Once)
        self._player.setSource(QUrl.fromLocalFile(str(Path(self.path).resolve())))
        if self._active:
            self._player.play()

    def _status(self, st):
        from PySide6.QtMultimedia import QMediaPlayer
        M = QMediaPlayer.MediaStatus
        if st == M.EndOfMedia and not self.loop:     # ループOFF: 最後のフレームで停止したままにする
            self._ended = True
            d = self._player.duration()
            if d > 0: self._player.setPosition(max(0, d - 1))
            self._player.pause(); return
        if st == M.InvalidMedia:
            self._fail(tr("動画ファイルを読み込めません（形式・コーデック非対応、または破損）"))
        elif st in (M.LoadedMedia, M.BufferedMedia, M.BufferingMedia) and self.video_state == "loading":
            self.video_state = "ok"; self._sync(); self.update()

    # ---- アニメーション背景 ----
    def _regen(self):
        r = random.Random(7)
        self._parts = [(r.random(), r.random(), r.uniform(-0.012, 0.012), r.uniform(-0.02, -0.004), r.uniform(0.8, 2.4), r.uniform(0, 6.28))
                       for _ in range(self.count)]

    def _tick(self, _):
        now = time.monotonic()
        if now - self._last >= 0.032:   # 約30fpsに間引いてCPU負荷を抑える
            self._last = now; self.update()

    def paintEvent(self, e):
        p = QPainter(self); w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG))
        if self.mode == "video" and self.video_state in ("loading", "ok"):
            return                       # 読み込み中は単色フォールバック
        p.setRenderHint(QPainter.Antialiasing)
        acc = QColor(theme.accent())
        g = QLinearGradient(0, 0, 0, h); top = QColor(255, 255, 255); bot = QColor(acc); bot.setAlpha(64)
        g.setColorAt(0, top); g.setColorAt(1, bot); p.fillRect(self.rect(), g)
        T = (time.monotonic() - self._t0) * self.speed / 50.0
        cx, cy, R = w * 0.5, h * 0.40, min(w, h) * 0.30
        p.save(); p.translate(cx, cy); p.rotate(-18 + (T * 2.0) % 360)
        p.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), 70), 1.6)); p.setBrush(Qt.NoBrush); p.drawEllipse(QPointF(0, 0), R * 1.5, R * 0.42)
        p.setPen(Qt.NoPen); a = (T * 0.35) % (2 * math.pi)
        p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 190)); p.drawEllipse(QPointF(math.cos(a) * R * 1.5, math.sin(a) * R * 0.42), 4, 4)
        p.restore()
        star = QPolygonF()
        for i in range(8):
            ang = math.pi / 4 * i - math.pi / 2; rad = R * (0.55 if i % 2 == 0 else 0.09)
            star.append(QPointF(cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
        p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 34)); p.setPen(Qt.NoPen); p.drawPolygon(star)
        for x0, y0, vx, vy, r, ph in self._parts:      # ふわふわ浮かぶ丸い光
            x, y = ((x0 + vx * T) % 1.0) * w, ((y0 + vy * T) % 1.0) * h
            tw = 0.5 + 0.5 * math.sin(T * 1.2 + ph)
            rr = r * (2.2 if r > 1.7 else 1.4)
            p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), int(30 + 80 * tw) if r > 1.7 else int(60 + 90 * tw))); p.drawEllipse(QPointF(x, y), rr, rr)

    # ---- レイアウト ----
    def _layout(self):
        if self._view is not None:
            self._view.setGeometry(self.rect()); self._scene.setSceneRect(0, 0, self.width(), self.height())
            self._item.setSize(QSizeF(self.width(), self.height()))
        self._shade.setGeometry(self.rect()); self._shade.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e); self._layout()

    def dispose(self):
        self._clock.stop()
        if self._player is not None:
            self._player.stop(); self._player.setSource(QUrl()); self._player.setVideoOutput(None)
