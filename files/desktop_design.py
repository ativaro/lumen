"""Shared Desktop chrome: app heading and existing menu surfaces, no app launcher."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel
from studio_design import font

PAGE_MARGIN = 24
PAGE_SPACING = 16
NAV_WIDTH = 224
HEADER_HEIGHT = 76
WEB_TOKENS = {'desktop-page-margin': str(PAGE_MARGIN)+'px','desktop-spacing': str(PAGE_SPACING)+'px','desktop-nav-width': str(NAV_WIDTH)+'px','desktop-header-height': str(HEADER_HEIGHT)+'px'}


class AppHeader(QFrame):
    def __init__(self, title, subtitle='', parent=None):
        super().__init__(parent)
        self.setObjectName('desktopAppHeader')
        self.setMinimumHeight(HEADER_HEIGHT)
        self.setFont(font(14))
        self.setStyleSheet('''
QFrame#desktopAppHeader { background:transparent;border:0;border-bottom:1px solid palette(mid); }
QLabel#desktopAppTitle { background:transparent;color:palette(text);font-size:26px;font-weight:500; }
QLabel#desktopAppSubtitle { background:transparent;color:palette(placeholder-text);font-size:12px; }
''')
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, PAGE_SPACING); row.setSpacing(PAGE_SPACING)
        text = QVBoxLayout(); text.setContentsMargins(0, 0, 0, 0); text.setSpacing(4)
        self.title = QLabel(title); self.title.setObjectName('desktopAppTitle'); self.title.setWordWrap(True)
        self.subtitle = QLabel(subtitle); self.subtitle.setObjectName('desktopAppSubtitle'); self.subtitle.setWordWrap(True); self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.title); text.addWidget(self.subtitle); row.addLayout(text, 1)
        self.actions = QHBoxLayout(); self.actions.setContentsMargins(0, 0, 0, 0); self.actions.setSpacing(8); row.addLayout(self.actions)


MENU_STYLE = '''
QMenu { background:palette(base);color:palette(text);border:1px solid palette(mid);border-radius:8px;padding:6px;font-size:14px; }
QMenu::item { padding:8px 24px 8px 12px;min-height:20px;border:1px solid transparent;border-radius:6px; }
QMenu::item:selected { background:palette(midlight);color:palette(text);border-color:palette(highlight); }
QMenu::item:disabled { color:palette(placeholder-text); }
QMenu::separator { height:1px;background:palette(mid);margin:6px 12px; }
QMenuBar { background:palette(window);color:palette(text);border:0;padding:4px; }
QMenuBar::item { background:transparent;padding:8px 12px;border-radius:6px; }
QMenuBar::item:selected { background:palette(midlight); }
QComboBox QAbstractItemView { background:palette(base);color:palette(text);border:1px solid palette(mid);padding:6px;selection-background-color:palette(midlight);selection-color:palette(text);outline:none; }
QComboBox QAbstractItemView::item { min-height:28px;padding:4px 12px; }
'''
