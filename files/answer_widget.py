"""Native presentation of the shared inert Markdown answer blocks."""
import math
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QDesktopServices, QPalette, QTextCursor, QTextOption, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSizePolicy, QTextBrowser, QStyleOptionButton, QStyle)
from search_document import SafeDocument
from answer_blocks import blocks, table_html
from ui_typography import font, format_document, metrics
from lumen_i18n import tr


class AnswerText(QTextBrowser):
    def __init__(self, settings, parent=None):
        super().__init__(parent); self.settings = settings
        self.setDocument(SafeDocument(self)); self.setFont(font(settings))
        self.setFrameShape(QFrame.NoFrame); self.setObjectName('answerText')
        self.setStyleSheet('QTextBrowser#answerText { background: transparent; border: none; padding: 0; }')
        self.setOpenLinks(False); self.setOpenExternalLinks(False)
        self.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url) if url.scheme() in ('http', 'https') else None)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); self.setMinimumWidth(0)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.document().contentsChanged.connect(self.fit)
        self.table = None
        self.document().documentLayout().documentSizeChanged.connect(self.fit)

    def loadResource(self, kind, url): return None

    def show_html(self, value):
        self.setHtml(value); self.document().setDocumentMargin(0)
        format_document(self.document(), self.settings)
        cursor = QTextCursor(self.document().lastBlock()); block = cursor.blockFormat()
        block.setBottomMargin(0); cursor.setBlockFormat(block); self.fit()

    def fit(self):
        height = max(25, math.ceil(self.document().size().height())+4)
        if height != self.height(): self.setFixedHeight(height)

    def render_table(self):
        if self.table is None: return
        palette = self.palette()
        self.show_html(table_html(self.table, self.viewport().width(), palette.color(QPalette.PlaceholderText).name(),
            palette.color(QPalette.Mid).name(), metrics(self.settings)['fontSize']))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.table is not None: self.render_table()
        self.fit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange and hasattr(self, 'table'): self.render_table()


class AnswerCheck(QCheckBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked(): return
        option = QStyleOptionButton(); self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.HighlightedText), 1.8))
        path = QPainterPath(); path.moveTo(rect.left()+4, rect.center().y())
        path.lineTo(rect.left()+8, rect.bottom()-5); path.lineTo(rect.right()-4, rect.top()+5)
        painter.drawPath(path)


class AnswerBody(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent); self.settings = settings; self.items = []; self.scope = None; self.states = {}
        self.layout_box = QVBoxLayout(self); self.layout_box.setContentsMargins(0, 0, 0, 0)
        self.layout_box.setSpacing(16); self.layout_box.setAlignment(Qt.AlignTop); self.setMinimumWidth(0)
        self.setStyleSheet('''QFrame#answerCard { background: palette(base); border: 1px solid palette(mid); border-radius: 12px; }
            QLabel#answerTitle { font-weight: 600; background: transparent; border: none; }
            QLabel#answerCount { color: palette(placeholder-text); font-size: 12px; background: transparent; border: none; }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid palette(placeholder-text); border-radius: 5px; background: transparent; }
            QCheckBox::indicator:checked { background: palette(highlight); border-color: palette(highlight); }
            QCheckBox::indicator:focus { border: 2px solid palette(link); }''')

    def textCursor(self):
        return next((w.textCursor() for w in self.findChildren(AnswerText) if w.textCursor().hasSelection()), QTextCursor())

    def set_answer(self, text, scope):
        parsed = blocks(text)
        if scope != self.scope:
            self.states.clear(); self.scope = scope
            while self.items:
                widget, _ = self.items.pop(); self.layout_box.removeWidget(widget); widget.deleteLater()
        while len(self.items) > len(parsed):
            widget, _ = self.items.pop(); self.layout_box.removeWidget(widget); widget.deleteLater()
        for index, block in enumerate(parsed):
            if index < len(self.items) and self.items[index][1] == block: continue
            if index < len(self.items):
                old, _ = self.items[index]; self.layout_box.removeWidget(old); old.deleteLater()
            widget = self.make_block(block)
            self.layout_box.insertWidget(index, widget)
            if index < len(self.items): self.items[index] = widget, block
            else: self.items.append((widget, block))

    def browser(self, body, parent):
        widget = AnswerText(self.settings, parent); widget.show_html(body); return widget

    def make_block(self, block):
        if block['kind'] == 'text': return self.browser(block['body'], self)
        card = QFrame(self); card.setObjectName('answerCard')
        box = QVBoxLayout(card); box.setContentsMargins(16, 14, 16, 14); box.setSpacing(12); box.setAlignment(Qt.AlignTop)
        head = QHBoxLayout(); title = QLabel(block['title']); title.setTextFormat(Qt.PlainText); title.setObjectName('answerTitle')
        title_font = font(self.settings); title_font.setPixelSize(metrics(self.settings)['fontSize']-2)
        title.setFont(title_font); head.addWidget(title); head.addStretch(); box.addLayout(head)
        if block['kind'] == 'checklist':
            count = QLabel(); count.setObjectName('answerCount'); head.addWidget(count); checks = []
            def recount(): count.setText(tr('{0} von {1}', sum(c.isChecked() for c in checks), len(checks)))
            for item in block['items']:
                row = QHBoxLayout(); row.setContentsMargins(min(item['indent'], 4)*16, 0, 0, 0)
                check = AnswerCheck(); check.setAccessibleName(item['text']); check.setObjectName('answerCheck')
                check.setChecked(self.states.get(item['key'], item['checked'])); checks.append(check)
                check.toggled.connect(lambda value, key=item['key']: (self.states.__setitem__(key, value), recount()))
                row.addWidget(check, 0, Qt.AlignTop); row.addWidget(self.browser(item['body'], card), 1); box.addLayout(row)
            recount()
            hint = QLabel(tr('Abhaken führt keine Aktion aus.')); hint.setWordWrap(True); hint.setObjectName('answerCount'); box.addWidget(hint)
        else:
            body = block['body'] if block['kind'] != 'table' else ''
            widget = self.browser(body, card)
            if block['kind'] == 'table': widget.table = block; widget.render_table()
            if block['kind'] == 'code':
                f = widget.font(); f.setFamily('monospace'); widget.setFont(f)
            box.addWidget(widget)
        return card
