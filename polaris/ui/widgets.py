"""アニメーション付きウィジェット群。ANIM['on']=False でも全機能は動作する。"""
from __future__ import annotations
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QTimer, QRectF, Property, QPoint)
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QPushButton, QWidget, QStackedWidget, QFrame, QHBoxLayout, QLabel, QGraphicsOpacityEffect, QVBoxLayout)

from .theme import ACCENT, PANEL, PANEL2, BORDER, TEXT, MUTED, OK, WARN, ERR

ANIM = {"on": True}


def _go(anim: QPropertyAnimation, start, end):
    if ANIM["on"]:
        anim.stop(); anim.setStartValue(start); anim.setEndValue(end); anim.start()
    else:
        anim.targetObject().setProperty(anim.propertyName().data().decode(), end)


class AnimButton(QPushButton):
    COLORS = {"primary": (ACCENT, "#ffffff"), "secondary": (PANEL2, TEXT), "danger": ("#5a2327", "#ffd9d9"), "ghost": (None, TEXT)}

    def __init__(self, text="", variant="secondary", parent=None):
        super().__init__(text, parent)
        self.variant, self._h, self._p = variant, 0.0, 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)  # タッチ操作を考慮
        self._ah = QPropertyAnimation(self, b"hoverLevel", self); self._ah.setDuration(140)
        self._ap = QPropertyAnimation(self, b"pressLevel", self); self._ap.setDuration(80)

    def _gh(self): return self._h
    def _sh(self, v): self._h = v; self.update()
    def _gp(self): return self._p
    def _sp(self, v): self._p = v; self.update()
    hoverLevel = Property(float, _gh, _sh)
    pressLevel = Property(float, _gp, _sp)

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
        base, fg = self.COLORS.get(self.variant, self.COLORS["secondary"])
        if not self.isEnabled():
            c, fg = QColor(PANEL2), MUTED
        elif base is None:
            c = QColor(255, 255, 255, int(28 * self._h + 40 * self._p))
        else:
            c = QColor(base).lighter(100 + int(16 * self._h)).darker(100 + int(20 * self._p))
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        r.adjust(self._p, self._p, -self._p, -self._p)
        p.setBrush(c)
        p.setPen(QPen(QColor(BORDER), 1) if self.variant == "secondary" else Qt.NoPen)
        p.drawRoundedRect(r, 9, 9)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(ACCENT), 2)); p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 8, 8)
        p.setPen(QColor(fg)); p.drawText(self.rect(), Qt.AlignCenter, self.text())


class Spinner(QWidget):
    def __init__(self, parent=None, size=22):
        super().__init__(parent)
        self.setFixedSize(size, size); self._a = 0
        self._t = QTimer(self); self._t.setInterval(33); self._t.timeout.connect(self._tick)
        self.hide()

    def _tick(self): self._a = (self._a + 14) % 360; self.update()
    def start(self): self.show(); self._t.start()
    def stop(self): self._t.stop(); self.hide()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(ACCENT), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(3, 3, self.width() - 6, self.height() - 6), int(-self._a * 16), 270 * 16)


class Toast(QFrame):
    def __init__(self, parent, text, kind):
        super().__init__(parent)
        col = {"info": ACCENT, "ok": OK, "warn": WARN, "error": ERR}.get(kind, ACCENT)
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
            a = QPropertyAnimation(eff, b"opacity", t); a.setDuration(180); a.setStartValue(0.0); a.setEndValue(1.0)
            a.setEasingCurve(QEasingCurve.OutCubic); t._in = a; a.start()
        QTimer.singleShot(ms, lambda: self._remove(t))

    def _remove(self, t, immediate=False):
        if t not in self.items:
            return
        self.items.remove(t)
        if immediate or not ANIM["on"]:
            t.hide(); t.deleteLater()
        else:
            if t._in is not None:
                t._in.stop()
            eff = t.graphicsEffect() or QGraphicsOpacityEffect(t)
            t.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", t); a.setDuration(220)
            a.setStartValue(eff.opacity()); a.setEndValue(0.0)
            a.finished.connect(t.deleteLater); a.start()
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

    def slide_to(self, index: int):
        if index == self.currentIndex():
            return
        self._cleanup()
        direction = 1 if index > self.currentIndex() else -1
        self.setCurrentIndex(index)
        w = self.currentWidget()
        if not ANIM["on"] or not self.isVisible() or w is None:
            return
        self._w = w
        eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
        end = w.pos()
        pa = QPropertyAnimation(w, b"pos", w); pa.setDuration(220); pa.setEasingCurve(QEasingCurve.OutCubic)
        pa.setStartValue(end + QPoint(0, 28 * direction)); pa.setEndValue(end)
        fa = QPropertyAnimation(eff, b"opacity", w); fa.setDuration(220); fa.setStartValue(0.0); fa.setEndValue(1.0)
        g = QParallelAnimationGroup(self); g.addAnimation(pa); g.addAnimation(fa)
        g.finished.connect(self._cleanup); self._group = g; g.start()


class Sidebar(QFrame):
    EXPANDED, COLLAPSED = 220, 68

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar"); self._w = self.EXPANDED; self.setFixedWidth(self._w)
        self._anim = QPropertyAnimation(self, b"sbWidth", self); self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    def _g(self): return self._w
    def _s(self, v): self._w = int(v); self.setFixedWidth(self._w)
    sbWidth = Property(int, _g, _s)

    def set_collapsed(self, collapsed: bool):
        _go(self._anim, self._w, self.COLLAPSED if collapsed else self.EXPANDED)
