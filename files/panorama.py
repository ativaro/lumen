"""The same quiet app navigation in native Lumen windows."""
from pathlib import Path
import re
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QActionGroup, QIcon, QIconEngine, QPixmap, QPalette, QPainter
from PySide6.QtWidgets import QApplication, QToolBar, QMessageBox
from PySide6.QtSvg import QSvgRenderer
from lumen_i18n import tr


class AppIcon(QIconEngine):
    def __init__(self, key):
        super().__init__(); self.key = key
        name = {'lumen': 'mark', 'files': 'drive'}.get(key, key)
        self.svg = (Path(__file__).with_name('panorama_icons') / ('lumen-' + name + '.svg')).read_bytes()
        self.svg = re.sub(rb'<style>.*?</style>', b'', self.svg, flags=re.S)

    def clone(self): return AppIcon(self.key)

    def paint(self, painter, rect, mode, state):
        palette = QApplication.palette()
        group = QPalette.Disabled if mode == QIcon.Disabled else QPalette.Active
        text = palette.color(group, QPalette.Text).name().encode()
        accent = palette.color(group, QPalette.Highlight).name().encode()
        svg = self.svg.replace(b'<svg ', b'<svg color="' + text + b'" ', 1)
        svg = svg.replace(b'class="accent"', b'color="' + accent + b'"')
        svg = svg.replace(b'class="tint"', b'fill="' + palette.base().color().name().encode() + b'"')
        QSvgRenderer(svg).render(painter, QRectF(rect))

    def pixmap(self, size, mode, state):
        result = QPixmap(size); result.fill(Qt.transparent)
        painter = QPainter(result); self.paint(painter, result.rect(), mode, state); painter.end()
        return result


def install(window, current):
    if hasattr(window, 'panorama_bar'):
        return window.panorama_bar
    from lumen_apps import catalogue, launch
    if current == 'radio': current = 'meetings'
    entries = {key: (title, icon) for key, title, _, icon in catalogue(include_utilities=True)}
    bar = QToolBar(tr('Lumen Apps'), window)
    bar.setObjectName('panoramaApps'); bar.setAccessibleName(tr('Lumen Apps'))
    bar.setMovable(False); bar.setFloatable(False)
    bar.setIconSize(QSize(24, 24)); bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    group = QActionGroup(bar); group.setExclusive(True)

    def open_app(key):
        if key == current:
            return
        try:
            launch(key)
        except (ValueError, OSError) as error:
            QMessageBox.warning(window, 'Lumen', str(error))

    for key in ('lumen', 'wissen', 'workbench', 'code', 'meetings', 'files', 'inbox', 'vault'):
        title, fallback = entries[key]
        action = bar.addAction(QIcon(AppIcon(key)), title.removeprefix('Lumen '))
        action.setToolTip(title); action.setCheckable(True); group.addAction(action)
        action.setChecked(key == current)
        action.triggered.connect(lambda _=False, app=key: open_app(app))
    bar.addSeparator()
    action = bar.addAction(QIcon.fromTheme('view-grid'), tr('Alle Apps'))
    action.triggered.connect(lambda: open_app('apps'))
    selected = next((action for action in group.actions() if action.isChecked()), None)
    if selected:
        group.triggered.connect(lambda _: selected.setChecked(True))
    window.addToolBar(Qt.TopToolBarArea, bar)
    window.panorama_bar = bar
    return bar
