"""起動スプラッシュ。角丸・枠なし。ロゴは縦横比を維持して中央表示。"""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPixmap, QPen, QGuiApplication
from PySide6.QtWidgets import QWidget, QLabel

from . import assets
from .widgets import Spinner

SPLASH_BG = "#ffffff"


class SplashWindow(QWidget):
    W, H, RADIUS = 520, 340, 28

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground); self.resize(self.W, self.H)
        self._star = QPixmap(str(assets.path("polaris_icon_black.png")))
        self._word = QPixmap(str(assets.path("polaris_wordmark_black.png")))
        self.spin = Spinner(self, 22)
        self.hint = QLabel("", self); self.hint.setAlignment(Qt.AlignCenter); self.hint.setStyleSheet("color:#6d7b96;background:transparent;")
        self.hint.hide()
        scr = QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry(); self.move(g.center().x() - self.W // 2, g.center().y() - self.H // 2)
        QTimer.singleShot(700, self._late_spinner)   # 一瞬で終わる起動では出さない

    def _late_spinner(self):
        if self.isVisible():
            self.spin.start()

    def show_hint(self, text: str):
        self.hint.setText(text); self.hint.show()

    def resizeEvent(self, e):
        self.spin.move((self.width() - 22) // 2, self.height() - 52)
        self.hint.setGeometry(20, self.height() - 80, self.width() - 40, 22)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(QColor(SPLASH_BG)); p.setPen(QPen(QColor("#d3e1f4"), 1.5)); p.drawRoundedRect(r, self.RADIUS, self.RADIUS)
        dpr = self.devicePixelRatioF()
        # 縦横比を維持（高さ基準で拡縮）。ウィンドウ拡大中もロゴの大きさは一定。
        sh, wh = 132, 52
        s = self._star.scaledToHeight(int(sh * dpr), Qt.SmoothTransformation); s.setDevicePixelRatio(dpr)
        w = self._word.scaledToHeight(int(wh * dpr), Qt.SmoothTransformation); w.setDevicePixelRatio(dpr)
        cx, cy = self.width() / 2, self.height() / 2 - 22
        p.drawPixmap(int(cx - s.width() / dpr / 2), int(cy - 52 - sh / 2 + 20), s)
        p.drawPixmap(int(cx - w.width() / dpr / 2), int(cy + sh / 2 + 4), w)
