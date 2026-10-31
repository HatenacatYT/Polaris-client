"""アニメーション付きウィジェット群。ANIM['on']=False でも全機能は動作する。
アニメーションの速度・距離は DUR / DIST に統一する。"""
from __future__ import annotations
import math
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QTimer, QRectF, QPointF, Property,
                            QPoint, QVariantAnimation)
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient
from PySide6.QtWidgets import (QPushButton, QWidget, QStackedWidget, QFrame, QHBoxLayout, QLabel, QGraphicsOpacityEffect, QDialog,
                               QMessageBox)

from . import theme
from .theme import PANEL2, BORDER, TEXT, MUTED, OK, WARN, ERR

ANIM = {"on": True}
DUR = {"fast": 140, "normal": 220, "slow": 420}   # 全画面共通の所要時間(ms)
DIST = 28                                          # 画面遷移の移動距離(px)
EASE = QEasingCurve.OutCubic


def _go(anim: QPropertyAnimation, start, end):
    if ANIM["on"]:
        anim.stop(); anim.setStartValue(start); anim.setEndValue(end); anim.start()
    else:
        anim.stop(); anim.targetObject().setProperty(bytes(anim.propertyName()).decode(), end)


class AnimButton(QPushButton):
    DANGER = ("#ffe4e8", "#c2354b")

    def __init__(self, text="", variant="secondary", parent=None):
        super().__init__(text, parent)
        self.variant, self._h, self._p, self._busy, self._spin = variant, 0.0, 0.0, False, 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)  # タッチ操作を考慮
        self._ah = QPropertyAnimation(self, b"hoverLevel", self); self._ah.setDuration(DUR["fast"]); self._ah.setEasingCurve(EASE)
        self._ap = QPropertyAnimation(self, b"pressLevel", self); self._ap.setDuration(80)
        self._sp = QVariantAnimation(self); self._sp.setStartValue(0.0); self._sp.setEndValue(360.0)
        self._sp.setDuration(900); self._sp.setLoopCount(-1); self._sp.valueChanged.connect(self._spin_tick)

    def _gh(self): return self._h
    def _sh(self, v): self._h = v; self.update()
    def _gp(self): return self._p
    def _sp_(self, v): self._p = v; self.update()
    hoverLevel = Property(float, _gh, _sh)
    pressLevel = Property(float, _gp, _sp_)

    def _spin_tick(self, v): self._spin = float(v); self.update()

    def set_busy(self, busy: bool):
        """処理中表示。処理中はクリックを受け付けない（二重起動防止）。"""
        self._busy = busy
        self.setEnabled(not busy)
        (self._sp.start if busy else self._sp.stop)()
        self.update()

    def sizeHint(self):
        s = super().sizeHint()
        s.setWidth(max(s.width(), self.fontMetrics().horizontalAdvance(self.text()) + 36))
        return s

    def enterEvent(self, e): _go(self._ah, self._h, 1.0); super().enterEvent(e)
    def leaveEvent(self, e): _go(self._ah, self._h, 0.0); _go(self._ap, self._p, 0.0); super().leaveEvent(e)
    def mousePressEvent(self, e): _go(self._ap, self._p, 1.0); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): _go(self._ap, self._p, 0.0); super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        if self.variant == "primary":
            base, fg = theme.accent(), theme.on_accent()
        elif self.variant == "danger":
            base, fg = self.DANGER
        elif self.variant == "ghost":
            base, fg = None, TEXT
        else:
            base, fg = PANEL2, TEXT
        if self._busy:
            c = QColor(theme.accent()).darker(125)
        elif not self.isEnabled():
            c, fg = QColor(PANEL2), MUTED
        elif base is None:
            c = QColor(20, 40, 90, int(18 * self._h + 28 * self._p))
        else:
            c = QColor(base).lighter(100 + int(8 * self._h)).darker(100 + int(10 * self._p)) if self.variant == "primary" else QColor(base).darker(100 + int(5 * self._h) + int(6 * self._p))
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1).adjusted(self._p, self._p, -self._p, -self._p)
        p.setBrush(c)
        p.setPen(QPen(QColor(BORDER), 1) if self.variant == "secondary" else Qt.NoPen)
        rad = r.height() / 2   # ピル型
        if self.variant == "primary" and self.isEnabled() and not self._busy:
            g = QLinearGradient(0, r.top(), 0, r.bottom()); g.setColorAt(0, c.lighter(112)); g.setColorAt(1, c); p.setBrush(g)
        p.drawRoundedRect(r, rad, rad)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(theme.accent()), 2)); p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rad - 1, rad - 1)
        p.setPen(QColor(theme.on_accent() if self._busy else fg))
        tr_ = self.rect()
        if self._busy:
            d = min(22, self.height() - 20); fm = self.fontMetrics(); tw = fm.horizontalAdvance(self.text())
            x0 = (self.width() - tw - d - 10) / 2
            p.setPen(QPen(QColor(theme.on_accent()), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(x0, (self.height() - d) / 2, d, d), int(-self._spin * 16), 270 * 16)
            p.setPen(QColor(theme.on_accent())); tr_ = self.rect().adjusted(int(x0 + d + 10), 0, 0, 0)
            p.drawText(tr_, Qt.AlignVCenter | Qt.AlignLeft, self.text()); return
        p.drawText(tr_, Qt.AlignCenter, self.text())


class GearButton(QPushButton):
    """歯車アイコン。ホバーで回転、押下で縮小。色はテーマに追従。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48); self.setCursor(Qt.PointingHandCursor); self.setFlat(True)
        self._a, self._h, self._p = 0.0, 0.0, 0.0
        self._aa = QPropertyAnimation(self, b"angle", self); self._aa.setDuration(DUR["slow"]); self._aa.setEasingCurve(QEasingCurve.OutBack)
        self._ah = QPropertyAnimation(self, b"hov", self); self._ah.setDuration(DUR["fast"])
        self._ap = QPropertyAnimation(self, b"prs", self); self._ap.setDuration(80)

    def _ga(self): return self._a
    def _sa(self, v): self._a = v; self.update()
    def _gh(self): return self._h
    def _sh(self, v): self._h = v; self.update()
    def _gp(self): return self._p
    def _sp(self, v): self._p = v; self.update()
    angle = Property(float, _ga, _sa); hov = Property(float, _gh, _sh); prs = Property(float, _gp, _sp)

    def enterEvent(self, e): _go(self._aa, self._a, 90.0); _go(self._ah, self._h, 1.0); super().enterEvent(e)
    def leaveEvent(self, e): _go(self._aa, self._a, 0.0); _go(self._ah, self._h, 0.0); _go(self._ap, self._p, 0.0); super().leaveEvent(e)
    def mousePressEvent(self, e): _go(self._ap, self._p, 1.0); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): _go(self._ap, self._p, 0.0); super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.BORDER), 1.2)); p.setBrush(QColor(255, 255, 255, 235 - int(25 * self._p))); p.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        p.setPen(Qt.NoPen)
        p.translate(self.width() / 2, self.height() / 2); p.rotate(self._a); s = 1.0 - 0.08 * self._p; p.scale(s, s)
        path = QPainterPath(); teeth, ro, ri = 8, 12.5, 9.5
        for i in range(teeth):
            t = 2 * math.pi * i / teeth
            for dt, r in ((-0.30, ri), (-0.17, ro), (0.17, ro), (0.30, ri)):
                pt = QPointF(math.cos(t + dt) * r, math.sin(t + dt) * r)
                path.moveTo(pt) if (i == 0 and dt == -0.30) else path.lineTo(pt)
        path.closeSubpath(); path.addEllipse(QPointF(0, 0), 4.2, 4.2); path.setFillRule(Qt.OddEvenFill)
        col = QColor(theme.accent()) if self._h > 0.5 else QColor(MUTED)
        p.setBrush(col); p.drawPath(path)


class Spinner(QWidget):
    def __init__(self, parent=None, size=22):
        super().__init__(parent)
        self.setFixedSize(size, size); self._a = 0.0
        self._an = QVariantAnimation(self); self._an.setStartValue(0.0); self._an.setEndValue(360.0)
        self._an.setDuration(900); self._an.setLoopCount(-1); self._an.valueChanged.connect(self._tick)
        self.hide()

    def _tick(self, v): self._a = float(v); self.update()
    def start(self): self.show(); self._an.start()
    def stop(self): self._an.stop(); self.hide()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.accent()), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(3, 3, self.width() - 6, self.height() - 6), int(-self._a * 16), 270 * 16)


class Toast(QFrame):
    def __init__(self, parent, text, kind):
        super().__init__(parent)
        col = {"info": theme.accent(), "ok": OK, "warn": WARN, "error": ERR}.get(kind, theme.accent())
        self.setObjectName("toast")
        self.setStyleSheet(f"#toast{{background:{PANEL2};border:1px solid {BORDER};border-left:4px solid {col};border-radius:10px;}}"
                           f"QLabel{{color:{TEXT};background:transparent;}}")
        lay = QHBoxLayout(self); lay.setContentsMargins(14, 10, 14, 10)
        lb = QLabel(text); lb.setWordWrap(True); lay.addWidget(lb)
        self.setFixedWidth(360); self.adjustSize(); self._in = None


class ToastManager:
    def __init__(self, host: QWidget):
        self.host, self.items = host, []

    def show(self, text, kind="info", ms=3200):
        t = Toast(self.host, text, kind)
        self.items.append(t); t.show(); t.raise_()
        if len(self.items) > 4:
            self._remove(self.items[0], immediate=True)
        self.reflow()
        if ANIM["on"]:
            eff = QGraphicsOpacityEffect(t); t.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", t); a.setDuration(DUR["normal"]); a.setStartValue(0.0); a.setEndValue(1.0)
            a.setEasingCurve(EASE); t._in = a; a.start()
        QTimer.singleShot(ms, lambda: self._remove(t))

    def _remove(self, t, immediate=False):
        if t not in self.items:
            return
        self.items.remove(t)
        try:
            if immediate or not ANIM["on"]:
                t.hide(); t.deleteLater()
            else:
                if t._in is not None:
                    t._in.stop()
                eff = t.graphicsEffect() or QGraphicsOpacityEffect(t)
                t.setGraphicsEffect(eff)
                a = QPropertyAnimation(eff, b"opacity", t); a.setDuration(DUR["normal"])
                a.setStartValue(eff.opacity()); a.setEndValue(0.0); a.finished.connect(t.deleteLater); a.start()
        except RuntimeError:
            # A parent window may be destroyed before the toast's single-shot
            # timer fires. The stale Python wrapper must not break the event loop.
            return
        self.reflow()

    def reflow(self):
        y = self.host.height() - 16
        for t in reversed(self.items):
            y -= t.height(); t.move(max(0, self.host.width() - t.width() - 16), y); y -= 10


class SlideStack(QStackedWidget):
    """ページ切替のスライド+フェード。連打されても前のアニメーションを確実に終了させる。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._group = None; self._w = None

    def _cleanup(self):
        if self._group is not None:
            g, self._group = self._group, None
            g.stop(); g.deleteLater()
        if self._w is not None:
            w, self._w = self._w, None
            w.setGraphicsEffect(None)
            w.setGeometry(self.rect())

    def slide_to(self, index: int, animate=True):
        if index == self.currentIndex():
            return
        self._cleanup()
        direction = 1 if index > self.currentIndex() else -1
        self.setCurrentIndex(index)
        w = self.currentWidget()
        if not animate or not ANIM["on"] or not self.isVisible() or w is None:
            return
        self._w = w
        eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
        end = w.pos()
        pa = QPropertyAnimation(w, b"pos", w); pa.setDuration(DUR["normal"]); pa.setEasingCurve(EASE)
        pa.setStartValue(end + QPoint(0, DIST * direction)); pa.setEndValue(end)
        fa = QPropertyAnimation(eff, b"opacity", w); fa.setDuration(DUR["normal"]); fa.setStartValue(0.0); fa.setEndValue(1.0)
        g = QParallelAnimationGroup(self); g.addAnimation(pa); g.addAnimation(fa)
        g.finished.connect(self._cleanup); self._group = g; g.start()


class FadeMixin:
    """ダイアログの表示・終了フェード。終了中の多重呼び出しは無視する。"""
    _closing = False

    def showEvent(self, e):
        super().showEvent(e)
        if ANIM["on"] and not getattr(self, "_shown_once", False):
            self._shown_once = True
            self.setWindowOpacity(0.0)
            a = QPropertyAnimation(self, b"windowOpacity", self); a.setDuration(DUR["fast"]); a.setStartValue(0.0); a.setEndValue(1.0)
            a.setEasingCurve(EASE); a.start(); self._fade = a

    def done(self, r):
        if ANIM["on"] and self.isVisible() and not self._closing:
            self._closing = True
            a = QPropertyAnimation(self, b"windowOpacity", self); a.setDuration(110)
            a.setStartValue(self.windowOpacity()); a.setEndValue(0.0)
            a.finished.connect(lambda: QDialog.done(self, r)); a.start(); self._fade_out = a
        elif not self._closing:
            QDialog.done(self, r)


class FadeDialog(FadeMixin, QDialog):
    pass


class FadeMessageBox(FadeMixin, QMessageBox):
    pass
