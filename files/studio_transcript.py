"""Selectable, rounded native messages with safe Markdown and incremental updates."""
import math
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QDesktopServices, QTextDocument, QFont, QIcon
from PySide6.QtWidgets import QScrollArea, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QSizePolicy, QPushButton
from assistant import Transcript, SafeDocument
from lumen_i18n import tr
from preview import label


class MessageBody(Transcript):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('studioMessage'); self.setFrameShape(QFrame.NoFrame)
        self.setOpenLinks(False)
        self.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url) if url.scheme() in ('https', 'http') else None)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.setMinimumWidth(0)
        from ui_typography import metrics
        from studio_design import font
        self.setFont(font(max(13, metrics(parent.settings)['fontSize']-4)))
        self.document().contentsChanged.connect(self.fit)

    def fit(self):
        height = max(32, math.ceil(self.document().size().height()) + 8)
        if self.height() != height: self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event); self.fit()


class StudioTranscript(QScrollArea):
    def __init__(self, backing, parent=None):
        super().__init__(parent)
        self.backing = backing; self.rows = []
        self.setObjectName('studioTranscript'); self.setFrameShape(QFrame.NoFrame); self.setWidgetResizable(True)
        self.setAccessibleName(tr('Gespräch mit Lumen'))
        self.content = QWidget(); self.content.setObjectName('studioMessages')
        self.content.setMaximumWidth(960); self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.box = QVBoxLayout(self.content); self.box.setContentsMargins(0, 12, 6, 0); self.box.setSpacing(24)
        self.tail = QWidget(); self.tail.setFixedHeight(0); self.box.addWidget(self.tail)
        self.box.addStretch(); self.setWidget(self.content)
        self.turn_index = None; self.anchoring = True
        self.latest = QPushButton('↓', self.viewport()); self.latest.setObjectName('latestMessage')
        self.latest.setAccessibleName(tr('Zur neuesten Nachricht')); self.latest.setToolTip(tr('Zur neuesten Nachricht'))
        self.latest.setFixedSize(40, 36); self.latest.hide(); self.latest.clicked.connect(self.go_to_latest)
        self.viewport().installEventFilter(self); self.content.installEventFilter(self)
        self.verticalScrollBar().sliderPressed.connect(self.reading)
        self.verticalScrollBar().actionTriggered.connect(self.reading)
        self.verticalScrollBar().valueChanged.connect(self.update_latest)
        self.reflow = QTimer(self); self.reflow.setSingleShot(True); self.reflow.timeout.connect(self.position_turn)

        self.answer_actions = QFrame(self.content); self.answer_actions.setObjectName('answerActions')
        actions = QHBoxLayout(self.answer_actions); actions.setContentsMargins(0, 12, 0, 0)
        for title, icon, control in ((tr('Kopieren'), 'edit-copy', parent.copy), (tr('Für mich speichern'), 'bookmark-new', parent.save_note_button), (tr('Merk dir das'), 'view-history', parent.remember_button)):
            from studio_design import icon as tinted_icon
            button = QPushButton(); button.setToolTip(title); button.setAccessibleName(title); button.setFixedSize(30, 28)
            button.setObjectName('answerAction'); button.setIcon(tinted_icon(icon)); button.clicked.connect(control.click); actions.addWidget(button)
        actions.addStretch(); self.answer_actions.hide()
        parent.backend.busyChanged.connect(lambda busy: self.answer_actions.setEnabled(not busy))
        parent.backend.sessionChanged.connect(lambda _: self.entries([row[1] for row in self.rows], parent.action))

    def reading(self, *_):
        self.anchoring = False

    def eventFilter(self, source, event):
        if source is self.content and event.type() == QEvent.LayoutRequest and hasattr(self, 'reflow'): self.reflow.start(0)
        if source is self.viewport() and event.type() in (QEvent.Wheel, QEvent.TouchBegin, QEvent.MouseButtonPress): self.reading()
        return super().eventFilter(source, event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End, Qt.Key_Space): self.reading()
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'reflow'): self.reflow.start(0)

    def update_latest(self, *_):
        if not self.rows: self.latest.hide(); return
        end = self.rows[-1][0].geometry().bottom()
        self.latest.move((self.viewport().width() - self.latest.width()) // 2, self.viewport().height() - self.latest.height() - 12)
        self.latest.setVisible(end - self.verticalScrollBar().value() > self.viewport().height() + 24)
        self.latest.raise_()

    def go_to_latest(self):
        self.reading()
        if self.rows:
            self.verticalScrollBar().setValue(max(0, self.rows[-1][0].geometry().bottom() - self.viewport().height() + 12))
        self.update_latest()

    def position_turn(self, position=None, index=None):
        if index is not None: self.turn_index = index; self.anchoring = True
        if not self.rows: self.update_latest(); return
        self.box.activate()
        if self.turn_index is not None and self.turn_index < len(self.rows):
            start = self.rows[self.turn_index][0].y()
            end = self.rows[-1][0].geometry().bottom()
            self.tail.setFixedHeight(max(0, self.viewport().height() - (end - start) - self.box.spacing()))
            self.box.activate()
            if self.anchoring: self.verticalScrollBar().setValue(start)
            elif position is not None: self.verticalScrollBar().setValue(position)
        self.update_latest()
        if position is not None: self.reflow.start(0)

    def refresh_typography(self):
        from ui_typography import metrics
        self.box.setSpacing(metrics(self.parent().settings)['spacing'] + 8)
        entries = [row[1] for row in self.rows]
        self.clear(); self.entries(entries)

    def setHtml(self, value): self.backing.setHtml(value)
    def toPlainText(self): return self.backing.toPlainText()
    def loadResource(self, kind, url): return None

    def textCursor(self):
        return next((row[2].textCursor() for row in self.rows if row[2].textCursor().hasSelection()), self.backing.textCursor())

    def entries(self, entries, action=False):
        rich = getattr(self.parent(), 'rich_widget', None)
        self.answer_actions.setParent(self.content)
        empty = tr('Das Ergebnis erscheint hier.') if action else tr('## Was möchtest du erledigen?\n\nSchreib einen Gedanken oder füge eine Datei hinzu. Lumen hilft dir beim nächsten Schritt.')
        values = entries or [('assistant', empty, [])]
        while len(self.rows) > len(values):
            container, _, _, _ = self.rows.pop()
            if rich is not None and container.isAncestorOf(rich): rich.setParent(self.content)
            self.box.removeWidget(container); container.deleteLater()
        for index, entry in enumerate(values):
            role, value, activity = entry
            if index >= len(self.rows):
                container = QWidget(); outer = QHBoxLayout(container); outer.setContentsMargins(0, 0, 0, 0)
                bubble = QFrame(); bubble.setObjectName('studioUserMessage' if role == 'user' else 'studioAssistantMessage')
                layout = QVBoxLayout(bubble); layout.setContentsMargins(14, 10, 14, 10) if role == 'user' else layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
                caption = label('Lumen', 'studioSpeaker'); caption.setVisible(role != 'user'); layout.addWidget(caption)
                if role == 'assistant':
                    from answer_widget import AnswerBody
                    body = AnswerBody(self.parent().settings, self.parent())
                else: body = MessageBody(self.parent())
                layout.addWidget(body)
                activity_label = label('', 'muted'); layout.addWidget(activity_label)
                if role == 'assistant':
                    mark = label('✧', 'studioAvatar'); mark.setAlignment(Qt.AlignCenter); mark.setFixedSize(26,26)
                    outer.addWidget(mark, 0, Qt.AlignTop); outer.setSpacing(9)
                outer.addWidget(bubble, 8)
                self.box.insertWidget(index, container); self.rows.append((container, entry, body, activity_label))
                changed = True
            else:
                container, previous, body, activity_label = self.rows[index]
                # Session switches can change roles at the same position.
                if previous[0] != role:
                    self.clear(); return self.entries(entries, action)
                changed = previous != entry or (role == 'assistant' and body.scope != (self.parent().backend.session, index))
                self.rows[index] = (container, entry, body, activity_label)
            if changed:
                if role == 'assistant':
                    body.set_answer(value, (self.parent().backend.session, index))
                else:
                    document = SafeDocument(); document.setDefaultFont(body.font())
                    document.setMarkdown(value, QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
                    body.setHtml(document.toHtml())
                    from ui_typography import format_document
                    format_document(body.document(), self.parent().settings); body.fit()
                activity_label.setText(' · '.join(activity) + (' …' if activity else '')); activity_label.setVisible(bool(activity))
        last = next((i for i in range(len(values)-1, -1, -1) if values[i][0] == 'assistant' and values[i][1]), None)
        if last is not None: self.rows[last][2].parentWidget().layout().addWidget(self.answer_actions)
        self.answer_actions.setVisible(bool(entries) and last is not None)
        self.answer_actions.setEnabled(not self.parent().backend.busy)
        index = getattr(self.parent(), 'rich_message_index', None)
        if rich is not None:
            if index is not None and index < len(self.rows):
                self.rows[index][2].parentWidget().layout().insertWidget(2, rich)
                rich.setVisible(rich.controller.active)
            else:
                rich.setParent(self.content); rich.hide()
        self.box.activate()
        self.reflow.start(0)

    def clear(self):
        rich = getattr(self.parent(), 'rich_widget', None)
        if rich is not None: rich.setParent(self.content); rich.hide()
        self.answer_actions.setParent(self.content); self.answer_actions.hide()
        for container, _, _, _ in self.rows:
            self.box.removeWidget(container); container.deleteLater()
        self.rows.clear()
