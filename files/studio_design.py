"""Native typography and theme icons shared by the Studio views."""
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon


@lru_cache(maxsize=1)
def family():
    names = []
    for path in sorted(Path(__file__).with_name('fonts').glob('*.woff2')):
        index = QFontDatabase.addApplicationFont(str(path))
        names.extend(QFontDatabase.applicationFontFamilies(index))
    return names[0] if names else 'Noto Sans'


def font(size=13, weight=QFont.Normal):
    value = QFont(family()); value.setPixelSize(size); value.setWeight(weight)
    return value


def surface(widget):
    widget.setFont(font())
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)


def icon(name):
    return QIcon.fromTheme(name, QIcon.fromTheme('text-x-generic'))
