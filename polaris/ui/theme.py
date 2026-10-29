"""ダークテーマ（黒・ダークグレー・白・アクセント）。"""
from PySide6.QtGui import QColor, QPalette, QFont

BG, PANEL, PANEL2, BORDER = "#101114", "#181a20", "#20232b", "#2c303a"
TEXT, MUTED, ACCENT = "#eceff4", "#9aa3b2", "#7c5cff"
OK, WARN, ERR = "#3ecf8e", "#f5a524", "#ff5c5c"
FONTS = ["Yu Gothic UI", "Meiryo UI", "Segoe UI", "Noto Sans CJK JP", "Noto Sans JP", "sans-serif"]


def apply_theme(app, accent=None):
    global ACCENT, QSS
    ACCENT = accent if isinstance(accent, str) and len(accent) == 7 and accent.startswith("#") else "#7c5cff"
    QSS = QSS_TEMPLATE
    for key, value in {"__ACCENT__": ACCENT, "{TEXT}": TEXT, "{BG}": BG, "{PANEL}": PANEL,
                       "{PANEL2}": PANEL2, "{BORDER}": BORDER, "{MUTED}": MUTED}.items():
        QSS = QSS.replace(key, value)
    app.setStyle("Fusion")
    f = QFont()
    f.setFamilies(FONTS)
    f.setPointSize(10)
    app.setFont(f)
    p = QPalette()
    for role, col in ((QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, PANEL), (QPalette.AlternateBase, PANEL2),
                      (QPalette.Text, TEXT), (QPalette.Button, PANEL2), (QPalette.ButtonText, TEXT), (QPalette.ToolTipBase, PANEL2),
                      (QPalette.ToolTipText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#ffffff"),
                      (QPalette.PlaceholderText, MUTED)):
        p.setColor(role, QColor(col))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    app.setPalette(p)
    app.setStyleSheet(QSS)


QSS_TEMPLATE = """
QWidget { color:{TEXT}; }
QMainWindow, QDialog, QMessageBox { background:{BG}; }
#content { background:{BG}; }
#sidebar { background:{PANEL}; border-right:1px solid {BORDER}; }
#card { background:{PANEL}; border:1px solid {BORDER}; border-radius:12px; }
#h1 { font-size:20pt; font-weight:600; }
#h2 { font-size:12pt; font-weight:600; }
#muted { color:{MUTED}; }
QPushButton#nav { text-align:left; padding:10px 14px; border:none; border-radius:8px; background:transparent; min-height:22px; }
QPushButton#nav:hover { background:{PANEL2}; }
QPushButton#nav:checked { background:__ACCENT__; color:white; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox { background:{PANEL2}; border:1px solid {BORDER}; border-radius:8px; padding:6px 8px; min-height:22px; selection-background-color:__ACCENT__; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border:1px solid __ACCENT__; }
QComboBox QAbstractItemView { background:{PANEL2}; border:1px solid {BORDER}; selection-background-color:__ACCENT__; }
QTableWidget, QListWidget { background:{PANEL}; border:1px solid {BORDER}; border-radius:10px; gridline-color:{BORDER}; alternate-background-color:{PANEL2}; }
QTableWidget::item, QListWidget::item { padding:6px; }
QTableWidget::item:selected, QListWidget::item:selected { background:__ACCENT__; color:white; }
QHeaderView::section { background:{PANEL2}; color:{MUTED}; border:none; border-bottom:1px solid {BORDER}; padding:8px; }
QScrollBar:vertical { background:transparent; width:12px; }
QScrollBar::handle:vertical { background:{BORDER}; border-radius:5px; min-height:30px; }
QScrollBar:horizontal { background:transparent; height:12px; }
QScrollBar::handle:horizontal { background:{BORDER}; border-radius:5px; min-width:30px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QCheckBox { spacing:8px; min-height:28px; }
QToolTip { background:{PANEL2}; color:{TEXT}; border:1px solid {BORDER}; }
QProgressBar { background:{PANEL2}; border:none; border-radius:4px; max-height:6px; }
QProgressBar::chunk { background:__ACCENT__; border-radius:4px; }
QPushButton { background:{PANEL2}; border:1px solid {BORDER}; border-radius:8px; padding:8px 14px; min-height:22px; }
QPushButton:hover { background:#2a2e38; }
"""
