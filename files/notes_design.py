"""Native Notes layout using the shared application palette."""
from functools import lru_cache
from pathlib import Path
import re
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QFont, QIcon, QIconEngine, QPixmap, QPalette, QPen, QPainter
from PySide6.QtWidgets import QApplication, QStyledItemDelegate, QStyle, QListView
from PySide6.QtSvg import QSvgRenderer
from lumen_i18n import tr


class NoteIcon(QIconEngine):
    def __init__(self,name):
        super().__init__();self.name=name
        self.svg=(Path(__file__).with_name('notes_icons')/(name+'.svg')).read_bytes()

    def clone(self):return NoteIcon(self.name)

    def paint(self,painter,rect,mode,state):
        palette=QApplication.palette()
        role=QPalette.HighlightedText if self.name=='save' else QPalette.Text
        color=palette.color(QPalette.Disabled if mode==QIcon.Disabled else QPalette.Active,role).name().encode()
        svg=self.svg.replace(b'#edece8',color).replace(b'#172c24',color)
        QSvgRenderer(svg).render(painter,QRectF(rect))

    def pixmap(self,size,mode,state):
        result=QPixmap(size);result.fill(Qt.transparent)
        painter=QPainter(result);self.paint(painter,result.rect(),mode,state);painter.end()
        return result


def icon(name):return QIcon(NoteIcon(name))


def apply(window, shell):
    from studio_design import font
    window.setFont(font(14))
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
    window.navigation.setFixedWidth(224) if not compact else window.navigation.setMaximumWidth(16777215)
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
            painter.setPen(Qt.NoPen); painter.setBrush(option.palette.color(QPalette.AlternateBase)); painter.drawRoundedRect(rect, 8, 8)
        if option.state & QStyle.State_HasFocus:
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(option.palette.color(QPalette.Link), 1)); painter.drawRoundedRect(rect.adjusted(1,1,-1,-1),8,8)
        title, _, detail = (index.data() or '').partition('\n')
        body = index.data(Qt.UserRole+1) or ''
        for y, text, size, color in [(12,title,13,QPalette.Text),(37,summary(body),11,QPalette.PlaceholderText),(58,detail,11,QPalette.PlaceholderText)]:
            font = QFont(option.font); font.setPixelSize(size); painter.setFont(font); painter.setPen(option.palette.color(color))
            text = painter.fontMetrics().elidedText(text, Qt.ElideRight, max(0,rect.width()-24))
            painter.drawText(QRectF(rect.x()+12,rect.y()+y,rect.width()-24,20), Qt.AlignLeft|Qt.AlignVCenter, text)
        painter.restore()
