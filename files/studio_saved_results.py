"""Saved outputs have their own selection and preview, independent of task controls."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument, QDesktopServices
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QSplitter, QPushButton, QMenu
from assistant import Transcript, SafeDocument
from lumen_i18n import tr
from preview import label
from studio_design import surface, font
from studio_tasks import TaskCards


class StudioSavedResults(QWidget):
    def __init__(self, workspace):
        super().__init__(); self.workspace = workspace; self.signature = None
        self.setObjectName('studioSavedResults'); surface(self)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = QFrame(); header.setObjectName('taskOverviewHead'); header.setMinimumHeight(121)
        head = QHBoxLayout(header); head.setContentsMargins(29, 24, 29, 22)
        intro = QVBoxLayout(); intro.addWidget(label(tr('Deine Ergebnisse.'), 'taskOverviewTitle'))
        subtitle = label(tr('Fertige Inhalte ansehen, speichern und weiterverwenden.'), 'taskMuted'); subtitle.setWordWrap(True); intro.addWidget(subtitle)
        head.addLayout(intro, 1)
        self.search = QLineEdit(); self.search.setObjectName('taskSearch'); self.search.setMaximumWidth(210)
        self.search.setPlaceholderText(tr('Ergebnisse finden')); self.search.setAccessibleName(tr('Ergebnisse finden')); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh); head.addWidget(self.search); root.addWidget(header)
        split = QSplitter(); split.setChildrenCollapsible(False); split.setHandleWidth(1)
        left = QWidget(); box = QVBoxLayout(left); box.setContentsMargins(20, 20, 20, 20)
        self.empty = label(tr('Noch keine fertigen Ergebnisse.'), 'taskMuted'); self.empty.setWordWrap(True); box.addWidget(self.empty)
        self.items = QListWidget(); self.items.setObjectName('taskList'); self.items.setMinimumWidth(160)
        self.items.setItemDelegate(TaskCards(self.items)); self.items.setAccessibleName(tr('Gespeicherte Ergebnisse'))
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); box.addWidget(self.items, 1); split.addWidget(left)
        right = QWidget(); content = QVBoxLayout(right); content.setContentsMargins(24, 20, 24, 20); content.setSpacing(16)
        self.title = label('', 'taskInspectorTitle'); self.title.setWordWrap(True); self.title.setTextFormat(Qt.PlainText); content.addWidget(self.title)
        self.preview = Transcript(); self.preview.setDocument(SafeDocument(self.preview)); self.preview.setObjectName('savedResultPreview')
        self.preview.setFont(font(14)); self.preview.setOpenLinks(False); self.preview.setAccessibleName(tr('Gespeichertes Ergebnis'))
        self.preview.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url) if url.scheme() in ('http', 'https') else None)
        content.addWidget(self.preview, 1)
        actions = QHBoxLayout(); self.controls = []
        for title, callback in [(tr('Speichern'), workspace.export_task), (tr('Als Dateiaktion'), workspace.task_to_file_action)]:
            button = QPushButton(title); button.clicked.connect(workspace.guarded(lambda fn=callback: self.use(fn)))
            actions.addWidget(button); self.controls.append(button)
        self.export = self.controls[0]; self.export.setObjectName('primary'); actions.addStretch()
        more = QPushButton('···'); more.setAccessibleName(tr('Weitere Ergebnisaktionen')); menu = QMenu(more)
        for title, callback in [(tr('Ins Wissen speichern'), workspace.task_to_knowledge), (tr('Als Ablauf speichern'), workspace.task_to_flow), (tr('Zum Auftrag'), self.open_task)]:
            menu.addAction(title, workspace.guarded(lambda fn=callback: self.use(fn)))
        self.conversation = menu.addAction(tr('Zum Gespräch'), workspace.guarded(lambda: self.use(workspace.open_task_conversation)))
        more.setMenu(menu); self.controls.append(more); actions.addWidget(more); content.addLayout(actions)
        split.addWidget(right); split.setStretchFactor(0, 0); split.setStretchFactor(1, 1); split.setSizes([330, 700]); root.addWidget(split, 1)
        self.items.currentItemChanged.connect(self.show_result)
        workspace.timer.timeout.connect(lambda: self.refresh() if self.isVisible() else None)
        self.show_result()

    def showEvent(self, event):
        super().showEvent(event); self.refresh()

    def refresh(self, *_):
        rows = self.workspace.store.rows("SELECT id,title,status,updated,error FROM tasks WHERE status='completed' AND trim(result)<>'' ORDER BY updated DESC LIMIT 200")
        query = self.search.text().strip().casefold()
        rows = [r for r in rows if query in r['title'].casefold()]
        signature = (query, rows)
        if signature == self.signature: return
        self.signature = signature; previous = self.selected()
        self.items.blockSignals(True); self.items.clear()
        for row in rows:
            item = QListWidgetItem(row['title']); item.setToolTip(row['title']); item.setData(Qt.UserRole, row['id']); item.setData(Qt.UserRole+1, row)
            self.items.addItem(item)
            if row['id'] == previous: self.items.setCurrentItem(item)
        if rows and self.items.currentItem() is None: self.items.setCurrentRow(0)
        self.items.blockSignals(False); self.empty.setVisible(not rows)
        self.empty.setText(tr('Keine Ergebnisse für diese Suche.') if query else tr('Noch keine fertigen Ergebnisse.'))
        self.show_result()

    def selected(self):
        item = self.items.currentItem(); return item.data(Qt.UserRole) if item else None

    def show_result(self, *_):
        task = self.workspace.store.task(self.selected()) if self.selected() else None
        self.title.setText(task['title'] if task else tr('Wähle ein Ergebnis'))
        self.preview.document().setMarkdown(task['result'] if task else '', QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
        self.conversation.setEnabled(bool(task and task['session']))
        for control in self.controls: control.setEnabled(bool(task))

    def use(self, callback):
        if self.selected(): callback(self.selected())

    def open_task(self, task_id):
        self.workspace.select_task(task_id); self.workspace.window.show_page(4)
