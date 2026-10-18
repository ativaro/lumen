"""Lumen's explicit results alongside the conversation, using Files workers."""
from pathlib import Path
import html
import json
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QComboBox, QSplitter, QPushButton, QMenu, QFrame, QTabBar, QStackedWidget, QSizePolicy, QDialog
from assistant import Transcript, SafeDocument
from core import file_kind
from gallery import Gallery, ImageLoader
from gallery_widgets import Filmstrip
from lumen_i18n import tr
from preview import Preview, label
from studio_chat import icon_button
from studio_design import surface, icon, font


def model_stream(messages, turn, *, include_text=True):
    blocks = []
    states = {'pending': tr('Wartet'), 'running': tr('Läuft'), 'completed': tr('Fertig'), 'error': tr('Fehlgeschlagen')}
    for message in messages:
        info = message.get('info', {})
        if info.get('role') != 'assistant' or info.get('parentID', '') != turn: continue
        for part in message.get('parts', []):
            kind = part.get('type')
            if (kind == 'reasoning' or kind == 'text' and include_text) and part.get('text') and not part.get('synthetic'):
                document = SafeDocument()
                document.setMarkdown(part['text'], QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
                body = document.toHtml().split('<body', 1)[1].split('>', 1)[1].rsplit('</body>', 1)[0]
                title = tr('Denktext') if kind == 'reasoning' else tr('Modelltext')
                blocks.append('<h3>' + html.escape(title) + '</h3>' + body)
            elif kind == 'tool':
                state = part.get('state', {})
                title = tr('Werkzeug · {0} · {1}', part.get('tool', ''), states.get(state.get('status'), state.get('status', '')))
                blocks.append('<h3>' + html.escape(title) + '</h3>')
                if state.get('title'): blocks.append('<p>' + html.escape(state['title']) + '</p>')
                for key in ('input', 'output', 'error'):
                    value = state.get(key)
                    if value in (None, '', {}): continue
                    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
                    blocks.append('<pre>' + html.escape(text) + '</pre>')
        if error := info.get('error'):
            detail = error.get('data', {}).get('message') or error.get('name', tr('Fehlgeschlagen'))
            blocks.append('<p>' + html.escape(detail) + '</p>')
    return ''.join(blocks)


class StudioPreview(Preview):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setContentsMargins(20, 8, 20, 20)
        self.layout.itemAt(0).widget().hide()
        self.note.hide()
        self.filmstrip = Filmstrip(ImageLoader(self, max_side=192, cache_limit=16), self)
        self.filmstrip.chosen.connect(self.choose_image)
        self.layout.insertWidget(2, self.filmstrip); self.filmstrip.hide()
        self.openImage.connect(self.open_gallery)
        actions = QHBoxLayout()
        for control in (self.open_button, self.edit_button):
            self.layout.removeWidget(control); actions.addWidget(control)
        self.layout.addLayout(actions)

    def photo_layout(self, enabled):
        super().photo_layout(enabled)
        if hasattr(self, 'filmstrip'):
            self.layout.removeWidget(self.filmstrip); self.layout.insertWidget(2, self.filmstrip)
            self.filmstrip.setVisible(enabled and len(self.filmstrip.paths) > 1)

    def choose_image(self, index):
        self.show_path(self.filmstrip.paths[index])

    def open_gallery(self, path, edit):
        paths = self.filmstrip.paths or [path]
        gallery = Gallery(paths, path, self)
        if edit: gallery.editor_button.setChecked(True)
        gallery.exec(); gallery.deleteLater()
        self.filmstrip.invalidate(path)
        self.show_path(path)

    def shutdown(self):
        self.cancel(); self.filmstrip.stop()


class StudioSurface(QWidget):
    def __init__(self, chat, parent=None, *, conversation_focus=False):
        super().__init__(parent)
        self.conversation_focus = conversation_focus
        self.chat = chat; self.paths = []; self.preview_wanted = True; self.narrow_preview = False
        self.work_busy = False
        self.answer_key = None
        self.setObjectName('studioWorkbench'); surface(self)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = QFrame(); header.setObjectName('studioWorkHead'); header.setFixedHeight(68)
        head = QHBoxLayout(header); head.setContentsMargins(26, 0, 24, 0); head.setSpacing(14)
        chat.heading.setObjectName('studioWorkTitle'); chat.heading.setWordWrap(False)
        chat.heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred); chat.heading.setMaximumWidth(380); head.addWidget(chat.heading)
        self.directory = label(Path(chat.backend.directory).name, 'studioWorkContext'); head.addWidget(self.directory, 1)
        self.status_label = label(tr('Bereit'), 'studioWorkStatus'); head.addWidget(self.status_label)
        for control, title, name in [(chat.new, tr('Neues Gespräch'), 'list-add'), (chat.options, tr('Optionen'), 'view-more-symbolic')]:
            control.setText(''); control.setIcon(icon(name)); control.setObjectName('studioIcon')
            control.setToolTip(title); control.setAccessibleName(title); control.setFixedSize(32, 32); head.addWidget(control); control.show()
        chat.heading.show(); root.addWidget(header)
        # Execution remains editable in the existing options panel.
        chat.options_box.layout().insertWidget(0, chat.execution)
        self.split = QSplitter(Qt.Horizontal); self.split.setChildrenCollapsible(False); self.split.setHandleWidth(1)
        root.addWidget(self.split, 1); self.split.addWidget(chat); chat.setMinimumWidth(320)
        self.pane = QWidget(); self.pane.setObjectName('studioPreviewPane'); self.pane.setMinimumWidth(0)
        layout = QVBoxLayout(self.pane); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        toolbar = QFrame(); toolbar.setObjectName('studioResultToolbar'); toolbar.setFixedHeight(49)
        top = QHBoxLayout(toolbar); top.setContentsMargins(22, 0, 18, 0)
        self.result_tabs = QTabBar(); self.result_tabs.setObjectName('studioResultTabs'); self.result_tabs.setDrawBase(False)
        self.result_tabs.addTab(tr('Ergebnis')); self.result_tabs.addTab(tr('Arbeitsschritte')); top.addWidget(self.result_tabs)
        top.addStretch(); self.heading = label(tr('Vorschau'), 'studioResultCaption'); top.addWidget(self.heading)
        self.pane_heading = top
        self.close_preview = icon_button(tr('Vorschau schließen'), 'window-close', self.close_pane)
        self.close_preview.setFixedSize(26, 26); top.addWidget(self.close_preview); layout.addWidget(toolbar)
        self.choice = QComboBox(); self.choice.setAccessibleName(tr('Datei in der Vorschau'))
        self.choice.setMinimumContentsLength(10); self.choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.choice.activated.connect(self.choose); layout.addWidget(self.choice)
        self.result_pages = QStackedWidget(); layout.addWidget(self.result_pages, 1)
        self.stage = QWidget(); self.stage.setObjectName('studioPaperArea')
        stage = QHBoxLayout(self.stage); stage.setContentsMargins(28, 24, 28, 24)
        self.paper = QFrame(); self.paper.setObjectName('studioPaper'); self.paper.setMaximumWidth(900)
        paper = QVBoxLayout(self.paper); paper.setContentsMargins(0, 0, 0, 0); paper.setSpacing(22)
        topline = QHBoxLayout(); topline.addWidget(label('LUMEN', 'studioPaperBrand')); topline.addStretch()
        self.result_status = label('', 'studioPaperMeta'); topline.addWidget(self.result_status); paper.addLayout(topline)
        self.answer = Transcript(); self.answer.setDocument(SafeDocument(self.answer)); self.answer.setObjectName('studioResult')
        self.answer.setFont(font(14)); self.answer.setAccessibleName(tr('Aktuelle Antwort von Lumen')); self.answer.setOpenLinks(False)
        from PySide6.QtGui import QDesktopServices
        self.answer.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url) if url.scheme() in ('http', 'https') else None)
        paper.addWidget(self.answer, 1); stage.addWidget(self.paper, 1)
        self.preview = StudioPreview(); stage.addWidget(self.preview, 1)
        self.result_pages.addWidget(self.stage)
        self.execution_detail = Transcript(); self.execution_detail.setDocument(SafeDocument(self.execution_detail))
        self.execution_detail.setOpenLinks(False); self.execution_detail.setObjectName('studioExecution'); self.execution_detail.setFont(font(14))
        self.execution_detail.setAccessibleName(tr('Arbeitsschritte des Gesprächs')); self.result_pages.addWidget(self.execution_detail)
        self.result_tabs.currentChanged.connect(self.result_pages.setCurrentIndex)
        dock = QFrame(); dock.setObjectName('studioResultDock')
        self.actions = QHBoxLayout(dock); self.actions.setContentsMargins(22, 14, 22, 14); self.actions.setSpacing(9)
        self.actions.addWidget(label(tr('Ergebnis verwenden'), 'studioDockCaption')); self.actions.addStretch()
        self.copy_answer = icon_button(tr('Kopieren'), 'edit-copy', chat.copy.click)
        self.save_answer = QPushButton(tr('Speichern')); self.save_answer.setIcon(icon('document-save')); self.save_answer.setObjectName('studioSave')
        self.result_menu = QMenu(self.save_answer)
        self.result_menu.addAction(tr('Für mich speichern'), lambda: chat.capture_knowledge(False, text=self.result_text()))
        self.result_menu.addAction(tr('Merk dir das'), lambda: chat.capture_knowledge(True, text=self.result_text()))
        self.save_answer.setMenu(self.result_menu)
        self.actions.addWidget(self.save_answer); layout.addWidget(dock)
        self.split.addWidget(self.pane); self.split.setStretchFactor(0, 1); self.split.setStretchFactor(1, 1)
        self.split.setSizes([560, 560]); self.pane.hide()
        if conversation_focus:
            self.focus_conversation(layout, dock)
        self.preview.filmstrip.chosen.connect(lambda i: self.choice.setCurrentIndex(
            self.choice.findData(self.preview.filmstrip.paths[i])))
        chat.resultChanged.connect(self.set_result); chat.previewRequested.connect(self.toggle_preview)
        chat.answerChanged.connect(self.show_answer); chat.backend.busyChanged.connect(self.show_answer)
        chat.backend.busyChanged.connect(self.follow_work)
        chat.backend.completed.connect(self.finish_work)
        chat.backend.statusChanged.connect(lambda _: self.update_execution())
        chat.backend.sessionChanged.connect(lambda _: self.update_execution())
        self.set_result(chat.presentation)
        self.show_answer()
        self.follow_work(chat.backend.busy)

    def focus_conversation(self, layout, dock):
        self.result_tabs.hide()
        self.heading.setText(tr('Arbeitsschritte'))
        self.pane_heading.removeWidget(self.heading); self.pane_heading.insertWidget(0, self.heading)
        self.pane.setAccessibleName(tr('Arbeitsschritte des Gesprächs'))
        self.close_preview.setAccessibleName(tr('Arbeitsschritte schließen'))
        self.close_preview.setToolTip(tr('Arbeitsschritte schließen'))
        self.chat.preview_button.setAccessibleName(tr('Arbeitsschritte anzeigen'))
        self.chat.preview_button.setToolTip(tr('Arbeitsschritte anzeigen'))
        self.chat.preview_button.setIcon(icon('view-list-details'))
        self.result_pages.removeWidget(self.stage)
        self.stage.hide(); self.stage.setParent(self.chat.parking)
        layout.removeWidget(dock)
        self.actions.itemAt(0).widget().hide()
        self.chat.layout().insertWidget(self.chat.layout().indexOf(self.chat.composer_surface), dock)
        self.files_button = QPushButton(tr('Dateien anzeigen'))
        self.files_button.setIcon(icon('document-open')); self.files_button.clicked.connect(self.open_files)
        self.actions.insertWidget(0, self.files_button); self.files_button.hide()
        self.file_dialog = QDialog(self)
        self.file_dialog.setWindowTitle(tr('Lumen · Dateien aus dem Gespräch'))
        self.file_dialog.resize(860, 680)
        files = QVBoxLayout(self.file_dialog)
        layout.removeWidget(self.choice); files.addWidget(self.choice); files.addWidget(self.preview)
        self.file_dialog.finished.connect(lambda _: self.preview.shutdown())
        self.split.setStretchFactor(0, 1); self.split.setStretchFactor(1, 0)
        self.pane.setMaximumWidth(480)

    def open_files(self):
        if not self.paths: return
        self.file_dialog.show(); self.file_dialog.raise_(); self.file_dialog.activateWindow()
        self.choose(self.choice.currentIndex())

    def shutdown(self):
        if self.conversation_focus: self.file_dialog.close()
        self.preview.shutdown()

    def bind_workspace(self, workspace):
        self.workspace = workspace
        self.export_answer = self.result_menu.addAction(tr('Als Datei speichern …'), workspace.guarded(lambda: self.use_task(workspace.export_task)))
        self.reuse_answer = QPushButton(tr('Als Dateiaktion')); self.reuse_answer.setIcon(icon('system-run'))
        self.reuse_answer.clicked.connect(workspace.guarded(lambda: self.use_task(workspace.task_to_file_action)))
        self.actions.addWidget(self.reuse_answer)
        more = icon_button(tr('Weitere Ergebnisaktionen'), 'view-more-symbolic', lambda: None)
        menu = QMenu(more); menu.addAction(tr('Kopieren'), self.copy_answer.click)
        menu.addAction(tr('Als Ablauf speichern'), workspace.guarded(lambda: self.use_task(workspace.task_to_flow)))
        self.task_link = QPushButton(tr('Ausführung prüfen')); self.task_link.clicked.connect(workspace.guarded(self.open_task))
        self.task_link.hide(); self.task_link.setParent(self)
        self.task_link_action = menu.addAction(tr('Ausführung prüfen'), self.task_link.click)
        more.setMenu(menu); self.actions.addWidget(more)
        self.chat.tracker.changed.connect(self.update_task_actions)
        self.chat.backend.busyChanged.connect(self.update_task_actions)
        self.result_menu.aboutToShow.connect(self.update_task_actions)
        self.update_task_actions()

    def result_text(self):
        if self.conversation_focus:
            return self.chat.transcript.textCursor().selectedText().replace('\u2029', '\n') or self.chat.last_answer
        return self.answer.textCursor().selectedText().replace('\u2029', '\n') or self.chat.last_answer

    def update_task_actions(self, *_):
        task = self.chat.answer_task() if not self.chat.backend.busy else None
        show_text = self.conversation_focus or not self.paths or self.choice.currentData() is None
        self.export_answer.setEnabled(bool(task)); self.reuse_answer.setVisible(show_text); self.reuse_answer.setEnabled(bool(task))
        self.task_link_action.setEnabled(bool(task)); self.task_link.setEnabled(bool(task))
        self.update_execution()

    def update_execution(self):
        from lumen_store import STATES
        task = self.chat.tracker.store.task(self.chat.tracker.task_id) if self.chat.tracker.task_id else None
        if task and task['session'] != self.chat.backend.session: task = None
        if not self.chat.backend.busy: task = self.chat.answer_task() or task
        self.directory.setText(Path(self.chat.backend.directory).name or '/')
        self.directory.setToolTip(self.chat.backend.directory)
        status = STATES.get(task['status'], task['status']) if task else tr('Läuft') if self.chat.backend.busy else tr('Bereit')
        self.status_label.setText('•  '+status)
        backend = self.chat.backend
        turn = backend.message_id or next((m.get('info', {}).get('parentID', '') for m in reversed(backend.messages)
            if m.get('info', {}).get('role') == 'assistant'), '')
        key = (backend.session, turn)
        if getattr(backend, 'execution', 'local') == 'server':
            content = '<p>' + tr('Der Server stellt hier keinen Live-Modellverlauf bereit.') + '</p>'
        else:
            content = model_stream(backend.messages, turn, include_text=not self.conversation_focus)
            if not content:
                content = '<p>' + (tr('Warte auf Modellausgabe …') if backend.busy else tr('Noch kein Modellverlauf für dieses Gespräch.')) + '</p>'
        if (key, content) == getattr(self, 'rendered_execution', None): return
        scroll = self.execution_detail.verticalScrollBar(); position = scroll.value()
        follow = position >= scroll.maximum() - 30 or key != getattr(self, 'execution_key', None)
        self.execution_key = key; self.rendered_execution = (key, content)
        self.execution_detail.setHtml(content)
        scroll.setValue(scroll.maximum() if follow else position)

    def use_task(self, callback):
        task = self.chat.answer_task() if not self.chat.backend.busy else None
        if not task: raise ValueError(tr('Zu dieser Antwort ist kein gespeicherter Auftrag verfügbar.'))
        callback(task['id'])

    def open_task(self):
        from lumen_detail_routes import open_tasks
        self.use_task(open_tasks)

    def follow_work(self, busy):
        if self.conversation_focus: return
        if busy and not self.work_busy: self.result_tabs.setCurrentIndex(1)
        self.work_busy = busy

    def finish_work(self, success, text):
        if self.conversation_focus: return
        if not success or not text.strip(): return
        from studio_results import from_messages
        backend = self.chat.backend
        result = from_messages([m for m in backend.messages if m.get('info', {}).get('parentID') == backend.message_id])
        if not result or not result['paths']:
            index = self.choice.findData(None)
            if index >= 0: self.choice.setCurrentIndex(index); self.choose(index)
        self.result_tabs.setCurrentIndex(0)

    def show_answer(self, *_):
        if self.conversation_focus:
            self.copy_answer.setEnabled(bool(self.chat.last_answer))
            self.save_answer.setEnabled(bool(self.chat.last_answer) and not self.chat.backend.busy)
            if hasattr(self, 'workspace'): self.update_task_actions()
            else: self.update_execution()
            return
        key = getattr(self.chat, '_answer_key', None)
        text = self.chat.last_answer
        if (key, text) != getattr(self, 'rendered_answer', None):
            position = self.answer.verticalScrollBar().value() if key == self.answer_key else 0
            self.answer_key = key; self.rendered_answer = (key, text)
            self.answer.document().setMarkdown(text or tr('## Platz für dein Ergebnis\n\nAntworte links im Gespräch. Hier bleibt die aktuelle Antwort griffbereit; Dateien zeigt Lumen nach ausdrücklicher Bereitstellung.'),
                QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
            from ui_typography import format_document, metrics
            format_document(self.answer.document(), self.chat.settings)
            self.answer.document().setDefaultFont(font(max(14, metrics(self.chat.settings)['fontSize']-3)))
            self.answer.verticalScrollBar().setValue(position)
        if self.paths and text and self.choice.findData(None) < 0: self.choice.addItem(tr('Antwort'), None)
        show_text = not self.paths or self.choice.currentData() is None
        self.paper.setVisible(show_text)
        self.answer.setVisible(show_text)
        self.preview.setVisible(not show_text)
        self.result_status.setText(tr('Lumen arbeitet …') if self.chat.backend.busy else tr('Aktuelle Antwort') if text else tr('Noch kein Ergebnis'))
        self.copy_answer.setEnabled(bool(text))
        self.save_answer.setEnabled(bool(text) and not self.chat.backend.busy)
        self.copy_answer.hide(); self.save_answer.setVisible(show_text)
        if hasattr(self, 'workspace'): self.update_task_actions()

    def set_result(self, result):
        paths = result['paths'] if result else []
        if not self.conversation_focus:
            self.heading.setText(result['title'] if result and result['title'] else tr('Ergebnis'))
        self.paths = paths; self.choice.clear()
        if paths and not self.conversation_focus: self.result_tabs.setCurrentIndex(0)
        for path in paths: self.choice.addItem(Path(path).name or '/', path)
        images = [p for p in paths if file_kind(p) == 'image']
        self.preview.filmstrip.stop()
        self.preview.filmstrip.loader.cache.clear()
        self.preview.filmstrip.select([], -1)
        self.preview.filmstrip.select(images, 0 if images else -1)
        if not self.conversation_focus:
            self.preview_wanted = True; self.narrow_preview = False
        self.preview.path = None
        self.update_visibility()
        if not paths:
            self.preview.clear(); self.preview.shutdown()
            self.preview.title.setText(tr('Ergebnisse von Lumen'))
            self.preview.detail.setText(tr('Hier zeigt Lumen gefundene und erstellte Dateien.'))
            self.preview.show_message(tr('Bitte Lumen, dir etwas zu zeigen.'))
        self.choice.setVisible(bool(paths))
        if self.conversation_focus:
            self.files_button.setVisible(bool(paths))
            if not paths: self.file_dialog.reject()
            elif self.file_dialog.isVisible(): self.choose(self.choice.currentIndex())
        self.show_answer()

    def choose(self, index):
        path = self.choice.itemData(index)
        self.show_answer()
        if path:
            self.preview.show_path(path)
            images = self.preview.filmstrip.paths
            self.preview.filmstrip.select(images, images.index(path) if path in images else -1)
        else: self.preview.shutdown()

    def toggle_preview(self):
        self.preview_wanted = not self.pane.isVisible(); self.narrow_preview = self.preview_wanted
        self.update_visibility()

    def close_pane(self):
        self.preview_wanted = False; self.narrow_preview = False; self.update_visibility()
        self.preview.shutdown(); self.chat.composer.setFocus()

    def update_visibility(self):
        wide = self.width() >= 900
        show = self.preview_wanted and (wide or self.narrow_preview)
        was_visible = self.pane.isVisible()
        self.pane.setVisible(show); self.chat.setVisible(self.conversation_focus or wide or not show)
        if self.conversation_focus:
            if wide and not getattr(self, 'conversation_sized', False):
                self.split.setSizes([max(320, self.width()-320), 320]); self.conversation_sized = True
        else:
            if show and (not was_visible or self.preview.path is None) and self.paths: self.choose(self.choice.currentIndex())
            if not show: self.preview.shutdown()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'pane'): self.update_visibility()
