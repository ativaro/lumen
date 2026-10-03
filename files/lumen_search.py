"""One native input for finding things and continuing a conversation in place."""
import html
import json
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    from lumen_crash import supervise
    supervise('search')

from lumen_i18n import worker_process, tr

from PyQt5.QtCore import QObject, Q_CLASSINFO, QEvent, QProcess, QRectF, QSize, QTimer, Qt, QUrl, pyqtSlot
from PyQt5.QtDBus import QDBus, QDBusConnection, QDBusMessage
from PyQt5.QtGui import QCursor, QDesktopServices, QIcon, QKeySequence, QPainter, QPalette
from PyQt5.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QShortcut, QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget

from assistant import ChatPanel
from lumen_actions import desktop_file


class SearchResultDelegate(QStyledItemDelegate):
    """Native rows with distinct title/path hierarchy and bounded, elided text."""
    def sizeHint(self, option, index):
        return QSize(300, 72)

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option); self.initStyleOption(styled, index)
        title, _, detail = index.data(Qt.DisplayRole).partition('\n')
        icon = QIcon(index.data(Qt.DecorationRole)); styled.text = ''; styled.icon = QIcon()
        painter.save(); painter.setRenderHint(QPainter.Antialiasing)
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, styled, painter, option.widget)
        rect = option.rect.adjusted(12, 10, -16, -10)
        tile = QRectF(rect.x(), rect.y() + 4, 44, 44)
        painter.setPen(Qt.NoPen); painter.setBrush(option.palette.alternateBase())
        painter.drawRoundedRect(tile, 10, 10)
        icon.paint(painter, tile.toRect().adjusted(8, 8, -8, -8))
        left = rect.x() + 60; width = max(0, rect.width() - 86)
        font = option.font; font.setPixelSize(15); painter.setFont(font)
        painter.setPen(option.palette.color(QPalette.Text))
        painter.drawText(left, rect.y() + 22, painter.fontMetrics().elidedText(title, Qt.ElideRight, width))
        font.setPixelSize(12); painter.setFont(font)
        painter.setPen(option.palette.color(QPalette.Dark))
        painter.drawText(left, rect.y() + 42, painter.fontMetrics().elidedText(detail, Qt.ElideMiddle, width))
        painter.drawText(rect.adjusted(rect.width() - 18, 0, 0, 0), Qt.AlignCenter, '›')
        painter.restore()


class SearchPalette(QWidget):
    def __init__(self, directory=None, backend=None, applications=None):
        super().__init__()
        self.setWindowTitle(tr('Lumen Suche')); self.setWindowIcon(QIcon.fromTheme('system-search'))
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(820, 640); self.setMinimumSize(540, 420)
        self.directory = str(directory or Path.home()); self.process = None; self.conversation = False
        self.generation = 0; self.scan_jobs = []; self.last_query = ''
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        surface = QFrame(); surface.setObjectName('searchSurface'); outer.addWidget(surface)
        box = QVBoxLayout(surface); box.setContentsMargins(26, 20, 26, 18); box.setSpacing(16)
        heading = QHBoxLayout(); title = QLabel(tr('Suche')); title.setObjectName('searchHeading'); heading.addWidget(title); heading.addStretch()
        self.reset_button = QPushButton(tr('Neue Suche')); self.reset_button.setObjectName('quiet')
        self.reset_button.setIcon(QIcon.fromTheme('view-refresh')); self.reset_button.clicked.connect(self.reset)
        close = QPushButton('×'); close.setObjectName('iconButton'); close.setFixedSize(36, 36); close.setToolTip(tr('Suche schließen · Esc')); close.setAccessibleName(tr('Suche schließen')); close.clicked.connect(self.hide); heading.addWidget(close)
        box.addLayout(heading)
        self.chat = ChatPanel(self.directory, backend=backend)
        self.chat.layout().setContentsMargins(0, 0, 0, 0)
        self.query = self.chat.composer
        self.chat.layout().removeWidget(self.query)
        self.query.setObjectName('searchComposer'); self.query.setFixedHeight(42); self.query.setPlaceholderText(tr('Dateien, Apps oder eine Frage …'))
        self.query.setAccessibleName(tr('Suchen oder mit Lumen sprechen'))
        input_surface = QFrame(); input_surface.setObjectName('searchInput')
        input_row = QHBoxLayout(input_surface); input_row.setContentsMargins(20, 8, 8, 8); input_row.setSpacing(12)
        input_row.addWidget(self.query, 1)
        voice = self.chat.context_tools.conversation
        if voice:
            input_row.addWidget(voice.button); input_row.addWidget(voice.interrupt_button)
            voice.started.connect(self.start_voice)
        self.go = QPushButton('↑'); self.go.setObjectName('searchSend'); self.go.setFixedSize(40, 40)
        self.go.setAccessibleName(tr('Ausgewählten Treffer öffnen oder Nachricht senden'))
        self.go.clicked.connect(self.submit); input_row.addWidget(self.go); box.addWidget(input_surface)
        if voice: box.addWidget(voice.indicator)
        self.hint = QLabel(tr('Enter öffnet den Treffer · Strg+Enter beginnt ein Gespräch hier')); self.hint.setObjectName('muted'); self.hint.setWordWrap(True)
        self.stack = QStackedWidget(); box.addWidget(self.stack, 1)
        self.results = QListWidget(); self.results.setObjectName('searchResults'); self.results.setAccessibleName(tr('Suchtreffer'))
        self.results.setItemDelegate(SearchResultDelegate(self.results))
        self.results.installEventFilter(self)
        self.stack.addWidget(self.results); self.stack.addWidget(self.chat)
        footer = QHBoxLayout(); footer.addWidget(self.reset_button)
        self.hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter); footer.addWidget(self.hint, 1); box.addLayout(footer)
        self.results.itemActivated.connect(lambda _: self.activate())
        self.results.itemClicked.connect(lambda _: self.activate())
        self.chat.heading.hide(); self.chat.new.hide(); self.chat.close_panel.hide(); self.chat.send_button.hide()
        for shortcut in self.chat.findChildren(QShortcut): shortcut.setEnabled(False)
        QShortcut(QKeySequence('Escape'), self, activated=self.hide)
        self.chat.context.hide(); self.chat.closeRequested.connect(self.hide)
        self.chat.backend.busyChanged.connect(self.busy_changed)
        self.chat.backend.failed.connect(lambda message: self.hint.setText(message))
        # The existing permission and question widgets remain part of the conversation.
        self.chat.options.setToolTip(tr('Gesprächsoptionen'))
        heading.insertWidget(2, self.chat.options); self.chat.options.hide()
        self.chat.layout().takeAt(0).layout().deleteLater()
        self.chat.dont_ask.hide(); self.chat.options.toggled.connect(self.chat.dont_ask.setVisible)
        self.debounce = QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(220)
        self.debounce.timeout.connect(self.search); self.query.textChanged.connect(self.changed)
        if applications is None:
            from gi.repository import Gio
            applications = [(a.get_display_name(), a.get_id()) for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()]
        self.applications = sorted(applications, key=lambda item: item[0].casefold())
        self.query.installEventFilter(self)
        self.search()

    def start_voice(self):
        self.cancel_scan(); self.conversation = True; self.stack.setCurrentWidget(self.chat); self.chat.options.show()
        self.hint.setText(tr('Sprachgespräch · automatische Gesprächsrunden · Mikrofon beendet sich beim Schließen'))

    def hideEvent(self, event):
        if self.chat.context_tools.conversation: self.chat.context_tools.conversation.stop()
        super().hideEvent(event)

    def recovery_state(self):
        return {'conversation': self.conversation, 'chat': self.chat.recovery_state()}

    def restore_recovery(self, state):
        self.chat.restore_recovery(state.get('chat', {}))
        self.conversation = bool(state.get('conversation'))
        self.stack.setCurrentWidget(self.chat if self.conversation else self.results)
        self.chat.options.setVisible(self.conversation)
        if not self.conversation: self.search()

    def present(self):
        # Re-read on activation too: a hidden singleton can outlive config-file watches.
        reload_theme = getattr(QApplication.instance(), 'reload_theme', None)
        if reload_theme: reload_theme()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.resize(min(820, area.width() - 40), min(640, area.height() - 90))
        self.move(area.x() + (area.width() - self.width()) // 2,
                  max(area.y() + 12, screen.geometry().y() + 80))
        self.show(); self.raise_(); self.activateWindow(); self.query.setFocus()

    def changed(self):
        if not self.conversation: self.debounce.start()

    def cancel_scan(self):
        self.generation += 1
        if self.process:
            self.process.kill(); self.process = None

    def item(self, title, detail, kind, value, icon, index=None):
        item = QListWidgetItem(QIcon.fromTheme(icon, QIcon.fromTheme('application-x-executable')), title + '\n' + detail)
        item.setData(Qt.UserRole, (kind, value))
        item.setToolTip('<qt>' + html.escape(title) + '<br>' + html.escape(detail) + '</qt>')
        self.results.insertItem(self.results.count() if index is None else index, item)

    def search(self):
        if self.conversation: return
        self.cancel_scan(); self.results.clear()
        query = self.query.toPlainText().strip()
        self.last_query = query; self.navigated = False
        if not query:
            self.hint.setText(tr('Apps und Dateien finden. Fragen werden im selben Fenster beantwortet.'))
            for title, identity in self.applications[:6]: self.item(title, tr('Anwendung'), 'app', identity, identity.removesuffix('.desktop'))
            self.results.setCurrentRow(0)
            return
        query = query[:300]
        self.hint.setText(tr('Enter öffnet den Treffer · Strg+Enter beginnt ein Gespräch hier'))
        question = '?' in query or query.lower().split()[0] in ('wie', 'warum', 'was', 'welche', 'welcher', 'wieso', 'kannst', 'erkläre', 'how', 'why', 'what', 'which', 'who', 'where', 'when', 'can', 'could', 'explain')
        if question:
            self.item(query, tr('Hier mit Lumen besprechen'), 'question', query, 'lumen')
        for title, identity in self.applications:
            if all(term in title.casefold() for term in query.casefold().split()): self.item(title, tr('Anwendung'), 'app', identity, identity.removesuffix('.desktop'))
            if self.results.count() >= 20: break
        if not any(self.results.item(i).data(Qt.UserRole)[0] == 'question' for i in range(self.results.count())):
            self.item(query, tr('Hier mit Lumen besprechen'), 'question', query, 'lumen')
        self.results.setCurrentRow(0)
        generation = self.generation; process = worker_process(self); self.process = process; self.scan_jobs.append(process)
        buffer = bytearray(); timer = QTimer(process); timer.setSingleShot(True)
        finished = False
        timer.timeout.connect(process.kill)
        def read():
            buffer.extend(bytes(process.readAllStandardOutput()))
            while b'\n' in buffer:
                line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
                if generation != self.generation: continue
                try: value = json.loads(line)
                except ValueError: continue
                if 'path' in value:
                    index = None if question else self.results.count() - 1
                    self.item(value['name'], str(Path(value['path']).parent), 'file', value['path'], 'folder' if value['directory'] else 'text-x-generic', index)
                    if not self.navigated: self.results.setCurrentRow(0)
        def done(code=0, *_):
            nonlocal finished
            if finished: return
            finished = True
            timer.stop(); read()
            if process in self.scan_jobs: self.scan_jobs.remove(process)
            if self.process is process:
                self.process = None
                self.hint.setText(tr('Enter öffnet · Strg+Enter fragt · Dateisuche in deinem persönlichen Ordner (begrenzt)'))
                if code: self.hint.setText(tr('Dateisuche unterbrochen. Apps und Gespräch sind weiterhin verfügbar.'))
                if self.results.count() and self.results.currentRow() < 0: self.results.setCurrentRow(0)
            process.deleteLater()
        process.readyReadStandardOutput.connect(read); process.finished.connect(done)
        process.errorOccurred.connect(lambda error: done(-1) if error == QProcess.FailedToStart else None)
        process.start(sys.executable, [str(Path(__file__).with_name('file_spaces.py'))])
        process.write((json.dumps(dict(root=self.directory, query=query, hidden=False, limit=100)) + '\n').encode()); process.closeWriteChannel(); timer.start(8000)

    def activate(self, ask=False):
        if self.chat.backend.busy: return
        query = self.query.toPlainText().strip()
        if self.conversation or ask:
            if not query: return
            self.cancel_scan(); self.conversation = True; self.stack.setCurrentWidget(self.chat)
            self.chat.options.show()
            self.hint.setText(tr('Gespräch · Antworten und Rückfragen bleiben in dieser Suche.'))
            self.chat.submit(query); self.query.setFocus(); return
        item = self.results.currentItem()
        if item is None:
            self.activate(True); return
        kind, value = item.data(Qt.UserRole)
        if kind == 'question': self.activate(True)
        else:
            try:
                if kind == 'app':
                    subprocess.Popen(['gio', 'launch', str(desktop_file(value))], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                elif not QDesktopServices.openUrl(QUrl.fromLocalFile(value)): raise ValueError(tr('Der Treffer konnte nicht geöffnet werden.'))
                self.hide()
            except Exception as error: self.hint.setText(str(error))

    def busy_changed(self, busy):
        self.reset_button.setEnabled(not busy)
        self.go.setEnabled(not busy)
        self.query.setReadOnly(busy)
        if not busy: self.query.setFocus()

    def reset(self):
        if self.chat.backend.busy: return
        self.chat.new_conversation(); self.conversation = False; self.query.clear()
        self.chat.options.setChecked(False); self.chat.options.hide()
        self.stack.setCurrentWidget(self.results); self.search(); self.query.setFocus()

    def submit(self, ask=False):
        self.debounce.stop()
        if not self.conversation and self.last_query != self.query.toPlainText().strip(): self.search()
        self.activate(ask)

    def eventFilter(self, obj, event):
        if obj is self.results and event.type() == QEvent.KeyPress:
            self.navigated = True
            if event.key() == Qt.Key_Escape: self.hide(); return True
        if obj is self.query and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
                self.submit(bool(event.modifiers() & Qt.ControlModifier)); return True
            if event.key() in (Qt.Key_Down, Qt.Key_Up) and not self.conversation:
                self.navigated = True
                self.results.setCurrentRow(max(0, min(self.results.count() - 1, self.results.currentRow() + (1 if event.key() == Qt.Key_Down else -1)))); return True
            if event.key() == Qt.Key_Escape: self.hide(); return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        event.ignore(); self.hide()

    def shutdown(self):
        self.debounce.stop(); self.cancel_scan()
        for process in self.scan_jobs[:]: process.kill(); process.waitForFinished(1000)
        self.chat.tracker.interrupt(); self.chat.context_tools.close(); self.chat.backend.shutdown()


class Activation(QObject):
    Q_CLASSINFO('D-Bus Interface', 'org.lumen.Search')
    def __init__(self, window): super().__init__(); self.window = window
    @pyqtSlot()
    def Activate(self): self.window.present()
    @pyqtSlot()
    def Voice(self):
        self.window.present()
        voice = self.window.chat.context_tools.conversation
        if voice and not voice.active: voice.toggle()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=tr('Lumen Suche'))
    parser.add_argument('--voice', action='store_true')
    parser.add_argument('--restore-state', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    from app import create_app
    app = create_app(); app.setApplicationName('lumen-search'); app.setApplicationDisplayName(tr('Lumen Suche')); app.setQuitOnLastWindowClosed(False)
    bus = QDBusConnection.sessionBus()
    if bus.isConnected() and not bus.registerService('org.lumen.Search'):
        reply = bus.call(QDBusMessage.createMethodCall('org.lumen.Search', '/Search', 'org.lumen.Search', 'Voice' if args.voice else 'Activate'), QDBus.Block, 3000)
        if reply.type() != QDBusMessage.ErrorMessage: return 0
        QMessageBox.warning(None, tr('Lumen Suche'), tr('Die laufende Suche konnte nicht aktiviert werden. Nach einem Update bitte die Suche neu starten; zuvor ungesendeten Text sichern.'))
        return 1
    window = SearchPalette(); activation = Activation(window)
    if args.restore_state:
        from lumen_crash import read_json
        try:
            state = read_json(args.restore_state)
            if not state or not isinstance(state.get('chat'), dict): raise ValueError(tr('Keine gültige Sitzungssicherung.'))
            window.restore_recovery(state)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            QMessageBox.warning(window, tr('Sitzung wiederherstellen'), str(error)); window.shutdown(); return 1
    if bus.isConnected(): bus.registerObject('/Search', activation, QDBusConnection.ExportAllSlots)
    app.aboutToQuit.connect(window.shutdown); window.present()
    from lumen_crash import attach
    attach(app, window, 'search')
    from setup_dialog import offer_setup
    QTimer.singleShot(250, activation.Voice if args.voice else lambda: offer_setup(window))
    return app.exec_()


if __name__ == '__main__': sys.exit(main())
