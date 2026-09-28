#!/usr/bin/python3
"""Lumen Files — a preview-first native file manager for Linux."""
import os
import sys
from pathlib import Path

from PyQt5.QtCore import (QDir, QFileInfo, QItemSelectionModel, QMimeData, QModelIndex,
                          QSettings, QSize, QSortFilterProxyModel, QStandardPaths,
                          QStorageInfo, Qt, QTimer, QTranslator, QLibraryInfo, QUrl)
from PyQt5.QtGui import QDesktopServices, QIcon, QKeySequence, QPalette, QColor, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileIconProvider,
                             QFileSystemModel, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QShortcut,
                             QSplitter, QStackedWidget, QTabBar, QTreeView, QVBoxLayout, QWidget)
from core import FileWorker, SearchWorker, file_kind, size_text, valid_name
from network import Network, ConnectDialog, display_url, is_network_address, normalize_url, server_label
from preview import Preview, label
from gallery import Gallery

ROOT = Path(__file__).resolve().parent


def button(text, callback, icon=None, tip=None):
    widget = QPushButton(text)
    if icon:
        widget.setIcon(QIcon.fromTheme(icon))
    widget.clicked.connect(callback)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setToolTip(tip or text)
    widget.setAccessibleName(tip or text)
    return widget


class FileFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = 'all'
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and index.column() == 3 and isinstance(self.sourceModel(), QFileSystemModel):
            return self.sourceModel().fileInfo(self.mapToSource(index)).lastModified().toString('dd.MM.yy HH:mm')
        return super().data(index, role)

    def path(self, index):
        index = self.mapToSource(index.sibling(index.row(), 0))
        model = self.sourceModel()
        return model.filePath(index) if isinstance(model, QFileSystemModel) else index.data(Qt.UserRole)

    def filterAcceptsRow(self, row, parent):
        if self.kind == 'all':
            return True
        model = self.sourceModel()
        index = model.index(row, 0, parent)
        if isinstance(model, QFileSystemModel):
            if model.isDir(index):
                return True
            path = model.filePath(index)
        else:
            path = index.data(Qt.UserRole)
        kind = file_kind(path)
        return kind in {'pdf', 'text'} if self.kind == 'document' else kind == self.kind

    def lessThan(self, left, right):
        model = self.sourceModel()
        if isinstance(model, QFileSystemModel):
            a, b = model.fileInfo(left), model.fileInfo(right)
            if a.isDir() != b.isDir():
                return a.isDir() if self.sortOrder() == Qt.AscendingOrder else b.isDir()
            if left.column() == 1:
                return a.size() < b.size()
            if left.column() == 3:
                return a.lastModified() < b.lastModified()
        else:
            a, b = left.data(Qt.UserRole + 1), right.data(Qt.UserRole + 1)
            if a is not None and b is not None:
                return a < b
        return super().lessThan(left, right)


class FileView(QTreeView):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDropIndicatorShown(True)

    def startDrag(self, supported):
        from PyQt5.QtGui import QDrag
        paths = self.window.selected_paths()
        if not paths:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        drag.setMimeData(mime)
        # Copy-only external dragging avoids accidental destructive drop actions.
        drag.exec_(Qt.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.setDropAction(Qt.CopyAction)
            event.accept()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        index = self.indexAt(event.pos())
        target = self.window.current_path
        if index.isValid():
            path = self.window.proxy.path(index)
            if Path(path).is_dir():
                target = path
        if paths:
            self.window.run_operation('copy', paths, target)
            event.setDropAction(Qt.CopyAction)
            event.accept()


class Window(QMainWindow):
    def __init__(self, start=None, settings=None):
        super().__init__()
        self.settings = settings or QSettings('Lumen', 'Files')
        self.setWindowTitle('Lumen Files')
        self.setWindowIcon(QIcon(str(ROOT / 'lumen-files.svg')))
        self.resize(1380, 860)
        self.setMinimumSize(1000, 640)
        self.tabs_data = []
        self.search_job = None
        self.search_jobs = []
        self.file_job = None
        self.search_errors = 0
        self.search_total = 0
        self.current_path = str(Path.home())
        self.current_location = self.current_path
        self.network = Network(self)
        self.connection_request = None
        self.hidden = self.settings.value('hidden', False, type=bool)
        self.icon_provider = QFileIconProvider()
        self.fs = QFileSystemModel(self)
        self.fs.setReadOnly(True)
        self.fs.setOption(QFileSystemModel.DontUseCustomDirectoryIcons, True)
        self.apply_hidden()
        self.fs.setRootPath(str(Path.home()))
        self.fs.directoryLoaded.connect(lambda _path: self.update_count())
        self.results = QStandardItemModel(self)
        self.results.setHorizontalHeaderLabels(['Name', 'Größe', 'Typ', 'Geändert', 'Ordner'])
        self.proxy = FileFilter(self)
        self.proxy.setSourceModel(self.fs)
        self.build_ui()
        self.network.connected.connect(self.network_connected)
        self.network.failed.connect(self.network_failed)
        self.network.busy.connect(self.cancel_connect_button.setVisible)
        self.install_shortcuts()
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(250)
        self.debounce.timeout.connect(self.start_search)
        self.search.textChanged.connect(self.queue_search)
        self.preview_delay = QTimer(self)
        self.preview_delay.setSingleShot(True)
        self.preview_delay.setInterval(100)
        self.preview_delay.timeout.connect(self.preview_selection)
        self.new_tab(start or self.settings.value('last_path', str(Path.home())))
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        tabrow = QHBoxLayout()
        tabrow.setContentsMargins(25, 5, 24, 0)
        brand = label('lumen', 'brand')
        brand.setFixedWidth(170)
        tabrow.addWidget(brand)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self.switch_tab)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        tabrow.addWidget(self.tabs)
        tabrow.addWidget(button('+', lambda: self.new_tab(self.current_location), tip='Neuer Tab · Strg+T'))
        tabrow.addStretch()
        layout.addLayout(tabrow)
        header = QFrame()
        header.setObjectName('appHeader')
        row = QHBoxLayout(header)
        row.setContentsMargins(25, 17, 24, 17)
        caption = label('DATEIEN & ORDNER', 'eyebrow')
        caption.setFixedWidth(170)
        row.addWidget(caption)
        self.search = QLineEdit()
        self.search.setObjectName('search')
        self.search.setAccessibleName('Dateien im aktuellen Ordner und Unterordnern suchen')
        self.search.setPlaceholderText('Dateien und Ordner finden …     Strg+F')
        self.search.setClearButtonEnabled(True)
        self.search.addAction(QIcon.fromTheme('edit-find'), QLineEdit.LeadingPosition)
        row.addWidget(self.search, 1)
        row.addSpacing(16)
        row.addWidget(button('Neuer Ordner', self.mkdir, 'folder-new', 'Neuer Ordner · Strg+Umschalt+N'))
        menu_button = button('•••', self.show_menu, tip='Ansicht und Tastenkürzel')
        menu_button.setObjectName('iconButton')
        row.addWidget(menu_button)
        layout.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(208)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 28, 14, 20)
        side.setSpacing(12)
        side.addWidget(label('DEINE ORTE', 'eyebrow'))
        self.places = QListWidget()
        self.places.setObjectName('places')
        self.places.setIconSize(QSize(22, 22))
        self.places.itemClicked.connect(lambda item: self.navigate(item.data(Qt.UserRole)))
        self.places.setContextMenuPolicy(Qt.CustomContextMenu)
        self.places.customContextMenuRequested.connect(self.place_menu)
        self.populate_places()
        side.addWidget(self.places, 1)
        side.addWidget(button('Server verbinden', self.connect_dialog, 'network-server'))
        side.addWidget(button('Ort merken', self.add_favorite, 'bookmark-new'))
        side.addSpacing(10)
        self.disk_label = label('', 'muted')
        side.addWidget(self.disk_label)
        self.location_badge = label('LOKAL AUF DEINEM RECHNER', 'tiny')
        side.addWidget(self.location_badge)
        body.addWidget(sidebar)
        content = QVBoxLayout()
        content.setSpacing(0)
        nav = QWidget()
        navrow = QHBoxLayout(nav)
        navrow.setContentsMargins(16, 12, 20, 12)
        navrow.setSpacing(6)
        self.back_button = button('←', lambda: self.history(-1), tip='Zurück · Alt+Links')
        self.forward_button = button('→', lambda: self.history(1), tip='Vorwärts · Alt+Rechts')
        for widget in [self.back_button, self.forward_button,
                       button('↑', self.up, tip='Übergeordneter Ordner · Alt+Hoch')]:
            widget.setObjectName('iconButton')
            navrow.addWidget(widget)
        self.path_stack = QStackedWidget()
        self.crumbs = QWidget()
        self.crumb_layout = QHBoxLayout(self.crumbs)
        self.crumb_layout.setContentsMargins(6, 0, 0, 0)
        self.crumb_layout.setSpacing(0)
        self.path_edit = QLineEdit()
        self.path_edit.setAccessibleName('Ordnerpfad')
        self.path_edit.returnPressed.connect(lambda: self.navigate(self.path_edit.text()))
        self.path_stack.addWidget(self.crumbs)
        self.path_stack.addWidget(self.path_edit)
        navrow.addWidget(self.path_stack, 1)
        navrow.addWidget(button('/', self.edit_path, tip='Pfad eingeben · Strg+L'))
        content.addWidget(nav)
        self.splitter = QSplitter()
        file_area = QWidget()
        files = QVBoxLayout(file_area)
        files.setContentsMargins(24, 22, 22, 8)
        files.setSpacing(14)
        title_row = QHBoxLayout()
        self.heading = label('', 'heading')
        title_row.addWidget(self.heading, 1)
        self.hidden_button = button('Versteckte', self.toggle_hidden, tip='Versteckte Dateien · Strg+H')
        self.hidden_button.setCheckable(True)
        self.hidden_button.setChecked(self.hidden)
        title_row.addWidget(self.hidden_button)
        self.preview_button = button('Vorschau', self.toggle_preview, tip='Vorschauleiste ein-/ausblenden')
        self.preview_button.setCheckable(True)
        self.preview_button.setChecked(True)
        title_row.addWidget(self.preview_button)
        files.addLayout(title_row)
        self.subtitle = label('Deine Dateien. Alles im Blick.', 'muted')
        files.addWidget(self.subtitle)
        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.filter_buttons = {}
        for text, kind in [('Alles', 'all'), ('Bilder', 'image'), ('Dokumente', 'document'), ('Videos', 'video'), ('Audio', 'audio')]:
            item = button(text, lambda _checked=False, k=kind: self.set_kind(k))
            item.setObjectName('chip')
            item.setCheckable(True)
            item.setChecked(kind == 'all')
            self.filter_buttons[kind] = item
            filters.addWidget(item)
        filters.addStretch()
        files.addLayout(filters)
        self.view = FileView(self)
        self.view.setObjectName('files')
        self.view.setAccessibleName('Dateiliste')
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setUniformRowHeights(True)
        self.view.setIconSize(QSize(26, 26))
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(False)
        self.view.setSortingEnabled(True)
        self.view.setModel(self.proxy)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        self.view.doubleClicked.connect(self.open_index)
        self.view.selectionModel().selectionChanged.connect(self.selection_changed)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.configure_columns()
        files.addWidget(self.view, 1)
        self.empty_label = label('', 'muted')
        self.empty_label.setAlignment(Qt.AlignCenter)
        files.addWidget(self.empty_label)
        self.splitter.addWidget(file_area)
        self.preview = Preview()
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([650, 410])
        content.addWidget(self.splitter, 1)
        body.addLayout(content, 1)
        layout.addLayout(body, 1)
        footer = QFrame()
        footer.setObjectName('footer')
        status = QHBoxLayout(footer)
        status.setContentsMargins(24, 9, 24, 9)
        self.status = label('Bereit', 'muted')
        status.addWidget(self.status, 1)
        self.activity = label('Leertaste  Vorschau    ·    Strg+F  Suche', 'muted')
        status.addWidget(self.activity)
        self.cancel_connect_button = button('Abbrechen', self.cancel_connection)
        self.cancel_connect_button.hide()
        status.addWidget(self.cancel_connect_button)
        layout.addWidget(footer)
        self.proxy.rowsInserted.connect(lambda *_: self.update_count())
        self.proxy.rowsRemoved.connect(lambda *_: self.update_count())
        self.proxy.modelReset.connect(self.update_count)

    def populate_places(self):
        self.places.clear()
        places = [('Persönlicher Ordner', str(Path.home()), 'user-home')]
        for text, location, icon in [('Schreibtisch', QStandardPaths.DesktopLocation, 'user-desktop'),
                                     ('Downloads', QStandardPaths.DownloadLocation, 'folder-download'),
                                     ('Dokumente', QStandardPaths.DocumentsLocation, 'folder-documents'),
                                     ('Bilder', QStandardPaths.PicturesLocation, 'folder-pictures'),
                                     ('Videos', QStandardPaths.MoviesLocation, 'folder-videos'),
                                     ('Musik', QStandardPaths.MusicLocation, 'folder-music')]:
            path = QStandardPaths.writableLocation(location)
            if path and Path(path).is_dir():
                places.append((text, path, icon))
        for path in self.settings.value('favorites', [], type=list):
            if path not in [p[1] for p in places]:
                places.append((Path(path).name or path, path, 'folder-favorites'))
        places.append(('Dateisystem', '/', 'drive-harddisk'))
        seen = {path for _, path, _ in places}
        for storage in QStorageInfo.mountedVolumes():
            path = storage.rootPath()
            if path == '/mnt/games':
                continue
            remote = bytes(storage.fileSystemType()) in {b'cifs', b'nfs', b'nfs4', b'fuse.sshfs', b'fuse.davfs'}
            if storage.isReady() and path not in seen and (remote or path.startswith(('/run/media/', '/media/', '/mnt/'))):
                places.append((Path(path).name, path, 'network-server' if remote else 'drive-removable-media'))
                seen.add(path)
        for text, path, icon in places:
            item = QListWidgetItem(QIcon.fromTheme(icon), text)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.places.addItem(item)
        servers = self.saved_servers()
        if servers:
            heading = QListWidgetItem('NETZWERK')
            heading.setFlags(Qt.NoItemFlags)
            self.places.addItem(heading)
            for address in servers:
                item = QListWidgetItem(QIcon.fromTheme('network-server'), server_label(address))
                item.setData(Qt.UserRole, address)
                item.setToolTip(display_url(address))
                self.places.addItem(item)

    def saved_servers(self):
        servers = []
        for address in self.settings.value('network_servers', [], type=list):
            try:
                servers.append(normalize_url(address))
            except ValueError:
                continue
        return list(dict.fromkeys(servers))

    def remember_server(self, address):
        servers = self.saved_servers()
        address = normalize_url(address)
        if address not in servers:
            self.settings.setValue('network_servers', servers + [address])
        self.populate_places()

    def connect_dialog(self):
        dialog = ConnectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.connect_server(dialog.url, remember=dialog.remember.isChecked())
        dialog.deleteLater()

    def connect_server(self, address, record=True, remember=False, history_position=None):
        self.cancel_connection()
        try:
            address = normalize_url(address)
        except ValueError as exc:
            self.error(str(exc))
            return
        self.connection_request = (self.tabs_data[self.tabs.currentIndex()], record, remember, history_position)
        self.activity.setText(f'Verbinde mit {QUrl(address).host()} …')
        self.network.mount(address)

    def cancel_connection(self):
        if self.connection_request:
            self.network.cancel()
            self.connection_request = None
            self.activity.setText('Verbindungsversuch verworfen')

    def network_connected(self, address, path):
        request, self.connection_request = self.connection_request, None
        if request and request[0] is self.tabs_data[self.tabs.currentIndex()]:
            if self.show_folder(path, request[1], address, request[3]):
                if request[2]:
                    self.remember_server(address)
                self.activity.setText(f'Verbunden mit {QUrl(address).host()}')
            else:
                self.activity.setText('Netzwerkordner nicht erreichbar')

    def network_failed(self, message):
        self.connection_request = None
        self.activity.setText('Netzwerkverbindung fehlgeschlagen')
        self.error('Verbindung fehlgeschlagen', message)

    def add_favorite(self):
        if is_network_address(self.current_location):
            self.remember_server(self.current_location)
            return
        paths = self.settings.value('favorites', [], type=list)
        if self.current_path not in paths:
            paths.append(self.current_path)
            self.settings.setValue('favorites', paths)
            self.populate_places()

    def place_menu(self, position):
        item = self.places.itemAt(position)
        if not item:
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        menu = QMenu(self)
        menu.addAction('In neuem Tab öffnen', lambda: self.new_tab(path))
        key = 'network_servers' if is_network_address(path) else 'favorites'
        favorites = self.settings.value(key, [], type=list)
        if path in favorites:
            def remove():
                self.settings.setValue(key, [p for p in favorites if p != path])
                self.populate_places()
            menu.addAction('Aus gemerkten Orten entfernen', remove)
        menu.exec_(self.places.viewport().mapToGlobal(position))

    def configure_columns(self):
        header = self.view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in [(1, 90), (2, 112), (3, 140), (4, 230)]:
            if column < self.proxy.columnCount():
                header.setSectionResizeMode(column, QHeaderView.Interactive)
                self.view.setColumnWidth(column, width)
        # Type is already visible in the icon/preview; save space in the default list.
        self.view.setColumnHidden(2, True)
        self.view.setColumnHidden(3, self.width() < 1180)
        self.fs.setHeaderData(0, Qt.Horizontal, 'Name')

    def shortcut(self, key, callback, local=False):
        shortcut = QShortcut(QKeySequence(key), self.view if local else self)
        shortcut.setContext(Qt.WidgetShortcut if local else Qt.WindowShortcut)
        shortcut.activated.connect(callback)

    def install_shortcuts(self):
        for key, callback in [('Ctrl+F', lambda: self.search.setFocus()), ('Ctrl+L', self.edit_path),
                              ('Ctrl+T', lambda: self.new_tab(self.current_location)),
                              ('Ctrl+K', self.connect_dialog),
                              ('Ctrl+W', lambda: self.close_tab(self.tabs.currentIndex())),
                              ('Ctrl+Tab', lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())),
                              ('Alt+Left', lambda: self.history(-1)), ('Alt+Right', lambda: self.history(1)),
                              ('Alt+Up', self.up),
                              ('Ctrl+H', self.toggle_hidden), ('Ctrl+Shift+N', self.mkdir),
                              ('F5', self.refresh), ('Escape', self.escape)]:
            self.shortcut(key, callback)
        for key, callback in [('Space', self.quicklook), ('Return', self.open_selected),
                              ('F2', self.rename), ('Delete', self.trash),
                              ('Ctrl+C', lambda: self.copy(False)), ('Ctrl+X', lambda: self.copy(True)),
                              ('Ctrl+V', self.paste)]:
            self.shortcut(key, callback, local=True)

    def new_tab(self, path):
        remote = str(path) if is_network_address(path) else self.network.remote(str(path))
        if remote:
            path = str(Path.home())
        path = str(Path(path).expanduser())
        if not Path(path).is_dir():
            path = str(Path.home())
        self.tabs_data.append({'history': [path], 'position': 0})
        self.tabs.blockSignals(True)
        index = self.tabs.addTab(Path(path).name or 'Dateisystem')
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        self.switch_tab(index)
        if remote:
            self.connect_server(remote)

    def switch_tab(self, index):
        if index >= 0:
            tab = self.tabs_data[index]
            self.navigate(tab['history'][tab['position']], record=False)

    def close_tab(self, index):
        if self.tabs.count() == 1:
            return
        self.tabs.blockSignals(True)
        self.tabs_data.pop(index)
        self.tabs.removeTab(index)
        self.tabs.blockSignals(False)
        self.switch_tab(self.tabs.currentIndex())

    def history(self, delta):
        tab = self.tabs_data[self.tabs.currentIndex()]
        position = tab['position'] + delta
        if 0 <= position < len(tab['history']):
            self.navigate(tab['history'][position], record=False, history_position=position)

    def navigate(self, path, record=True, history_position=None):
        remote = str(path) if is_network_address(path) else self.network.remote(str(path))
        if remote:
            self.connect_server(remote, record, history_position=history_position)
            return
        self.cancel_connection()
        if str(path).startswith('file:'):
            path = QUrl(str(path)).toLocalFile()
        self.show_folder(path, record, history_position=history_position)

    def show_folder(self, path, record=True, location=None, history_position=None):
        path = os.path.abspath(os.path.expanduser(str(path)))
        if not os.path.isdir(path) or not os.access(path, os.R_OK | os.X_OK):
            self.error('Der Ordner ist nicht erreichbar oder nicht lesbar.', path)
            return False
        self.current_path = path
        self.current_location = location or path
        remote = location is not None
        tab = self.tabs_data[self.tabs.currentIndex()]
        if history_position is not None:
            tab['position'] = history_position
        if record and tab['history'][tab['position']] != self.current_location:
            tab['history'] = tab['history'][:tab['position'] + 1] + [self.current_location]
            tab['position'] += 1
        title = server_label(location) if remote else Path(path).name or 'Dateisystem'
        self.tabs.setTabText(self.tabs.currentIndex(), title)
        self.tabs.setTabToolTip(self.tabs.currentIndex(), display_url(location) if remote else path)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.debounce.stop()
        self.cancel_search()
        self.proxy.setSourceModel(self.fs)
        self.view.setRootIndex(self.proxy.mapFromSource(self.fs.setRootPath(path)))
        self.view.clearSelection()
        self.configure_columns()
        self.preview.clear()
        self.path_edit.setText(display_url(location) if remote else path)
        self.path_stack.setCurrentWidget(self.crumbs)
        self.build_crumbs(self.current_location)
        self.heading.setText(title)
        self.subtitle.setText('Deine Dateien. Alles im Blick.')
        self.search.setPlaceholderText(f'In {Path(path).name or "/"} und Unterordnern suchen …     Strg+F')
        self.back_button.setEnabled(tab['position'] > 0)
        self.forward_button.setEnabled(tab['position'] < len(tab['history']) - 1)
        if remote:
            self.disk_label.setText(f'{QUrl(location).host()}\n{QUrl(location).scheme().upper()} verbunden')
        else:
            storage = QStorageInfo(path)
            self.disk_label.setText(f'{size_text(storage.bytesAvailable())} frei\nauf {storage.displayName() or "diesem Laufwerk"}')
        self.location_badge.setText('NETZWERKVERBINDUNG' if remote else 'LOKAL AUF DEINEM RECHNER')
        for i in range(self.places.count()):
            self.places.item(i).setSelected(self.places.item(i).data(Qt.UserRole) == self.current_location)
        self.update_count()
        self.view.setFocus()
        return True

    def build_crumbs(self, path):
        while self.crumb_layout.count():
            item = self.crumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        remote = is_network_address(path)
        if remote:
            url = QUrl(path)
            paths = list(reversed(Path(url.path()).parents)) + [Path(url.path())]
            parts = []
            for part in paths:
                crumb_url = QUrl(url)
                crumb_url.setPath(str(part), QUrl.DecodedMode)
                parts.append(crumb_url.toString(QUrl.FullyEncoded))
        else:
            parts = list(reversed(Path(path).parents)) + [Path(path)]
        if len(parts) > 4:
            parts = [parts[0]] + parts[-3:]
        for i, part in enumerate(parts):
            if i:
                self.crumb_layout.addWidget(label('  /  ', 'muted'))
            text = (Path(QUrl(part).path()).name or QUrl(part).host()) if remote else ('~' if part == Path.home() else part.name or 'Rechner')
            crumb = button(text, lambda _checked=False, p=part: self.navigate(p), tip=str(part))
            crumb.setObjectName('crumb')
            self.crumb_layout.addWidget(crumb)
        self.crumb_layout.addStretch()

    def up(self):
        if is_network_address(self.current_location):
            url = QUrl(self.current_location)
            url.setPath(str(Path(url.path()).parent), QUrl.DecodedMode)
            self.navigate(url.toString(QUrl.FullyEncoded))
        else:
            self.navigate(Path(self.current_path).parent)

    def edit_path(self):
        self.path_stack.setCurrentWidget(self.path_edit)
        self.path_edit.setFocus()
        self.path_edit.selectAll()

    def apply_hidden(self):
        flags = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.System
        if self.hidden:
            flags |= QDir.Hidden
        self.fs.setFilter(flags)

    def toggle_hidden(self):
        self.hidden = not self.hidden
        self.hidden_button.setChecked(self.hidden)
        self.settings.setValue('hidden', self.hidden)
        self.apply_hidden()
        if self.search.text().strip():
            self.queue_search()
        else:
            QTimer.singleShot(50, self.update_count)

    def toggle_preview(self):
        self.preview.setVisible(self.preview_button.isChecked())

    def set_kind(self, kind):
        self.proxy.kind = kind
        self.proxy.invalidateFilter()
        for value, item in self.filter_buttons.items():
            item.setChecked(value == kind)
        self.update_count()

    def cancel_search(self):
        if self.search_job:
            self.search_job.stop.set()
            self.search_job = None

    def queue_search(self, _text=None):
        self.cancel_search()
        self.subtitle.setText('Suche wird aktualisiert …')
        self.debounce.start()

    def start_search(self):
        self.cancel_search()
        query = self.search.text().strip()
        if not query:
            self.proxy.setSourceModel(self.fs)
            self.view.setRootIndex(self.proxy.mapFromSource(self.fs.index(self.current_path)))
            self.configure_columns()
            self.subtitle.setText('Deine Dateien. Alles im Blick.')
            self.update_count()
            return
        self.results.removeRows(0, self.results.rowCount())
        self.proxy.setSourceModel(self.results)
        self.view.setRootIndex(QModelIndex())
        self.configure_columns()
        self.preview.clear()
        self.search_errors = self.search_total = 0
        job = SearchWorker(self.current_path, query, self.hidden)
        self.search_job = job
        self.search_jobs.append(job)
        job.batch.connect(lambda paths: self.add_results(job, paths))
        job.progress.connect(lambda count, errors: self.search_progress(job, count, errors))
        job.summary.connect(lambda count, limited, elapsed: self.search_done(job, count, limited, elapsed))
        job.finished.connect(lambda: self.release_search(job))
        self.subtitle.setText('Suche läuft · Dateinamen · einschließlich Unterordnern')
        job.start()

    def release_search(self, job):
        if job in self.search_jobs:
            self.search_jobs.remove(job)
        job.deleteLater()

    def add_results(self, job, paths):
        if self.search_job is not job:
            return
        self.proxy.setDynamicSortFilter(False)
        for path in paths:
            info = QFileInfo(path)
            items = [QStandardItem(value) for value in [info.fileName(),
                     '—' if info.isDir() else size_text(info.size()),
                     'Ordner' if info.isDir() else info.suffix().upper(),
                     info.lastModified().toString('dd.MM.yy HH:mm'),
                     os.path.relpath(info.absolutePath(), self.current_path)]]
            items[0].setIcon(self.icon_provider.icon(info))
            items[0].setData(path, Qt.UserRole)
            items[0].setToolTip(path)
            items[1].setData(info.size(), Qt.UserRole + 1)
            items[3].setData(info.lastModified().toMSecsSinceEpoch(), Qt.UserRole + 1)
            for item in items:
                item.setEditable(False)
            self.results.appendRow(items)
        self.proxy.setDynamicSortFilter(True)
        self.proxy.invalidate()
        self.update_count()

    def search_progress(self, job, count, errors):
        if self.search_job is job:
            self.search_errors, self.search_total = errors, count
            self.subtitle.setText(f'Suche läuft · {count:,} Einträge geprüft · Unterordner einbezogen')

    def search_done(self, job, count, limited, elapsed):
        if self.search_job is job:
            self.search_job = None
            detail = f'{count:,} Treffer · {elapsed:.2f} s · Dateinamen in Unterordnern'
            if limited:
                detail += ' · Limit 5.000 erreicht — Suche eingrenzen'
            if self.search_errors:
                detail += f' · {self.search_errors} nicht lesbare Einträge übersprungen'
            self.subtitle.setText(detail)
            self.update_count()

    def update_count(self):
        if not hasattr(self, 'status'):
            return
        count = self.proxy.rowCount(self.view.rootIndex())
        selected = len(self.selected_paths())
        self.status.setText(f'{count:,} Einträge' + (f'  ·  {selected} ausgewählt' if selected else ''))
        self.empty_label.setText(('Suche läuft …' if self.search_job else 'Keine Einträge. Suche oder Filter anpassen.') if count == 0 else '')
        self.empty_label.setVisible(count == 0)

    def selected_paths(self):
        return [self.proxy.path(index) for index in self.view.selectionModel().selectedRows() if index.isValid()]

    def selection_changed(self, *_args):
        if hasattr(self, 'preview_delay'):
            self.preview_delay.start()
        self.update_count()

    def preview_selection(self):
        paths = self.selected_paths()
        if len(paths) == 1:
            remote = self.network.remote(str(Path(paths[0]).parent))
            self.preview.show_path(paths[0], display_url(remote) if remote else None)
        else:
            self.preview.clear()
            if paths:
                self.preview.title.setText(f'{len(paths)} ausgewählt')
                self.preview.show_message('Eine einzelne Datei auswählen,\num die Vorschau zu sehen.')

    def open_index(self, index):
        path = self.proxy.path(index)
        if path:
            self.open_path(path)

    def open_selected(self):
        paths = self.selected_paths()
        if paths:
            self.open_path(paths[0])

    def open_path(self, path):
        if Path(path).is_dir():
            self.navigate(path)
        elif file_kind(path) == 'image':
            self.open_gallery(path)
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.error('Die Datei konnte nicht geöffnet werden.', path)

    def quicklook(self):
        paths = self.selected_paths()
        if len(paths) != 1:
            return
        if file_kind(paths[0]) == 'image' and not Path(paths[0]).is_dir():
            self.open_gallery(paths[0])
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(Path(paths[0]).name + ' — Vorschau')
        dialog.resize(980, 780)
        layout = QVBoxLayout(dialog)
        preview = Preview()
        layout.addWidget(preview)
        remote = self.network.remote(str(Path(paths[0]).parent))
        preview.show_path(paths[0], display_url(remote) if remote else None)
        QShortcut(QKeySequence('Space'), dialog, activated=dialog.accept)
        dialog.finished.connect(preview.cancel)
        dialog.exec_()
        dialog.deleteLater()

    def open_gallery(self, path):
        paths = [self.proxy.path(self.proxy.index(row, 0, self.view.rootIndex()))
                 for row in range(self.proxy.rowCount(self.view.rootIndex()))]
        images = [p for p in paths if file_kind(p) == 'image']
        if path not in images:
            images.append(path)
        self.preview.cancel()
        dialog = Gallery(images, path, self)
        dialog.exec_()
        for row in range(self.proxy.rowCount(self.view.rootIndex())):
            index = self.proxy.index(row, 0, self.view.rootIndex())
            if self.proxy.path(index) == dialog.path:
                self.view.setCurrentIndex(index)
                break
        dialog.deleteLater()
        self.refresh()

    def copy(self, cut):
        paths = self.selected_paths()
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        mime.setData('application/x-kde-cutselection', b'1' if cut else b'0')
        mime.setData('x-special/gnome-copied-files', (('cut' if cut else 'copy') + '\n' +
                     '\n'.join(QUrl.fromLocalFile(path).toString() for path in paths)).encode())
        QApplication.clipboard().setMimeData(mime)
        self.activity.setText(f'{len(paths)} zum {"Verschieben" if cut else "Kopieren"} vorgemerkt')

    def paste(self):
        mime = QApplication.clipboard().mimeData()
        if not mime:
            return
        paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
        cut = bytes(mime.data('application/x-kde-cutselection')) == b'1'
        if paths:
            self.run_operation('move' if cut else 'copy', paths, self.current_path)

    def run_operation(self, action, paths, target=None):
        if self.file_job:
            self.error('Bitte den laufenden Dateivorgang abwarten.')
            return
        job = FileWorker(action, paths, target, portable=bool(target and self.network.remote(target)))
        self.file_job = job
        job.progress.connect(lambda name: self.activity.setText(f'Dateivorgang: {name}'))
        def completed(done, errors):
            self.activity.setText(f'{len(done)} Einträge verarbeitet' + (f' · {len(errors)} Fehler' if errors else ''))
            if action == 'move' and done:
                mime = QApplication.clipboard().mimeData()
                current = [u.toLocalFile() for u in mime.urls()] if mime else []
                if current == paths:
                    remaining = [p for p in paths if p not in done]
                    replacement = QMimeData()
                    replacement.setUrls([QUrl.fromLocalFile(p) for p in remaining])
                    replacement.setData('application/x-kde-cutselection', b'1')
                    QApplication.clipboard().setMimeData(replacement)
            if errors:
                self.error('Nicht alle Einträge konnten verarbeitet werden.', '\n\n'.join(errors))
            self.refresh()
        def finished():
            self.file_job = None
            job.deleteLater()
        job.completed.connect(completed)
        job.finished.connect(finished)
        job.start()

    def mkdir(self):
        name, ok = QInputDialog.getText(self, 'Neuer Ordner', 'Name des Ordners:')
        if ok:
            try:
                path = Path(self.current_path) / valid_name(name)
                self.run_operation('mkdir', [str(path)])
            except ValueError as exc:
                self.error(str(exc))

    def rename(self):
        paths = self.selected_paths()
        if len(paths) != 1:
            return
        path = Path(paths[0])
        name, ok = QInputDialog.getText(self, 'Umbenennen', 'Neuer Name:', text=path.name)
        if ok and name != path.name:
            try:
                self.run_operation('rename', paths, str(path.with_name(valid_name(name))))
            except ValueError as exc:
                self.error(str(exc))

    def trash(self):
        paths = self.selected_paths()
        if paths and QMessageBox.question(self, 'In den Papierkorb',
                f'{len(paths)} ausgewählte Einträge in den Papierkorb verschieben?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.run_operation('trash', paths)

    def context_menu(self, position):
        index = self.view.indexAt(position)
        if index.isValid() and not self.view.selectionModel().isSelected(index):
            self.view.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        paths = self.selected_paths()
        menu = QMenu(self)
        if paths:
            menu.addAction('Öffnen', self.open_selected)
            if len(paths) == 1:
                menu.addAction('Große Vorschau\tLeertaste', self.quicklook)
                menu.addAction('Enthaltenden Ordner öffnen', lambda: self.navigate(Path(paths[0]).parent))
                if Path(paths[0]).is_dir():
                    menu.addAction('In neuem Tab öffnen', lambda: self.new_tab(paths[0]))
                menu.addAction('Umbenennen\tF2', self.rename)
            menu.addSeparator()
            menu.addAction('Kopieren\tStrg+C', lambda: self.copy(False))
            menu.addAction('Ausschneiden\tStrg+X', lambda: self.copy(True))
            menu.addAction('Pfad kopieren', lambda: QApplication.clipboard().setText('\n'.join(self.network.remote(p) or p for p in paths)))
            menu.addSeparator()
            menu.addAction('In den Papierkorb\tEntf', self.trash)
        menu.addAction('Hier einfügen\tStrg+V', self.paste)
        menu.addAction('Neuer Ordner', self.mkdir)
        menu.exec_(self.view.viewport().mapToGlobal(position))

    def refresh(self):
        if self.search.text().strip():
            self.start_search()
        else:
            # QFileSystemModel watches the current directory; preserve selection and scroll.
            self.view.viewport().update()
            QTimer.singleShot(150, self.update_count)
        self.populate_places()

    def escape(self):
        if self.connection_request:
            self.cancel_connection()
        elif self.path_stack.currentWidget() is self.path_edit:
            self.path_stack.setCurrentWidget(self.crumbs)
            self.view.setFocus()
        elif self.search.text():
            self.search.clear()
            self.view.setFocus()

    def show_menu(self):
        menu = QMenu(self)
        menu.addAction('Mit Server verbinden\tStrg+K', self.connect_dialog)
        menu.addAction('Aktualisieren\tF5', self.refresh)
        menu.addAction('Versteckte Dateien\tStrg+H', self.toggle_hidden)
        menu.addSeparator()
        menu.addAction('Tastenkürzel & Info', lambda: QMessageBox.information(self, 'Lumen Files',
            'Lumen Files · 0.2\n\nStrg+F  Suchen\nStrg+L  Pfad eingeben\nStrg+K  Server verbinden\n'
            'Strg+T / Strg+W  Tab öffnen / schließen\nAlt+Pfeile  Navigation\n'
            'Leertaste  Große Vorschau\nF2  Umbenennen\nStrg+C / X / V  Kopieren / Ausschneiden / Einfügen\n'
            'Entf  Papierkorb\n\nSuche: Dateinamen im aktuellen Ordner und Unterordnern. '
            'Mehrere Wörter müssen alle im Namen vorkommen. Maximal 5.000 Treffer; kein Volltextindex.\n\n'
            'PDFs sind blätterbar. Videos zeigen ein Standbild, Audio eine Wellenform. Wiedergabe in der Standard-App.'))
        menu.exec_(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def error(self, message, detail=''):
        box = QMessageBox(QMessageBox.Warning, 'Lumen Files', message, QMessageBox.Ok, self)
        box.setTextFormat(Qt.PlainText)
        if detail:
            box.setDetailedText(detail)
        box.exec_()

    def closeEvent(self, event):
        if self.file_job and self.file_job.isRunning():
            self.error('Es läuft noch ein Dateivorgang. Bitte vor dem Schließen abwarten.')
            event.ignore()
            return
        self.cancel_search()
        self.cancel_connection()
        self.preview.cancel()
        for job in self.search_jobs[:]:
            job.stop.set()
            if not job.wait(1500):
                self.activity.setText('Suche wird beendet. Bitte gleich erneut schließen.')
                event.ignore()
                return
        self.settings.setValue('last_path', self.current_location)
        self.settings.setValue('geometry', self.saveGeometry())
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'view'):
            self.view.setColumnHidden(3, self.width() < 1180)


def create_app():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setApplicationName('Lumen Files')
    app.setDesktopFileName('lumen-files')
    app.translator = QTranslator(app)
    app.translator.load('qtbase_de', QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    app.installTranslator(app.translator)
    kde = QSettings(str(Path.home() / '.config/kdeglobals'), QSettings.IniFormat)
    QIcon.setThemeSearchPaths([str(Path(path) / 'icons') for path in
                             QStandardPaths.standardLocations(QStandardPaths.GenericDataLocation)]
                             + QIcon.themeSearchPaths())
    QIcon.setThemeName(kde.value('Icons/Theme', 'breeze-dark'))
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in [(QPalette.Window, '#191f29'), (QPalette.WindowText, '#e6ebf2'),
                        (QPalette.Base, '#1c2430'), (QPalette.AlternateBase, '#222c39'),
                        (QPalette.Text, '#e6ebf2'), (QPalette.Button, '#293544'),
                        (QPalette.ButtonText, '#e6ebf2'), (QPalette.Highlight, '#304f53'),
                        (QPalette.HighlightedText, '#effffb'), (QPalette.ToolTipBase, '#293544'),
                        (QPalette.ToolTipText, '#e6ebf2')]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet((ROOT / 'style.qss').read_text())
    return app


if __name__ == '__main__':
    app = create_app()
    start = sys.argv[1] if len(sys.argv) > 1 else None
    if start and start.startswith('file:'):
        start = QUrl(start).toLocalFile()
    if start and Path(start).is_file():
        start = str(Path(start).parent)
    window = Window(start)
    window.show()
    sys.exit(app.exec_())
