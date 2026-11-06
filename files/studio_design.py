"""Native typography and theme icons shared by the Studio views."""
from functools import lru_cache
from pathlib import Path
from weakref import ref
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QIconEngine, QPainter, QPalette, QPixmap
from lumen_qt import is_deleted


@lru_cache(maxsize=1)
def family():
    names = []
    for path in sorted(Path(__file__).with_name('fonts').glob('*.woff2')):
        index = QFontDatabase.addApplicationFont(str(path))
        names.extend(QFontDatabase.applicationFontFamilies(index))
    return names[0] if names else 'Noto Sans'


def font(size=14, weight=QFont.Normal):
    value = QFont(family()); value.setPixelSize(size); value.setWeight(weight)
    return value


def surface(widget):
    widget.setFont(font())
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)


def icon(name):
    return QIcon.fromTheme(name, QIcon.fromTheme('text-x-generic'))


class ButtonIcon(QIconEngine):
    """Keep primary glyphs on the text color, including after live theme changes."""
    def __init__(self, source, owner):
        super().__init__(); self.source = source; self.owner = owner

    def clone(self):
        return ButtonIcon(self.source, self.owner)

    def paint(self, painter, rect, mode, state):
        owner = self.owner()
        if owner is None or is_deleted(owner) or owner.objectName() not in ('primary', 'studioSave'):
            self.source.paint(painter, rect, Qt.AlignCenter, mode, state)
            return
        ratio = painter.device().devicePixelRatioF()
        image = self.source.pixmap(rect.size(), ratio, QIcon.Normal, state)
        group = QPalette.Disabled if mode == QIcon.Disabled else QPalette.Active
        tint = QPainter(image); tint.setCompositionMode(QPainter.CompositionMode_SourceIn)
        tint.fillRect(image.rect(), owner.palette().color(group, QPalette.ButtonText)); tint.end()
        painter.drawPixmap(rect, image)

    def pixmap(self, size, mode, state):
        image = QPixmap(size); image.fill(Qt.transparent)
        painter = QPainter(image); self.paint(painter, image.rect(), mode, state); painter.end()
        return image


def button_icon(name, owner):
    source = QIcon.fromTheme(name)
    return source if source.isNull() else QIcon(ButtonIcon(source, ref(owner)))
