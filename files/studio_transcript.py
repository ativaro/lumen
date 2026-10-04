"""Selectable, rounded native messages with safe Markdown and incremental updates."""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QTextDocument, QFont
from PySide6.QtWidgets import QScrollArea, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QSizePolicy
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
        font = QFont(self.font()); font.setPixelSize(15); self.setFont(font)
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
        self.box = QVBoxLayout(self.content); self.box.setContentsMargins(0, 12, 6, 0); self.box.setSpacing(24)
        self.box.addStretch(); self.setWidget(self.content)

    def setHtml(self, value): self.backing.setHtml(value)
    def toPlainText(self): return self.backing.toPlainText()
    def loadResource(self, kind, url): return None

    def textCursor(self):
        return next((row[2].textCursor() for row in self.rows if row[2].textCursor().hasSelection()), self.backing.textCursor())

    def entries(self, entries, action=False):
        empty = tr('Das Ergebnis erscheint hier.') if action else tr('## Was möchtest du erledigen?\n\nSchreib einen Gedanken oder füge eine Datei hinzu. Lumen hilft dir beim nächsten Schritt.')
        values = entries or [('assistant', empty, [])]
        while len(self.rows) > len(values):
            container, _, _, _ = self.rows.pop(); self.box.removeWidget(container); container.deleteLater()
        for index, entry in enumerate(values):
            role, value, activity = entry
            if index >= len(self.rows):
                container = QWidget(); outer = QHBoxLayout(container); outer.setContentsMargins(0, 0, 0, 0)
                bubble = QFrame(); bubble.setObjectName('studioUserMessage' if role == 'user' else 'studioAssistantMessage')
                layout = QVBoxLayout(bubble); layout.setContentsMargins(18, 14, 18, 14); layout.setSpacing(8)
                caption = label(tr('DU') if role == 'user' else 'LUMEN', 'studioSpeaker'); layout.addWidget(caption)
                body = MessageBody(); layout.addWidget(body)
                activity_label = label('', 'muted'); layout.addWidget(activity_label)
                if role == 'user': outer.addStretch(1)
                outer.addWidget(bubble, 8)
                self.box.insertWidget(index, container); self.rows.append((container, entry, body, activity_label))
                changed = True
            else:
                container, previous, body, activity_label = self.rows[index]
                # Session switches can change roles at the same position.
                if previous[0] != role:
                    self.clear(); return self.entries(entries, action)
                changed = previous != entry
                self.rows[index] = (container, entry, body, activity_label)
            if changed:
                document = SafeDocument(); document.setDefaultFont(body.font())
                document.setMarkdown(value, QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
                body.setHtml(document.toHtml()); body.fit()
                activity_label.setText(' · '.join(activity) + (' …' if activity else '')); activity_label.setVisible(bool(activity))
        self.box.activate()

    def clear(self):
        for container, _, _, _ in self.rows:
            self.box.removeWidget(container); container.deleteLater()
        self.rows.clear()
