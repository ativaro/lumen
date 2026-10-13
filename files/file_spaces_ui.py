"""Native library/source controls and asynchronous virtual file views."""
import json
import os
from pathlib import Path
import sys

from lumen_i18n import worker_process, tr

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Qt, QModelIndex, QDateTime, QItemSelectionModel
from PySide6.QtGui import QIcon, QStandardItem
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget)

from core import size_text
from file_spaces import Catalog, DEFAULTS, LIBRARY, SHELF, canonical, virtual
from network import ConnectDialog, Network, display_url, is_network_address, server_label


def button(text, callback):
    item = QPushButton(text)
    item.clicked.connect(callback)
    return item


class LibraryDialog(QDialog):
    def __init__(self, catalog, library, parent):
        super().__init__(parent)
        self.catalog, self.library, self.saved = catalog, library, None
        self.setWindowTitle(tr('Bibliothek bearbeiten') if library else tr('Neue Bibliothek'))
        self.resize(740, 420)
        layout = QVBoxLayout(self)
        self.name = QLineEdit(library['name'] if library else '')
        form = QFormLayout(); form.addRow(tr('Name'), self.name); layout.addLayout(form)
        hint = QLabel(tr('Alle Quellen erscheinen gemeinsam. Die Dateien bleiben an ihrem Ort.\nDie Bezeichnung wird bei jeder Datei als Herkunft angezeigt.'))
        hint.setWordWrap(True); layout.addWidget(hint)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr('Bezeichnung'), tr('Ordner oder Netzwerkadresse')])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 170)
        self.table.setAccessibleName(tr('Quellen der Bibliothek'))
        layout.addWidget(self.table)
        for source in (library or {}).get('sources', []):
            self.add(source['label'], source['location'])
        actions = QHBoxLayout()
        actions.addWidget(button(tr('Ordner hinzufügen …'), self.local))
        actions.addWidget(button(tr('Netzwerk hinzufügen …'), self.remote))
        remove = button(tr('Quelle entfernen'), self.remove); remove.setObjectName('danger'); actions.addWidget(remove)
        layout.addLayout(actions)
        self.error = QLabel(); self.error.setWordWrap(True); layout.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self.save); box.rejected.connect(self.reject); layout.addWidget(box)

    def add(self, label, location):
        row = self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(label))
        self.table.setItem(row, 1, QTableWidgetItem(location))

    def local(self):
        path = QFileDialog.getExistingDirectory(self, tr('Quelle auswählen'))
        if path: self.add(Path(path).name or tr('Dieser PC'), path)

    def remote(self):
        dialog = ConnectDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.add(server_label(dialog.url), dialog.url)
        dialog.deleteLater()

    def remove(self):
        row = self.table.currentRow()
        if row >= 0: self.table.removeRow(row)

    def save(self):
        try:
            sources = [{'label': self.table.item(row, 0).text(), 'location': self.table.item(row, 1).text()}
                       for row in range(self.table.rowCount())]
            self.saved = self.catalog.save_library(self.library, self.name.text(), sources)
            self.accept()
        except (ValueError, OSError) as error:
            self.error.setText(str(error))


class ShelfButton(QPushButton):
    def __init__(self, spaces):
        super().__init__(tr('Sammelfläche'))
        self.spaces = spaces
        self.setAcceptDrops(True)
        self.setToolTip(tr('Dateien hierher ziehen oder Auswahl über das Kontextmenü sammeln'))
        self.clicked.connect(lambda: spaces.window.navigate(SHELF))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        try:
            locations = [url.toLocalFile() if url.isLocalFile() else url.toString(QUrl.FullyEncoded)
                         for url in event.mimeData().urls()]
            self.spaces.collect(locations)
            event.setDropAction(Qt.CopyAction); event.accept()
        except ValueError as error:
            self.spaces.window.error(str(error))


class FileSpaces(QObject):
    def __init__(self, window, catalog=None):
        super().__init__(window)
        self.window, self.catalog = window, catalog or Catalog()
        self.generation = 0
        self.jobs, self.connections, self.errors, self.seen = [], [], {}, set()
        self.pending = 0
        self.source_queue, self.active_sources = [], 0
        self.active_room = None
        self.restore_selection = []

    def reference(self, path):
        return canonical(self.window.network.remote(path) or path)

    def local_reference(self, address):
        if not is_network_address(address): return address
        for path, root in self.window.network.mounts.items():
            if address == root or address.startswith(root.rstrip('/') + '/'):
                relative = QUrl(address).path()[len(QUrl(root).path().rstrip('/')):].lstrip('/')
                return str(Path(path) / relative)
        return address

    def name(self, location):
        if location == SHELF: return tr('Sammelfläche')
        library = self.catalog.library(location[len(LIBRARY):])
        return library['name'] if library else tr('Bibliothek fehlt')

    def edit_library(self, identity=None):
        if identity and identity.startswith('project-'):
            self.window.show_workplace(); return
        dialog = LibraryDialog(self.catalog, self.catalog.library(identity) if identity else None, self.window)
        if dialog.exec() == QDialog.Accepted:
            self.window.populate_places()
            self.window.navigate(LIBRARY + dialog.saved['id'])
        dialog.deleteLater()

    def library_menu(self, menu, location):
        identity = location[len(LIBRARY):]
        menu.addAction(tr('Quellen bearbeiten …'), lambda: self.edit_library(identity))
        if identity.startswith('project-'): return
        if identity not in {item[0] for item in DEFAULTS}:
            previous = self.catalog.library(identity)
            def remove():
                try: self.catalog.remove('library', identity, previous)
                except ValueError as error:
                    self.window.error(str(error)); return
                self.window.populate_places()
                if self.window.current_location == location: self.window.navigate(str(Path.home()))
            menu.addAction(tr('Bibliothek entfernen (Dateien behalten)'), remove)

    def collect(self, paths):
        self.catalog.add_shelf([self.reference(path) for path in paths])
        self.update_shelf()

    def update_shelf(self):
        locations = self.catalog.shelf()
        self.shelf_button.setText(tr('Sammelfläche · {0}', len(locations)))
        if hasattr(self, 'shelf_summary'):
            self.shelf_summary.setText('   ·   '.join(Path(QUrl(p).path()).name if is_network_address(p) else Path(p).name
                for p in locations[:4]) or tr('Dateien hier sammeln — Originale bleiben an ihrem Ort'))
            self.shelf_summary.setToolTip('\n'.join(display_url(p) for p in locations))

    def sources_action(self):
        if self.window.current_location.startswith(LIBRARY):
            self.edit_library(self.window.current_location[len(LIBRARY):])
        elif self.window.current_location == SHELF:
            paths, _ = QFileDialog.getOpenFileNames(self.window, tr('Dateien sammeln'))
            self.collect(paths); self.reload()
        else: self.library_manager()

    def source_details(self):
        text = self.window.source_status.toolTip() or tr('Die Dateien aller erreichbaren Quellen werden gemeinsam angezeigt.')
        QMessageBox.information(self.window, tr('Quellen'), text)

    def stop_loading(self):
        self.cancel()
        self.window.stop_sources.setEnabled(False)
        self.window.source_status.setText(tr('Laden angehalten · F5 zum Aktualisieren'))

    def library_manager(self):
        menu = QMenu(self.window)
        for library in self.catalog.libraries():
            menu.addAction(library['name'] + ' …', lambda _=False, identity=library['id']: self.edit_library(identity))
        menu.addSeparator(); menu.addAction(tr('Neue Bibliothek …'), lambda: self.edit_library())
        menu.exec(self.window.mapToGlobal(self.window.rect().center()))

    def shelf_menu(self):
        menu = QMenu(self.window)
        menu.addAction(tr('Sammelfläche öffnen'), lambda: self.window.navigate(SHELF))
        menu.addAction(tr('Dateien hinzufügen …'), self.choose_shelf_files)
        menu.addAction(tr('Auswahl sammeln'), lambda: self.collect(self.window.selected_paths()))
        menu.addAction(tr('Auswahl in Ordner kopieren …'), self.copy_to)
        menu.addAction(tr('Verweise leeren (Dateien behalten)'), self.clear_shelf)
        menu.exec(self.shelf_button.mapToGlobal(self.shelf_button.rect().bottomLeft()))

    def choose_shelf_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self.window, tr('Dateien sammeln'))
        self.collect(paths)
        if self.window.current_location == SHELF: self.reload()

    def clear_shelf(self):
        self.catalog.replace_shelf([]); self.update_shelf()
        if self.window.current_location == SHELF: self.reload()

    def chat(self):
        return self.window.lumen_host.chat if hasattr(self.window, 'lumen_host') else getattr(self.window, 'assistant', None)

    def capture(self):
        window, chat = self.window, self.chat()
        state = {'tabs': [tab['history'][tab['position']] for tab in window.tabs_data],
            'active': window.tabs.currentIndex(), 'selection': [self.reference(p) for p in window.selected_paths()],
            'shelf': self.catalog.shelf(), 'view': window.settings.value('viewMode', 'list'),
            'sort': window.view.header().sortIndicatorSection(),
            'descending': window.view.header().sortIndicatorOrder() == Qt.DescendingOrder,
            'tasks': (self.active_room or {}).get('state', {}).get('tasks', [])}
        if chat:
            state['chat'] = {'directory': self.reference(chat.backend.directory), 'session': chat.backend.session,
                'draft': chat.composer.toPlainText(), 'paths': [self.reference(p) for p in chat.paths]}
        return state

    def save_active_room(self):
        if not self.active_room: return True
        try:
            self.active_room = self.catalog.save_room(self.active_room, self.active_room['name'], self.capture())
            return True
        except (ValueError, OSError) as error:
            self.window.error(tr('Dateiansicht konnte nicht gespeichert werden.'), str(error) +
                tr('\nDu kannst die aktuelle Ansicht als neue Dateiansicht speichern.')); return False

    def room_menu(self):
        menu = QMenu(self.window)
        for room in self.catalog.rooms():
            if room.get('project'):continue
            action = menu.addAction(room['name'], lambda _=False, value=room: self.open_room(value))
            action.setCheckable(True); action.setChecked(bool(self.active_room and self.active_room['id'] == room['id']))
        menu.addSeparator()
        menu.addAction(tr('Dateiansicht speichern …'), self.new_room)
        if self.active_room and not self.active_room.get('project'):
            menu.addAction(tr('Dateiansicht aktualisieren'), self.save_active_room)
            menu.addAction(tr('Dateiansicht umbenennen …'), self.rename_room)
            menu.addAction(tr('Aufträge zuordnen …'), self.room_tasks)
            for task in self.catalog.store.tasks():
                if task['id'] in self.active_room['state'].get('tasks', []):
                    menu.addAction(tr('Auftrag: ') + task['title'], lambda _=False, t=task: self.open_task(t))
            menu.addAction(tr('Dateiansicht entfernen (Dateien behalten)'), self.delete_room)
        menu.addSeparator();menu.addAction(tr('Lumen Projekte öffnen'), self.window.show_workplace)
        menu.exec(self.window.room_button.mapToGlobal(self.window.room_button.rect().bottomLeft()))

    def new_room(self):
        name, ok = QInputDialog.getText(self.window, tr('Dateiansicht speichern'), tr('Name:'))
        if ok:
            try:
                self.active_room = self.catalog.save_room(None, name, self.capture())
                self.catalog.use_room_shelf(self.active_room['id'], self.active_room['state']['shelf'])
                self.update_shelf()
                if self.window.current_location == SHELF: self.reload()
                self.window.room_button.setText(self.active_room['name'])
            except ValueError as error: self.window.error(str(error))

    def rename_room(self):
        name, ok = QInputDialog.getText(self.window, tr('Dateiansicht umbenennen'), tr('Name:'), text=self.active_room['name'])
        if ok:
            try:
                self.active_room = self.catalog.save_room(self.active_room, name, self.capture())
                self.window.room_button.setText(name)
            except ValueError as error: self.window.error(str(error))

    def delete_room(self):
        try: self.catalog.remove('room', self.active_room['id'], self.active_room)
        except ValueError as error:
            self.window.error(str(error)); return
        self.active_room = None
        self.catalog.use_room_shelf(); self.update_shelf()
        if self.window.current_location == SHELF: self.reload()
        self.window.room_button.setText(tr('Dateiansichten'))

    def room_tasks(self):
        dialog = QDialog(self.window); dialog.setWindowTitle(tr('Aufträge dieser Dateiansicht zuordnen'))
        layout = QVBoxLayout(dialog); tasks = QListWidget(); layout.addWidget(tasks)
        chosen = self.active_room['state'].get('tasks', [])
        for task in self.catalog.store.tasks():
            item = QListWidgetItem(task['title']); item.setData(Qt.UserRole, task['id'])
            item.setCheckState(Qt.Checked if task['id'] in chosen else Qt.Unchecked); tasks.addItem(item)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(dialog.accept); box.rejected.connect(dialog.reject); layout.addWidget(box)
        if dialog.exec() == QDialog.Accepted:
            state = self.capture()
            state['tasks'] = [tasks.item(i).data(Qt.UserRole) for i in range(tasks.count()) if tasks.item(i).checkState() == Qt.Checked]
            try: self.active_room = self.catalog.save_room(self.active_room, self.active_room['name'], state)
            except ValueError as error: self.window.error(str(error))
        dialog.deleteLater()

    def open_task(self, task):
        if hasattr(self.window, 'lumen_host'):
            host = self.window.lumen_host
            host.show_page(4); host.workspace.refresh_tasks()
            for i in range(host.workspace.tasks.count()):
                item = host.workspace.tasks.item(i)
                if item.data(Qt.UserRole) == task['id']: host.workspace.tasks.setCurrentItem(item); break
        else:
            QMessageBox.information(self.window, task['title'], task['result'] or task['prompt'] or task['status'])

    def open_room(self, room, chat_directory=None, on_open=None):
        window, chat = self.window, self.chat()
        if self.active_room and room['id'] == self.active_room['id']:
            if on_open: on_open()
            return
        if window.file_job or (chat and (chat.backend.busy or chat.context_tools.process)):
            window.error(tr('Bitte den laufenden Datei-, Aufnahme- oder Lumen-Vorgang zuerst beenden.')); return
        directory = room['state'].get('chat', {}).get('directory', '')
        if is_network_address(directory) and chat_directory is None:
            self.cancel()
            generation = self.generation
            connection = Network(self); self.connections.append(connection)
            def mounted(address, path):
                if generation != self.generation: return
                window.network.mounts[path] = address
                self.open_room(room, path, on_open)
            connection.connected.connect(mounted)
            connection.failed.connect(lambda message: window.error(message) if generation == self.generation else None)
            try: connection.mount(directory)
            except ValueError as error: window.error(str(error))
            return
        if not self.save_active_room(): return
        if not self.active_room:
            previous = next((r for r in self.catalog.rooms() if r['id'] == 'previous'), None)
            try: self.catalog.put('room', {'id': 'previous', 'name': tr('Vorheriger Arbeitsstand'), 'state': self.capture()}, previous)
            except ValueError as error:
                window.error(str(error)); return
        state = room['state']
        self.active_room = None
        self.cancel(); window.cancel_connection(); window.cancel_search()
        window.tabs.blockSignals(True)
        while window.tabs.count(): window.tabs.removeTab(0)
        window.tabs_data.clear(); window.tabs.blockSignals(False)
        for path in state.get('tabs', []) or [str(Path.home())]:
            window.new_tab(path, activate=False)
        index = max(0, min(state.get('active', 0), window.tabs.count() - 1))
        window.tabs.blockSignals(True); window.tabs.setCurrentIndex(index); window.tabs.blockSignals(False)
        # Room shelves are independent, shared only with windows in that room.
        self.catalog.use_room_shelf(room['id'], state.get('shelf', [])); self.update_shelf()
        self.restore_selection = state.get('selection', [])
        window.switch_tab(index)
        window.set_view_mode(state.get('view', 'list'))
        window.view.sortByColumn(state.get('sort', 0), Qt.DescendingOrder if state.get('descending') else Qt.AscendingOrder)
        self.select_paths(self.restore_selection)
        if state.get('chat'):
            context = state['chat']
            if chat is None:
                window.ask_lumen('open', []); chat = self.chat()
            chat.backend.new_conversation(chat_directory or context['directory'])
            chat.set_action('open')
            if context.get('session'): chat.backend.select_session(context['session'])
            chat.paths = [self.local_reference(p) for p in context.get('paths', [])]
            chat.composer.setPlainText(context.get('draft', '')); chat.update_context()
        elif chat:
            chat.backend.new_conversation(); chat.composer.clear(); chat.paths = []; chat.update_context()
        self.active_room = room
        window.room_button.setText(room['name'])
        if on_open: on_open()

    def remove_shelf(self, paths):
        self.catalog.remove_shelf([self.reference(path) for path in paths])
        self.update_shelf(); self.reload()

    def choose_target(self):
        return QFileDialog.getExistingDirectory(self.window, tr('Zielordner auswählen'), str(Path.home())) or None

    def copy_to(self):
        paths = self.window.selected_paths()
        if not paths: return
        target = self.choose_target()
        if target: self.window.run_operation('copy', paths, target)

    def cancel(self):
        self.generation += 1
        for job in self.jobs[:]:
            job.kill()
        for connection in self.connections:
            connection.mounts.clear()  # Mount ownership is transferred to Window.network.
            connection.close(); connection.deleteLater()
        self.connections.clear()
        self.pending = 0
        self.source_queue, self.active_sources = [], 0

    def reload(self):
        window = self.window
        if not virtual(window.current_location): return
        self.cancel()
        generation = self.generation
        self.errors, self.seen = {}, set()
        window.results.clear()
        window.results.setHorizontalHeaderLabels([tr('Name'), tr('Größe'), tr('Typ'), tr('Geändert'), tr('Herkunft')])
        window.proxy.setSourceModel(window.results)
        window.set_file_root(QModelIndex()); window.configure_columns()
        query = window.search.text().strip()
        if window.current_location == SHELF:
            sources = {}
            for location in self.catalog.shelf():
                if is_network_address(location):
                    url = QUrl(location); name = Path(url.path()).name
                    url.setPath(str(Path(url.path()).parent), QUrl.DecodedMode)
                    parent = url.toString(QUrl.FullyEncoded)
                else: parent, name = str(Path(location).parent), Path(location).name
                source = sources.setdefault(parent, {'label': server_label(parent) if is_network_address(parent) else parent,
                    'location': parent, 'names': []})
                source['names'].append(name)
            sources = list(sources.values())
        else:
            library = self.catalog.library(window.current_location[len(LIBRARY):])
            sources = library['sources'] if library else []
        self.pending = len(sources)
        window.sources_button.setText(tr('Sammeln') if window.current_location == SHELF else tr('{0} Quellen …', len(sources)))
        self.source_queue = sources[:]
        self.pump(query, generation)
        self.show_status()

    def pump(self, query, generation):
        window = self.window
        while self.source_queue and self.active_sources < 4 and generation == self.generation:
            source = self.source_queue.pop(0)
            self.active_sources += 1
            if is_network_address(source['location']):
                connection = Network(self); self.connections.append(connection)
                def mounted(address, path, source=source):
                    if generation != self.generation: return
                    window.network.mounts[path] = address
                    self.scan(source, path, query, generation)
                connection.connected.connect(mounted)
                connection.failed.connect(lambda message, s=source: self.done(s, generation, message))
                try: connection.mount(source['location'])
                except ValueError as error: self.done(source, generation, str(error))
            else:
                self.scan(source, source['location'], query, generation)
    def scan(self, source, root, query, generation):
        job = worker_process(self); self.jobs.append(job)
        buffer = bytearray()
        found = set()
        limit = self.window.settings.value('searchLimit', 5000, type=int)
        timer = QTimer(job); timer.setSingleShot(True)
        timeout = []
        def expired():
            timeout.append(True); job.kill()
        timer.timeout.connect(expired)
        def read():
            buffer.extend(bytes(job.readAllStandardOutput()))
            while b'\n' in buffer:
                line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
                if generation != self.generation: continue
                try: entry = json.loads(line)
                except ValueError:
                    self.errors[source['location']] = tr('Ungültige Antwort beim Lesen.'); continue
                if 'path' in entry:
                    found.add(entry['name'])
                    if 'names' not in source or entry['name'] in source['names']:
                        self.add_entry(entry, source, root, limit)
                elif 'error' in entry: self.errors[source['location']] = entry['error']
                elif 'limited' in entry: self.errors[source['location']] = tr('Trefferlimit erreicht — Suche eingrenzen.')
        finished = []
        def finish(code):
            if finished: return
            finished.append(True); timer.stop(); read()
            if job in self.jobs: self.jobs.remove(job)
            error = tr('Zeitlimit beim Lesen erreicht. Mit F5 erneut versuchen.') if timeout else ''
            if code and not error: error = tr('Quelle konnte nicht gelesen werden.')
            if 'names' in source and not query:
                missing = set(source['names']) - found
                if missing: error = tr('{0} gesammelte Einträge nicht erreichbar; Verweise bleiben erhalten.', len(missing))
            self.done(source, generation, error)
            job.deleteLater()
        job.readyReadStandardOutput.connect(read)
        job.finished.connect(finish)
        job.errorOccurred.connect(lambda error: finish(1) if error == QProcess.FailedToStart else None)
        job.start(sys.executable, [str(Path(__file__).with_name('file_spaces.py'))])
        job.write((json.dumps({'root': root, 'query': query if 'names' not in source else '',
            'hidden': self.window.hidden or 'names' in source, 'limit': max(100, min(50000, limit)),
            'names': source.get('names')}) + '\n').encode())
        job.closeWriteChannel(); timer.start(30000)

    def add_entry(self, entry, source, root, limit):
        path = entry['path']
        if path in self.seen: return
        if self.window.current_location == SHELF and any(term not in entry['name'].casefold()
                for term in self.window.search.text().casefold().split()): return
        if len(self.seen) >= limit:
            self.errors[source['location']] = tr('Trefferlimit erreicht — Suche eingrenzen.'); return
        self.seen.add(path)
        origin = source['label']
        relative = os.path.relpath(str(Path(path).parent), root)
        if relative != '.': origin += ' / ' + relative
        name = entry['name'].replace('\n', '↵').replace('\t', '⇥')
        items = [QStandardItem(value) for value in [name, '—' if entry['directory'] else size_text(entry['size']),
            tr('Ordner') if entry['directory'] else Path(path).suffix[1:].upper(),
            QDateTime.fromSecsSinceEpoch(int(entry['modified'])).toString('dd.MM.yy HH:mm'), origin]]
        items[0].setData(path, Qt.UserRole)
        items[0].setData(bool(entry['directory']), Qt.UserRole + 3)
        items[0].setData(origin, Qt.UserRole + 2)
        items[0].setIcon(QIcon.fromTheme('folder' if entry['directory'] else 'text-x-generic'))
        items[1].setData(entry['size'], Qt.UserRole + 1)
        items[3].setData(entry['modified'] * 1000, Qt.UserRole + 1)
        for item in items:
            item.setEditable(False); item.setToolTip(origin + '\n' + self.reference(path))
        self.window.results.appendRow(items)
        if self.reference(path) in self.restore_selection:
            self.select_paths(self.restore_selection)

    def done(self, source, generation, error=''):
        if generation != self.generation: return
        if error: self.errors[source['location']] = error
        self.pending = max(0, self.pending - 1)
        self.active_sources = max(0, self.active_sources - 1)
        self.pump(self.window.search.text().strip(), generation)
        self.show_status()

    def show_status(self):
        self.window.stop_sources.setEnabled(bool(self.pending))
        message = tr('{0} Quellen werden geladen …', self.pending) if self.pending else tr('Alle erreichbaren Quellen geladen')
        if self.errors: message += tr(' · {0} Hinweise (Details)', len(self.errors))
        self.window.source_status.setText(message)
        self.window.source_status.setToolTip('\n\n'.join(display_url(path) + ': ' + error for path, error in self.errors.items()))

    def select_paths(self, paths):
        window = self.window
        restored = set()
        for row in range(window.proxy.rowCount(window.view.rootIndex())):
            index = window.proxy.index(row, 0, window.view.rootIndex())
            reference = self.reference(window.proxy.path(index))
            if reference in paths:
                window.view.selectionModel().select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                restored.add(reference)
        self.restore_selection = [p for p in self.restore_selection if p not in restored]

    def directory_loaded(self, path):
        if path == self.window.current_path and self.restore_selection:
            paths, self.restore_selection = self.restore_selection, []
            self.select_paths(paths)

    def close(self):
        self.cancel()
        for job in self.jobs[:]:
            job.waitForFinished(1000)
