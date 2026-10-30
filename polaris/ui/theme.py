"""ダークテーマ。アクセント色は実行時に変更できる（theme.set_accent → apply_theme）。"""
from PySide6.QtGui import QColor, QPalette, QFont

BG, PANEL, PANEL2, BORDER = "#f5f9ff", "#ffffff", "#e9f1fd", "#d3e1f4"
TEXT, MUTED = "#22314f", "#6d7b96"
OK, WARN, ERR = "#1fae74", "#d98a0b", "#e5484d"
FONTS = ["Yu Gothic UI", "Meiryo UI", "Segoe UI", "Noto Sans CJK JP", "Noto Sans JP", "sans-serif"]
PRESET_COLORS = {"cyan": "#27a9ff", "purple": "#8b6cff", "red": "#ff5a74", "green": "#25c48b", "navy": "#2e4a86"}
RADIUS = 14   # 角丸ルール: 入力=14 / カード=20 / ボタン=ピル型(高さの半分)
_accent = ["#27a9ff"]


def accent() -> str:
    return _accent[0]


def set_accent(color: str):
    if QColor(color).isValid():
        _accent[0] = QColor(color).name()


def resolve(settings) -> str:
    return settings.custom_color if settings.accent == "custom" else PRESET_COLORS.get(settings.accent, "#27a9ff")


def on_accent() -> str:
    c = QColor(accent())
    return "#16223d" if (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) > 150 else "#ffffff"


def apply_theme(app):
    app.setStyle("Fusion")
    f = QFont(); f.setFamilies(FONTS); f.setPointSize(10); app.setFont(f)
    p = QPalette()
    for role, col in ((QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, PANEL), (QPalette.AlternateBase, PANEL2),
                      (QPalette.Text, TEXT), (QPalette.Button, PANEL2), (QPalette.ButtonText, TEXT), (QPalette.ToolTipBase, PANEL2),
                      (QPalette.ToolTipText, TEXT), (QPalette.Highlight, accent()), (QPalette.HighlightedText, on_accent()),
                      (QPalette.PlaceholderText, MUTED)):
        p.setColor(role, QColor(col))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED)); p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    app.setPalette(p)
    app.setStyleSheet(qss())


def qss() -> str:
    a, oa = accent(), on_accent()
    return f"""
QWidget {{ color:{TEXT}; }}
QMainWindow, QDialog, QMessageBox {{ background:{BG}; }}
#content {{ background:{BG}; }}
#root {{ background:{BG}; border:1px solid {BORDER}; }}
#titlebar {{ background:{PANEL}; border-bottom:1px solid {BORDER}; }}
#sidebar {{ background:{PANEL}; border-right:1px solid {BORDER}; }}
#card {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:20px; }}
#homeCard {{ background:rgba(255,255,255,0.88); border:1px solid {BORDER}; border-radius:28px; }}
#presetCard {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:20px; }}
#presetCard:hover, #presetCard:focus {{ border:2px solid {a}; background:{BG}; }}
#h1 {{ font-size:20pt; font-weight:700; }}
#h2 {{ font-size:12pt; font-weight:700; }}
#muted {{ color:{MUTED}; }}
#badge {{ background:{a}; color:{oa}; border-radius:10px; padding:2px 10px; font-size:9pt; font-weight:700; }}
QPushButton#nav {{ text-align:left; padding:10px 16px; border:none; border-radius:21px; background:transparent; min-height:22px; }}
QPushButton#nav:hover {{ background:{PANEL2}; }}
QPushButton#nav:checked {{ background:{a}; color:{oa}; font-weight:700; }}
QListWidget#cats {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:20px; padding:8px; }}
QListWidget#cats::item {{ padding:10px 14px; border-radius:16px; }}
QListWidget#cats::item:selected {{ background:{a}; color:{oa}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:14px; padding:6px 12px; min-height:24px; selection-background-color:{a}; selection-color:{oa}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border:2px solid {a}; }}
QComboBox QAbstractItemView, QMenu {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:12px; selection-background-color:{a}; selection-color:{oa}; padding:4px; }}
QMenu::item {{ padding:8px 22px; border-radius:10px; }}
QMenu::item:selected {{ background:{a}; color:{oa}; }}
QTableWidget, QListWidget {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:16px; gridline-color:{BORDER}; alternate-background-color:{BG}; }}
QTableWidget::item, QListWidget::item {{ padding:6px; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background:{a}; color:{oa}; }}
QHeaderView::section {{ background:{PANEL2}; color:{MUTED}; border:none; border-bottom:1px solid {BORDER}; padding:8px; }}
QScrollBar:vertical {{ background:transparent; width:12px; }}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:5px; min-height:30px; }}
QScrollBar:horizontal {{ background:transparent; height:12px; }}
QScrollBar::handle:horizontal {{ background:{BORDER}; border-radius:5px; min-width:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QCheckBox, QRadioButton {{ spacing:8px; min-height:28px; }}
QSlider::groove:horizontal {{ height:8px; background:{PANEL2}; border-radius:4px; }}
QSlider::sub-page:horizontal {{ background:{a}; border-radius:4px; }}
QSlider::handle:horizontal {{ background:{PANEL}; border:2px solid {a}; width:18px; margin:-7px 0; border-radius:11px; }}
QToolTip {{ background:{PANEL}; color:{TEXT}; border:1px solid {BORDER}; border-radius:8px; padding:4px; }}
QProgressBar {{ background:{PANEL2}; border:none; border-radius:2px; max-height:4px; }}
QProgressBar::chunk {{ background:{a}; border-radius:2px; }}
QPushButton {{ background:{PANEL2}; border:1px solid {BORDER}; border-radius:19px; padding:8px 18px; min-height:22px; }}
QPushButton:hover {{ background:{BORDER}; }}
"""
