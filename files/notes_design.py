"""Native Notes counterpart of knowledge.css and the server's Graphit palette."""
from functools import lru_cache
from pathlib import Path
import re
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette, QPen, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QListView
from lumen_i18n import tr


def icon(name):
    return QIcon(str(Path(__file__).with_name('notes_icons') / (name+'.svg')))


def apply(window, shell):
    for path in Path(__file__).with_name('project_fonts').glob('*.woff2'):
        QFontDatabase.addApplicationFont(str(path))
    font = QFont('DM Sans 9pt'); font.setPixelSize(14); window.setFont(font)
    palette = window.palette()
    for role, color in [(QPalette.Window, '#191b1e'), (QPalette.Base, '#202326'),
                         (QPalette.AlternateBase, '#282c30'), (QPalette.Text, '#edece8'),
                         (QPalette.WindowText, '#edece8'), (QPalette.ButtonText, '#edece8'),
                         (QPalette.Button, '#202326'), (QPalette.Mid, '#363a3e'),
                         (QPalette.Midlight, '#282c30'), (QPalette.Dark, '#a4abae'),
                         (QPalette.Link, '#bbd2c5'), (QPalette.Highlight, '#3b5048'),
                         (QPalette.HighlightedText, '#edece8'), (QPalette.PlaceholderText, '#a4abae')]:
        palette.setColor(role, QColor(color))
    window.setPalette(palette); shell.setPalette(palette)
    window.resize(1440, 960)


def reflow(window):
    if not hasattr(window, 'notes_layout'): return
    compact = window.width() < 1100
    if getattr(window, '_notes_compact', None) == compact: return
    window._notes_compact = compact
    grid = window.notes_layout
    grid.removeWidget(window.navigation); grid.removeWidget(window.split)
    grid.setColumnStretch(0, 0 if not compact else 1); grid.setColumnStretch(1, 0 if compact else 1)
    grid.setRowStretch(0, 0 if compact else 1); grid.setRowStretch(1, 1 if compact else 0)
    window.navigation.setFixedWidth(180) if not compact else window.navigation.setMaximumWidth(16777215)
    if compact: window.navigation.setMinimumWidth(0)
    window.navigation.setMaximumHeight(150 if compact else 16777215)
    window.area_caption.setVisible(not compact);window.collection_label.setVisible(not compact)
    window.collections.setFlow(QListView.LeftToRight if compact else QListView.TopToBottom)
    window.collections.setWrapping(compact)
    window.collections.setMaximumHeight(70 if compact else 16777215)
    window.collections.setMinimumHeight(40 if compact else 80)
    grid.addWidget(window.navigation, 0, 0)
    grid.addWidget(window.split, 1 if compact else 0, 0 if compact else 1)
    window.split.setSizes([240, max(360, window.width()-460)])


@lru_cache(maxsize=512)
def summary(text):
    from notes_structure import document_parts
    from notes_rich_codec import SafeDocument
    body = document_parts(text, '')[3]
    body = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', lambda m:m[2] or m[1], body)
    document = SafeDocument(); document.setMarkdown(body[:2000])
    return ' '.join(document.toPlainText().split())[:75] or tr('Noch ohne Inhalt')


class NoteListDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index): return QSize(180, 88)

    def paint(self, painter, option, index):
        painter.save(); painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(0, 2, 0, -2)
        active = bool(option.state & QStyle.State_Selected)
        if active or option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen); painter.setBrush(QColor('#282c30')); painter.drawRoundedRect(rect, 8, 8)
        if option.state & QStyle.State_HasFocus:
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor('#bbd2c5'), 1)); painter.drawRoundedRect(rect.adjusted(1,1,-1,-1),8,8)
        title, _, detail = (index.data() or '').partition('\n')
        body = index.data(Qt.UserRole+1) or ''
        for y, text, size, color in [(12,title,13,'#edece8'),(37,summary(body),11,'#a4abae'),(58,detail,11,'#a4abae')]:
            font = QFont(option.font); font.setPixelSize(size); painter.setFont(font); painter.setPen(QColor(color))
            text = painter.fontMetrics().elidedText(text, Qt.ElideRight, max(0,rect.width()-24))
            painter.drawText(QRectF(rect.x()+12,rect.y()+y,rect.width()-24,20), Qt.AlignLeft|Qt.AlignVCenter, text)
        painter.restore()
