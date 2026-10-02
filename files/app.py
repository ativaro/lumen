#!/usr/bin/python3
"""Lumen Files — a preview-first native file manager for Linux."""
import os
import sys
from pathlib import Path

if __name__ == '__main__':
    from lumen_crash import supervise
    supervise('files')

from PyQt5.QtCore import (QDir, QEvent, QFileInfo, QItemSelectionModel, QMimeData, QModelIndex, QRect, QRectF,
                          QSettings, QSize, QSortFilterProxyModel, QStandardPaths, QFileSystemWatcher,
                          QStorageInfo, Qt, QTimer, QTranslator, QLibraryInfo, QUrl)
from PyQt5.QtGui import QDesktopServices, QIcon, QKeySequence, QPalette, QColor, QFont, QPainterPath, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDockWidget, QFileIconProvider,
                             QFileSystemModel, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QShortcut, QSizePolicy,
                             QSlider, QSplitter, QStackedWidget, QStyle, QStyleOptionViewItem, QStyledItemDelegate, QTabBar, QTreeView, QVBoxLayout, QWidget)
from core import FileWorker, SearchWorker, file_kind, size_text, valid_name
from network import Network, ConnectDialog, display_url, is_network_address, normalize_url, server_label
from preview import Preview, label
from gallery import Gallery, ImageLoader
from disk_analysis import DiskAnalysis
from file_spaces import LIBRARY, SHELF, virtual
from file_spaces_ui import FileSpaces, ShelfButton
from folder_icons import folder_icons

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
        self.folder_sizes = {}
        self.folder_icons = folder_icons()
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)

    def data(self, index, role=Qt.DisplayRole):
        if index.column() == 0 and role == Qt.DecorationRole and self.directory(index):
            source = self.sourceModel()
            if isinstance(source, QFileSystemModel) and source.fileInfo(self.mapToSource(index)).isSymLink():
                return super().data(index, role)
            return self.folder_icons.get(self.path(index), self.folder_icons[''])
        if index.column() == 1 and role in (Qt.DisplayRole, Qt.ToolTipRole, Qt.ForegroundRole) and self.directory(index):
            value = self.folder_sizes.get(self.path(index))
            if role == Qt.DisplayRole:
                return size_text(value) if value is not None else 'Berechnen'
            if role == Qt.ToolTipRole:
                return ('Klick: Ordnergröße einschließlich Unterordnern berechnen. '
                        'Berechnete Werte sind eine Momentaufnahme; F5 setzt sie zurück.')
            if value is None:
                return QApplication.palette().brush(QPalette.Link)
        if role == Qt.DisplayRole and index.column() == 3 and isinstance(self.sourceModel(), QFileSystemModel):
            return self.sourceModel().fileInfo(self.mapToSource(index)).lastModified().toString('dd.MM.yy HH:mm')
        return super().data(index, role)

    def path(self, index):
        index = self.mapToSource(index.sibling(index.row(), 0))
        model = self.sourceModel()
        return model.filePath(index) if isinstance(model, QFileSystemModel) else index.data(Qt.UserRole)

    def directory(self, index):
        if not index.isValid(): return False
        source = self.mapToSource(index)
        model = self.sourceModel()
        return model.isDir(source) if isinstance(model, QFileSystemModel) else source.sibling(source.row(), 2).data() == 'Ordner'

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
            if index.sibling(row, 2).data() == 'Ordner':
                return True
        kind = file_kind(path)
        return kind in {'pdf', 'text'} if self.kind == 'document' else kind == self.kind

    def lessThan(self, left, right):
        model = self.sourceModel()
        if isinstance(model, QFileSystemModel):
            a, b = model.fileInfo(left), model.fileInfo(right)
            if a.isDir() != b.isDir():
                return a.isDir() if self.sortOrder() == Qt.AscendingOrder else b.isDir()
            if left.column() == 1:
                if a.isDir():
                    return self.folder_sizes.get(model.filePath(left), -1) < self.folder_sizes.get(model.filePath(right), -1)
                return a.size() < b.size()
            if left.column() == 3:
                return a.lastModified() < b.lastModified()
        else:
            a, b = left.data(Qt.UserRole + 1), right.data(Qt.UserRole + 1)
            if left.column() == 1:
                if left.sibling(left.row(), 2).data() == 'Ordner':
                    a = self.folder_sizes.get(left.sibling(left.row(), 0).data(Qt.UserRole), -1)
                if right.sibling(right.row(), 2).data() == 'Ordner':
                    b = self.folder_sizes.get(right.sibling(right.row(), 0).data(Qt.UserRole), -1)
            if a is not None and b is not None:
                return a < b
        return super().lessThan(left, right)


class PlacesDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setWidth(self.parent().viewport().width())
        return size


class FileDropMixin:
    def __init__(self, window):
        super().__init__()
        self.main_window = window
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDropIndicatorShown(True)

    def startDrag(self, supported):
        from PyQt5.QtGui import QDrag
        paths = self.main_window.selected_paths()
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
        target = None if virtual(self.main_window.current_location) else self.main_window.current_path
        if index.isValid():
            path = self.main_window.proxy.path(index)
            if Path(path).is_dir():
                target = path
        if paths:
            target = target or self.main_window.spaces.choose_target()
            if not target: return
            self.main_window.run_operation('copy', paths, target)
            event.setDropAction(Qt.CopyAction)
            event.accept()


class FileView(FileDropMixin, QTreeView):
    pass


class ThumbnailDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return self.parent().gridSize()

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        grid = self.parent()
        path = grid.model().path(index)
        cached = grid.loader.cache.get(path)
        if cached:
            grid.loader.cache.move_to_end(path)
            option.icon = QIcon(cached[0])
        elif (file_kind(path) == 'image' and path not in grid.failed
              and path != grid.loader.loading and path not in grid.loader.pending):
            if len(grid.loader.pending) < grid.loader.cache_limit:
                grid.loader.pending.append(path)
                grid.load_timer.start()

    def paint(self, painter, option, index):
        grid = self.parent()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # PyQt exposes a borrowed QIcon here; copy before clearing the option.
        icon, name = QIcon(opt.icon), index.data(Qt.DisplayRole) or ''
        opt.text, opt.icon = '', QIcon()
        opt.state &= ~QStyle.State_HasFocus
        opt.rect = option.rect.adjusted(5, 3, -5, -3)
        grid.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, grid)
        rect = option.rect.adjusted(10, 8, -10, -8)
        photo = QRect(rect.x(), rect.y(), rect.width(), rect.height() - 48)
        path = grid.model().path(index)
        cached = grid.loader.cache.get(path)
        painter.save()
        if cached:
            clip = QPainterPath(); clip.addRoundedRect(QRectF(photo), 5, 5)
            painter.setClipPath(clip)
            painter.fillRect(photo, option.palette.alternateBase())
            pixmap = cached[0].scaled(photo.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(photo.x() + (photo.width() - pixmap.width()) // 2,
                               photo.y() + (photo.height() - pixmap.height()) // 2, pixmap)
            painter.setClipping(False)
        else:
            # Ordinary files/folders keep their native icon, without a photo tile.
            side = min(100, photo.width() - 24, photo.height() - 8)
            icon.paint(painter, QRect(photo.center().x() - side // 2,
                                     photo.bottom() - side + 4, side, side), Qt.AlignCenter)
        font = QFont(option.font); font.setBold(False); painter.setFont(font)
        painter.setPen(option.palette.color(QPalette.Text))
        text_rect = QRect(rect.x(), photo.bottom() + 7, rect.width(), 20)
        alignment = Qt.AlignLeft if cached else Qt.AlignHCenter
        painter.drawText(text_rect, alignment | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(name, Qt.ElideMiddle, text_rect.width()))
        if option.state & QStyle.State_HasFocus:
            # A quiet caption underline keeps keyboard focus visible without a giant tile.
            painter.fillRect(text_rect.x() + 8, text_rect.bottom() + 2,
                             text_rect.width() - 16, 1, option.palette.color(QPalette.Link))
        local_model = isinstance(grid.model().sourceModel(), QFileSystemModel)
        remote = grid.main_window.network.remote(path)
        origin = (QUrl(remote).host() if remote else '') if local_model else index.data(Qt.UserRole + 2) or ''
        amount = (size_text(grid.model().folder_sizes[path]) if path in grid.model().folder_sizes
                  else index.sibling(index.row(), 1).data(Qt.DisplayRole) if not grid.model().directory(index) else '')
        if amount:
            origin = ' · '.join(part for part in (origin, str(amount)) if part)
        font.setBold(False); font.setPointSizeF(max(9, font.pointSizeF() - 1)); painter.setFont(font)
        painter.setPen(option.palette.color(QPalette.Dark))
        painter.drawText(text_rect.translated(0, 21), alignment | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(origin, Qt.ElideMiddle, text_rect.width()))
        painter.restore()


class FileGrid(FileDropMixin, QListView):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName('fileGrid')
        self.setAccessibleName('Dateien als Bildraster')
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(ThumbnailDelegate(self))
        self.loader = ImageLoader(self, max_side=256, cache_limit=256)
        self.failed = set()
        self.load_timer = QTimer(self)
        self.load_timer.setSingleShot(True)
        self.load_timer.setInterval(20)
        self.load_timer.timeout.connect(self.loader.advance)
        self.loader.ready.connect(lambda *_: self.viewport().update())
        self.loader.failed.connect(self.load_failed)

    def load_failed(self, path, _message):
        if len(self.failed) >= self.loader.cache_limit:
            self.failed.clear()
        self.failed.add(path)

    def reset_thumbnails(self, *_):
        self.load_timer.stop()
        self.loader.pending.clear()
        self.loader.cancel()
        self.loader.cache.clear()
        self.failed.clear()
        self.viewport().update()

    def paintEvent(self, event):
        # Queue only visible items; scrolling abandons work that has not started.
        self.loader.pending.clear()
        super().paintEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_metrics()

    def update_metrics(self):
        desired = self.iconSize().width() + 32
        width = max(desired, self.viewport().width())
        columns = max(1, round((width - 12) / desired))
        cell = max(80, (width - 12) // columns)
        self.setGridSize(QSize(cell, int(desired * .50) + 62))

    def hideEvent(self, event):
        self.load_timer.stop()
        self.loader.pending.clear()
        self.loader.cancel()
        super().hideEvent(event)


class Window(QMainWindow):
    def __init__(self, start=None, settings=None, catalog=None):
        super().__init__()
        self.settings = settings or QSettings('Lumen', 'Files')
        self.setWindowTitle('Lumen Files')
        self.setObjectName('filesWindow')
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
        self.spaces = FileSpaces(self, catalog)
        self.connection_request = None
        self.hidden = self.settings.value('hidden', False, type=bool)
        self.icon_provider = QFileIconProvider()
        self.fs = QFileSystemModel(self)
        self.fs.setReadOnly(True)
        self.fs.setOption(QFileSystemModel.DontUseCustomDirectoryIcons, True)
        self.apply_hidden()
        self.fs.setRootPath(str(Path.home()))
        self.fs.directoryLoaded.connect(lambda _path: self.update_count())
        self.fs.directoryLoaded.connect(self.spaces.directory_loaded)
        self.results = QStandardItemModel(self)
        self.results.setHorizontalHeaderLabels(['Name', 'Größe', 'Typ', 'Geändert', 'Ordner'])
        self.proxy = FileFilter(self)
        self.proxy.setSourceModel(self.fs)
        self.build_ui()
        from offline_ui import Offline
        self.offline = Offline(self)
        self.offline.catalogChanged.connect(self.populate_places)
        self.network.connected.connect(self.network_connected)
        self.network.failed.connect(self.network_failed)
        self.network.busy.connect(self.cancel_connect_button.setVisible)
        self.install_shortcuts()
        QShortcut(QKeySequence("Ctrl+J"), self, activated=lambda: self.ask_lumen("open", self.context_paths()))
        QShortcut(QKeySequence('Ctrl+Shift+F'), self, activated=self.search_contents)
        QShortcut(QKeySequence('Ctrl+,'), self, activated=self.show_settings)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(max(100, min(1500, self.settings.value('searchDelay', 250, type=int))))
        self.debounce.timeout.connect(self.start_search)
        self.search.textChanged.connect(self.queue_search)
        self.preview_delay = QTimer(self)
        self.preview_delay.setSingleShot(True)
        self.preview_delay.setInterval(100)
        self.preview_delay.timeout.connect(self.preview_selection)
        self.session_save = QTimer(self)
        self.session_save.setSingleShot(True)
        self.session_save.setInterval(500)
        self.session_save.timeout.connect(self.save_session)
        resume = self.settings.value('restoreLastFolder', True, type=bool)
        saved_paths = self.settings.value('session/tabs', [], type=list) if resume and not start else []
        paths = []
        saved_active = self.settings.value('session/activeTab', 0, type=int)
        restored_active = 0
        for position, path in enumerate(saved_paths):
            if isinstance(path, str):
                try:
                    if virtual(path):
                        pass
                    elif is_network_address(path):
                        path = normalize_url(path)
                    elif not Path(path).is_dir():
                        continue
                    if position == saved_active:
                        restored_active = len(paths)
                    paths.append(path)
                except ValueError:
                    pass
        for path in paths:
            self.new_tab(path, activate=False)
        if paths:
            index = restored_active
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
            self.switch_tab(index)
        else:
            startup_key = 'last_path' if resume else 'startFolder'
            self.new_tab(start or self.settings.value(startup_key, str(Path.home())))
        self.preview_button.setChecked(self.settings.value('previewVisible', True, type=bool))
        self.preview.setVisible(self.preview_button.isChecked())
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        splitter = self.settings.value('session/splitter')
        if splitter:
            self.splitter.restoreState(splitter)
        self.view.sortByColumn(max(0, min(3, self.settings.value('session/sortColumn', 0, type=int))),
                               Qt.DescendingOrder if self.settings.value('session/sortDescending', False, type=bool) else Qt.AscendingOrder)
        self.view.header().sortIndicatorChanged.connect(lambda *_: self.session_save.start())
        self.splitter.splitterMoved.connect(lambda *_: self.session_save.start())
        self.set_view_mode(self.settings.value('viewMode', 'list'))

    def build_ui(self):
        central = QWidget()
        central.setObjectName('filesSurface')
        self.setCentralWidget(central)
        font = QFont(self.font()); font.setPixelSize(14); central.setFont(font)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        tabstrip = QFrame(); tabstrip.setObjectName('tabStrip')
        tabrow = QHBoxLayout(tabstrip)
        tabrow.setContentsMargins(20, 9, 16, 9)
        brand = label('Dateien', 'brand')
        brand.setFixedWidth(202)
        tabrow.addWidget(brand)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self.switch_tab)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        tabrow.addWidget(self.tabs)
        new_tab = button('+', lambda: self.new_tab(self.current_location), tip='Neuer Tab · Strg+T')
        new_tab.setObjectName('toolButton'); new_tab.setFixedSize(30, 30)
        tabrow.addWidget(new_tab)
        tabrow.addStretch()
        self.room_button = button('Arbeitsräume', self.spaces.room_menu, 'folder-favorites')
        self.room_button.setObjectName('toolButton')
        self.room_button.setMaximumWidth(200)
        tabrow.addWidget(self.room_button)
        settings_button = button('', self.show_settings, 'configure', 'Einstellungen · Strg+Komma')
        settings_button.setObjectName('toolButton')
        tabrow.addWidget(settings_button)
        layout.addWidget(tabstrip)
        header = QFrame()
        header.setObjectName('appHeader')
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(8)
        navigation = QWidget()
        navigation.setFixedWidth(112)
        nav_buttons = QHBoxLayout(navigation)
        nav_buttons.setContentsMargins(0, 0, 0, 0)
        nav_buttons.setSpacing(4)
        self.back_button = button('', lambda: self.history(-1), 'go-previous', 'Zurück · Alt+Links')
        self.forward_button = button('', lambda: self.history(1), 'go-next', 'Vorwärts · Alt+Rechts')
        for item in (self.back_button, self.forward_button,
                     button('', self.up, 'go-up', 'Übergeordneter Ordner · Alt+Hoch')):
            item.setObjectName('iconButton')
            item.setFixedSize(32, 32)
            nav_buttons.addWidget(item)
        nav_buttons.addStretch()
        row.addWidget(navigation)
        self.heading = label('', 'heading')
        self.heading.setWordWrap(False)
        self.heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.heading.setParent(header); self.heading.hide()
        self.path_stack = QStackedWidget()
        self.crumbs = QScrollArea()
        self.crumbs.setFrameShape(QFrame.NoFrame)
        self.crumbs.setFixedHeight(36)
        self.crumbs.setWidgetResizable(True)
        self.crumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.crumbs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.crumbs.horizontalScrollBar().rangeChanged.connect(
            lambda _minimum, maximum: self.crumbs.horizontalScrollBar().setValue(maximum))
        crumb_content = QWidget()
        self.crumbs.setWidget(crumb_content)
        self.crumbs.viewport().setAutoFillBackground(False)
        crumb_content.setAutoFillBackground(False)
        self.crumb_layout = QHBoxLayout(crumb_content)
        self.crumb_layout.setContentsMargins(6, 0, 0, 0)
        self.crumb_layout.setSpacing(0)
        self.path_edit = QLineEdit()
        self.path_edit.setAccessibleName('Ordnerpfad')
        self.path_edit.returnPressed.connect(lambda: self.navigate(self.path_edit.text()))
        self.path_stack.addWidget(self.crumbs)
        self.path_stack.addWidget(self.path_edit)
        self.path_stack.setMinimumWidth(80)
        self.path_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.path_stack, 1)
        edit_path = button('', self.edit_path, 'document-edit', 'Pfad eingeben · Strg+L')
        edit_path.setObjectName('toolButton'); row.addWidget(edit_path)
        self.search = QLineEdit()
        self.search.setObjectName('search')
        self.search.setAccessibleName('Dateien im aktuellen Ordner und Unterordnern suchen')
        self.search.setPlaceholderText('Suchen')
        self.search.setToolTip('Dateinamen in diesem Ordner und Unterordnern suchen · Strg+F')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(180)
        self.search.setMaximumWidth(280)
        self.search.addAction(QIcon.fromTheme('edit-find'), QLineEdit.LeadingPosition)
        row.addWidget(self.search, 1)
        contents = self.search.addAction(QIcon.fromTheme('edit-find-replace'), QLineEdit.TrailingPosition)
        contents.setToolTip('In Dateiinhalten suchen · Strg+Umschalt+F')
        contents.triggered.connect(self.search_contents)
        new_folder = button('', self.mkdir, 'folder-new', 'Neuer Ordner · Strg+Umschalt+N')
        new_folder.setObjectName('toolButton'); row.addWidget(new_folder)
        self.preview_button = button('', self.toggle_preview, 'view-preview', 'Vorschauleiste ein-/ausblenden')
        self.preview_button.setObjectName('toolButton')
        self.preview_button.setCheckable(True)
        self.preview_button.setChecked(True)
        row.addWidget(self.preview_button)
        lumen = button('Lumen', lambda: self.ask_lumen('open', self.context_paths()), tip='Lumen öffnen · Strg+J')
        lumen.setObjectName('assistantButton')
        row.addWidget(lumen)
        menu_button = button('···', self.show_menu, tip='Weitere Aktionen und Ansicht')
        menu_button.setObjectName('iconButton')
        row.addWidget(menu_button)
        layout.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 14, 14, 10)
        side.setSpacing(4)
        side.addWidget(label('Favoriten', 'eyebrow'))
        self.places = QListWidget()
        self.places.setObjectName('places')
        self.places.setIconSize(QSize(20, 20))
        self.places.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.places.setTextElideMode(Qt.ElideRight)
        self.places.setUniformItemSizes(True)
        self.places.setItemDelegate(PlacesDelegate(self.places))
        self.places.itemClicked.connect(lambda item: self.navigate(item.data(Qt.UserRole)))
        self.places.setContextMenuPolicy(Qt.CustomContextMenu)
        self.places.customContextMenuRequested.connect(self.place_menu)
        self.populate_places()
        side.addWidget(self.places, 1)
        connections = QHBoxLayout()
        connections.setSpacing(6)
        connect = button('Server verbinden', self.connect_dialog, 'network-server')
        favorite = button('', self.add_favorite, 'bookmark-new', 'Diesen Ort merken')
        favorite.setFixedWidth(30)
        analysis = button('Speicheranalyse', self.open_analysis, 'drive-harddisk')
        for action in (connect, favorite, analysis):
            action.setObjectName('sideAction')
        connections.addWidget(connect, 1)
        connections.addWidget(favorite)
        side.addLayout(connections)
        side.addWidget(analysis)
        self.disk_label = label('', 'muted')
        side.addWidget(self.disk_label)
        self.location_badge = label('LOKAL AUF DEINEM RECHNER', 'tiny')
        side.addWidget(self.location_badge)
        body.addWidget(sidebar)
        content = QVBoxLayout()
        content.setSpacing(0)
        self.source_bar = QWidget()
        source_row = QHBoxLayout(self.source_bar)
        source_row.setContentsMargins(18, 4, 16, 4)
        self.sources_button = button('Quellen …', self.spaces.sources_action)
        self.source_status = button('', self.spaces.source_details)
        self.source_status.setObjectName('crumb')
        source_row.addWidget(self.sources_button)
        source_row.addWidget(self.source_status, 1)
        self.stop_sources = button('Stoppen', self.spaces.stop_loading)
        source_row.addWidget(self.stop_sources)
        self.source_bar.hide()
        content.addWidget(self.source_bar)
        self.splitter = QSplitter()
        file_area = QWidget()
        file_area.setObjectName('fileArea')
        files = QVBoxLayout(file_area)
        files.setContentsMargins(20, 12, 20, 12)
        files.setSpacing(8)
        self.subtitle = label('', 'muted')
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
        self.view_buttons = {}
        for mode, icon, tip in [('list', 'view-list-details', 'Listenansicht · Strg+1'),
                                ('grid', 'view-list-icons', 'Bildraster · Strg+2')]:
            item = button('', lambda _=False, m=mode: self.set_view_mode(m), icon, tip)
            item.setObjectName('toolButton')
            item.setCheckable(True)
            item.setFixedWidth(32)
            self.view_buttons[mode] = item
            filters.addWidget(item)
        self.hidden_button = button('', self.toggle_hidden, 'view-hidden', 'Versteckte Dateien · Strg+H')
        self.hidden_button.setObjectName('toolButton')
        self.hidden_button.setCheckable(True)
        self.hidden_button.setChecked(self.hidden)
        filters.addWidget(self.hidden_button)
        files.addLayout(filters)
        self.view = FileView(self)
        self.view.setObjectName('files')
        self.view.setAccessibleName('Dateiliste')
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setUniformRowHeights(True)
        self.view.setIconSize(QSize(20, 20))
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(False)
        self.view.setSortingEnabled(True)
        self.view.setModel(self.proxy)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        self.view.doubleClicked.connect(self.open_index)
        self.view.clicked.connect(self.size_clicked)
        self.view.selectionModel().selectionChanged.connect(self.selection_changed)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.configure_columns()
        self.grid = FileGrid(self)
        self.grid.setModel(self.proxy)
        self.grid.setSelectionModel(self.view.selectionModel())
        self.grid.doubleClicked.connect(self.open_index)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self.context_menu)
        self.proxy.dataChanged.connect(self.grid.reset_thumbnails)
        self.fs.directoryLoaded.connect(lambda path: self.grid.reset_thumbnails() if path == self.current_path else None)
        self.file_stack = QStackedWidget()
        self.file_stack.addWidget(self.view)
        self.file_stack.addWidget(self.grid)
        files.addWidget(self.file_stack, 1)
        self.empty_label = label('', 'muted')
        self.empty_label.setAlignment(Qt.AlignCenter)
        files.addWidget(self.empty_label)
        self.splitter.addWidget(file_area)
        self.preview = Preview()
        self.preview.openImage.connect(self.open_gallery)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([780, 320])
        content.addWidget(self.splitter, 1)
        body.addLayout(content, 1)
        layout.addLayout(body, 1)
        self.shelf_bar = QFrame()
        self.shelf_bar.setObjectName('shelfBar')
        shelf_row = QHBoxLayout(self.shelf_bar)
        shelf_row.setContentsMargins(0, 0, 0, 0); shelf_row.setSpacing(4)
        self.spaces.shelf_button = ShelfButton(self.spaces)
        self.spaces.shelf_button.setObjectName('shelfButton')
        self.spaces.shelf_button.setToolTip('Dateien hier sammeln · Ziehen oder aus der Auswahl hinzufügen')
        shelf_row.addWidget(self.spaces.shelf_button)
        self.spaces.shelf_summary = QLabel('Dateien hier sammeln — Originale bleiben an ihrem Ort')
        self.spaces.shelf_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.spaces.shelf_summary.setParent(self.shelf_bar); self.spaces.shelf_summary.hide()
        collect = button('', lambda: self.spaces.collect(self.selected_paths()), 'list-add', 'Auswahl zur Sammelfläche hinzufügen')
        collect.setObjectName('toolButton'); shelf_row.addWidget(collect)
        shelf_actions = button('···', self.spaces.shelf_menu, tip='Aktionen für die Sammelfläche')
        shelf_actions.setObjectName('toolButton'); shelf_row.addWidget(shelf_actions)
        self.spaces.update_shelf()
        footer = QFrame()
        footer.setObjectName('footer')
        status = QHBoxLayout(footer)
        status.setContentsMargins(16, 8, 16, 8)
        self.status = label('Bereit', 'muted')
        self.status.setWordWrap(False)
        status.addWidget(self.status)
        status.addWidget(self.subtitle, 1)
        status.addWidget(self.shelf_bar)
        self.thumbnail_size = QSlider(Qt.Horizontal)
        self.thumbnail_size.setRange(96, 224)
        self.thumbnail_size.setFixedWidth(100)
        self.thumbnail_size.setAccessibleName('Größe der Miniaturen')
        self.thumbnail_size.setToolTip('Miniaturen verkleinern oder vergrößern')
        self.thumbnail_size.setValue(max(96, min(224, self.settings.value('thumbnailSize', 144, type=int))))
        self.thumbnail_size.valueChanged.connect(self.set_thumbnail_size)
        self.set_thumbnail_size(self.thumbnail_size.value())
        self.photo_bar = QWidget()
        photo_row = QHBoxLayout(self.photo_bar)
        photo_row.setContentsMargins(10, 2, 10, 2)
        photo_row.addWidget(label('Miniaturen', 'muted'))
        photo_row.addWidget(self.thumbnail_size)
        status.addWidget(self.photo_bar)
        self.activity = label('Leertaste · Vorschau', 'muted')
        self.activity.setWordWrap(False)
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
                                     ]:
            path = QStandardPaths.writableLocation(location)
            if path and Path(path).is_dir():
                places.append((text, path, icon))
        for library in self.spaces.catalog.libraries():
            places.append((library['name'], LIBRARY + library['id'], library['icon']))
        for path in self.settings.value('favorites', [], type=list):
            if path not in [p[1] for p in places]:
                places.append((Path(path).name or path, path, 'folder-favorites'))
        if hasattr(self, 'offline'):
            from lumen_offline import folders
            for folder in folders(self.offline.store):
                places.append((folder['name'] + ' · Offline', folder['local'], 'folder-download'))
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
            heading = QListWidgetItem('Netzwerk')
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
        if virtual(self.current_location):
            self.spaces.sources_action()
            return
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
        if path.startswith(LIBRARY):
            self.spaces.library_menu(menu, path)
        if is_network_address(path):
            menu.addAction('Offline verfügbar machen …', lambda: self.offline.add(path))
        menu.addAction('Neue Bibliothek …', self.spaces.edit_library)
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
        size_width = max(130, self.view.fontMetrics().horizontalAdvance('Berechnen') + 32)
        for column, width in [(1, size_width), (2, 112), (3, 140), (4, 230)]:
            if column < self.proxy.columnCount():
                header.setSectionResizeMode(column, QHeaderView.Interactive)
                self.view.setColumnWidth(column, width)
        # Type is already visible in the icon/preview; save space in the default list.
        self.view.setColumnHidden(2, True)
        self.view.setColumnHidden(3, self.width() < 1180)
        self.fs.setHeaderData(0, Qt.Horizontal, 'Name')

    def shortcut(self, key, callback, local=False):
        shortcut = QShortcut(QKeySequence(key), self.file_stack if local else self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)

    def install_shortcuts(self):
        for key, callback in [('Ctrl+F', lambda: self.search.setFocus()), ('Ctrl+L', self.edit_path),
                              ('Ctrl+T', lambda: self.new_tab(self.current_location)),
                              ('Ctrl+K', self.connect_dialog),
                              ('Ctrl+1', lambda: self.set_view_mode('list')),
                              ('Ctrl+2', lambda: self.set_view_mode('grid')),
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

    def set_view_mode(self, mode):
        mode = 'grid' if mode == 'grid' else 'list'
        self.file_stack.setCurrentWidget(self.grid if mode == 'grid' else self.view)
        self.photo_bar.setVisible(mode == 'grid')
        for name, item in self.view_buttons.items():
            item.setChecked(name == mode)
        self.settings.setValue('viewMode', mode)
        self.file_stack.currentWidget().setFocus()
        self.file_stack.currentWidget().scrollTo(self.view.currentIndex())

    def set_thumbnail_size(self, size):
        self.grid.setIconSize(QSize(size, size))
        self.grid.update_metrics()
        self.settings.setValue('thumbnailSize', size)

    def set_file_root(self, index):
        self.grid.reset_thumbnails()
        self.view.setRootIndex(index)
        self.grid.setRootIndex(index)

    def new_tab(self, path, activate=True):
        collection = str(path) if virtual(path) else None
        remote = None if collection else str(path) if is_network_address(path) else self.network.remote(str(path))
        if remote:
            try:
                remote = normalize_url(remote)
            except ValueError as error:
                self.error(str(error))
                remote = None
            path = str(Path.home())
        path = str(Path(path).expanduser())
        if not Path(path).is_dir():
            path = str(Path.home())
        self.tabs_data.append({'history': [collection or remote or path], 'position': 0})
        self.tabs.blockSignals(True)
        index = self.tabs.addTab(self.spaces.name(collection) if collection else server_label(remote) if remote else Path(path).name or 'Dateisystem')
        if activate:
            self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        if activate:
            self.switch_tab(index)
        self.session_save.start()

    def save_session(self):
        self.settings.setValue('session/tabs', [tab['history'][tab['position']] for tab in self.tabs_data])
        self.settings.setValue('session/activeTab', self.tabs.currentIndex())
        self.settings.setValue('session/splitter', self.splitter.saveState())
        self.settings.setValue('session/sortColumn', self.view.header().sortIndicatorSection())
        self.settings.setValue('session/sortDescending', self.view.header().sortIndicatorOrder() == Qt.DescendingOrder)
        self.settings.sync()

    def recovery_state(self):
        return {'tabs': [tab['history'][tab['position']] for tab in self.tabs_data],
                'active': self.tabs.currentIndex(), 'geometry': bytes(self.saveGeometry()).hex(),
                'chat': self.assistant.recovery_state() if hasattr(self, 'assistant') else None}

    def restore_recovery(self, state):
        paths = state.get('tabs', [])
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise ValueError('Ungültige gespeicherte Tabs.')
        if paths:
            self.tabs.blockSignals(True)
            self.tabs_data.clear()
            while self.tabs.count(): self.tabs.removeTab(0)
            self.tabs.blockSignals(False)
            for path in paths[:100]: self.new_tab(path, activate=False)
            index = max(0, min(len(self.tabs_data) - 1, int(state.get('active', 0))))
            self.tabs.setCurrentIndex(index); self.switch_tab(index)
        if state.get('geometry'): self.restoreGeometry(bytes.fromhex(state['geometry']))
        if state.get('chat'):
            self.ask_lumen('open', [], recovery=state['chat'])
        self.save_session()

    def switch_tab(self, index):
        if index >= 0:
            tab = self.tabs_data[index]
            self.navigate(tab['history'][tab['position']], record=False)
            self.session_save.start()

    def close_tab(self, index):
        if self.tabs.count() == 1:
            return
        self.tabs.blockSignals(True)
        self.tabs_data.pop(index)
        self.tabs.removeTab(index)
        self.tabs.blockSignals(False)
        self.switch_tab(self.tabs.currentIndex())
        self.release_unused_network()

    def release_unused_network(self):
        if self.file_job and self.file_job.isRunning(): return
        if any(virtual(t['history'][t['position']]) for t in self.tabs_data): return
        if self.connection_request or any(is_network_address(t['history'][t['position']]) for t in self.tabs_data): return
        if not self.network.mounts: return
        self.cancel_search(); self.preview.clear(); self.grid.reset_thumbnails()
        old = self.fs
        old.setOption(QFileSystemModel.DontWatchForChanges, True)
        self.fs = QFileSystemModel(self)
        self.fs.setReadOnly(True); self.fs.setOption(QFileSystemModel.DontUseCustomDirectoryIcons, True)
        self.apply_hidden()
        self.fs.directoryLoaded.connect(lambda _path: self.update_count())
        self.fs.directoryLoaded.connect(self.spaces.directory_loaded)
        self.fs.directoryLoaded.connect(lambda path: self.grid.reset_thumbnails() if path == self.current_path else None)
        self.proxy.setSourceModel(self.fs)
        self.set_file_root(self.proxy.mapFromSource(self.fs.setRootPath(self.current_path)))
        old.deleteLater()
        self.network.release()

    def history(self, delta):
        tab = self.tabs_data[self.tabs.currentIndex()]
        position = tab['position'] + delta
        if 0 <= position < len(tab['history']):
            self.navigate(tab['history'][position], record=False, history_position=position)

    def navigate(self, path, record=True, history_position=None):
        if virtual(path):
            self.show_collection(path, record, history_position)
            return
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
        self.spaces.cancel()
        self.proxy.folder_sizes.clear()
        self.source_bar.hide()
        self.results.setHorizontalHeaderLabels(['Name', 'Größe', 'Typ', 'Geändert', 'Ordner'])
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
        self.set_file_root(self.proxy.mapFromSource(self.fs.setRootPath(path)))
        self.view.clearSelection()
        self.configure_columns()
        self.preview.clear()
        self.path_edit.setText(display_url(location) if remote else path)
        self.path_stack.setCurrentWidget(self.crumbs)
        self.build_crumbs(self.current_location)
        self.heading.setText(title)
        self.subtitle.clear()
        self.search.setPlaceholderText('Suchen')
        self.back_button.setEnabled(tab['position'] > 0)
        self.forward_button.setEnabled(tab['position'] < len(tab['history']) - 1)
        if remote:
            self.disk_label.setText(f'{QUrl(location).host()}\n{QUrl(location).scheme().upper()} verbunden')
        else:
            storage = QStorageInfo(path)
            self.disk_label.setText(f'{size_text(storage.bytesAvailable())} frei\nauf {storage.displayName() or "diesem Laufwerk"}')
        self.location_badge.setText('Netzwerk' if remote else 'Lokales Laufwerk')
        for i in range(self.places.count()):
            self.places.item(i).setSelected(self.places.item(i).data(Qt.UserRole) == self.current_location)
        self.update_count()
        self.file_stack.currentWidget().setFocus()
        self.session_save.start()
        return True

    def show_collection(self, location, record=True, history_position=None):
        self.proxy.folder_sizes.clear()
        self.cancel_connection(); self.cancel_search(); self.debounce.stop()
        self.current_location, self.current_path = location, str(Path.home())
        tab = self.tabs_data[self.tabs.currentIndex()]
        if history_position is not None: tab['position'] = history_position
        if record and tab['history'][tab['position']] != location:
            tab['history'] = tab['history'][:tab['position'] + 1] + [location]
            tab['position'] += 1
        title = self.spaces.name(location)
        self.tabs.setTabText(self.tabs.currentIndex(), title)
        self.tabs.setTabToolTip(self.tabs.currentIndex(), title)
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.search.setPlaceholderText('In allen Quellen suchen')
        self.preview.clear(); self.heading.setText(title); self.subtitle.clear()
        self.path_edit.setText(location); self.path_stack.setCurrentWidget(self.crumbs)
        while self.crumb_layout.count():
            item = self.crumb_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.crumb_layout.addWidget(label(title, 'muted')); self.crumb_layout.addStretch()
        self.back_button.setEnabled(tab['position'] > 0)
        self.forward_button.setEnabled(tab['position'] < len(tab['history']) - 1)
        self.disk_label.setText('Dateien bleiben an ihrem Ort')
        self.location_badge.setText('Sammelfläche' if location == SHELF else 'Gemeinsame Ansicht')
        for i in range(self.places.count()):
            self.places.item(i).setSelected(self.places.item(i).data(Qt.UserRole) == location)
        self.source_bar.show(); self.spaces.reload(); self.session_save.start()

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
            if Path.home() in parts:
                parts = parts[parts.index(Path.home()):]
        if len(parts) > 4:
            parts = [parts[0]] + parts[-3:]
        for i, part in enumerate(parts):
            if i:
                self.crumb_layout.addWidget(label('  ›  ', 'muted'))
            text = (Path(QUrl(part).path()).name or QUrl(part).host()) if remote else ('Persönlich' if part == Path.home() else part.name or 'Rechner')
            crumb = button(self.fontMetrics().elidedText(text, Qt.ElideMiddle, 150),
                           lambda _checked=False, p=part: self.navigate(p), tip=str(part))
            crumb.setObjectName('crumb')
            self.crumb_layout.addWidget(crumb)
        self.crumb_layout.addStretch()

    def up(self):
        if virtual(self.current_location):
            self.history(-1)
        elif is_network_address(self.current_location):
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
        if virtual(self.current_location) or self.search.text().strip():
            self.queue_search()
        else:
            QTimer.singleShot(50, self.update_count)

    def toggle_preview(self):
        self.preview.setVisible(self.preview_button.isChecked())
        self.settings.setValue('previewVisible', self.preview_button.isChecked())

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

    def search_contents(self):
        from content_search_dialog import ContentSearchDialog
        root = self.spaces.choose_target() if virtual(self.current_location) else self.current_path
        if not root: return
        dialog = ContentSearchDialog(root, self.search.text(), self.hidden, self)
        dialog.folderRequested.connect(self.navigate)
        dialog.exec_()
        dialog.deleteLater()

    def queue_search(self, _text=None):
        self.cancel_search()
        self.spaces.cancel()
        self.subtitle.setText('Suche wird aktualisiert …')
        self.debounce.start()

    def start_search(self):
        self.cancel_search()
        if virtual(self.current_location):
            self.spaces.reload()
            return
        query = self.search.text().strip()
        if not query:
            self.proxy.setSourceModel(self.fs)
            self.set_file_root(self.proxy.mapFromSource(self.fs.index(self.current_path)))
            self.configure_columns()
            self.subtitle.clear()
            self.update_count()
            return
        self.results.removeRows(0, self.results.rowCount())
        self.proxy.setSourceModel(self.results)
        self.set_file_root(QModelIndex())
        self.configure_columns()
        self.preview.clear()
        self.search_errors = self.search_total = 0
        job = SearchWorker(self.current_path, query, self.hidden, self.settings.value('searchLimit', 5000, type=int))
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
                detail += f' · Limit {job.limit:,} erreicht — Suche eingrenzen'
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

    def context_paths(self):
        return self.selected_paths() or ([] if virtual(self.current_location) else [self.current_path])

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

    def ask_lumen(self, action, paths, recovery=None):
        if hasattr(self, 'lumen_host'):
            self.lumen_host.chat.begin_context(action, paths, directory=self.current_path)
            self.lumen_host.show_page(0)
            return
        if not hasattr(self, 'assistant'):
            from assistant import ChatPanel
            self.assistant = ChatPanel(self.current_path, self)
            self.assistant_dock = QDockWidget('Lumen', self)
            self.assistant_dock.setObjectName('lumenDock')
            self.assistant_dock.setWidget(self.assistant)
            self.assistant_dock.setTitleBarWidget(QWidget(self.assistant_dock))
            self.assistant.closeRequested.connect(self.assistant_dock.hide)
            self.assistant.actionChanged.connect(lambda _: self.assistant_dock.setWindowTitle(self.assistant.heading.text() if self.assistant.action else 'Lumen'))
            self.assistant_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
            def assistant_visibility(visible):
                self.preview.setVisible(not visible and self.preview_button.isChecked())
                self.centralWidget().setMinimumWidth(1000 if visible else 0)
                self.setMinimumWidth(max(1000, self.minimumSizeHint().width()))
            self.assistant_dock.visibilityChanged.connect(assistant_visibility)
            self.addDockWidget(Qt.RightDockWidgetArea, self.assistant_dock)
            self.resizeDocks([self.assistant_dock], [440], Qt.Horizontal)
        self.assistant_dock.show()
        self.assistant_dock.raise_()
        if recovery is not None: self.assistant.restore_recovery(recovery)
        else: self.assistant.begin_context(action, paths, directory=self.current_path)

    def lumen_menu(self, menu, paths):
        if not paths:
            return
        submenu = menu.addMenu(QIcon.fromTheme('lumen'), 'Lumen')
        for title, action in [('Mit Lumen öffnen', 'open'), ('Erklären', 'explain'),
                              ('Fehler beheben', 'fix'), ('Git-Diff prüfen', 'review')]:
            submenu.addAction(title, lambda _=False, a=action: self.ask_lumen(a, paths))
        submenu.addSeparator()
        submenu.addAction('Intelligent umbenennen …', lambda: self.organize_files('rename', paths))
        submenu.addAction('Dateien sortieren …', lambda: self.organize_files('sort', paths))

    def organize_files(self, mode, paths=None):
        if self.file_job:
            self.error('Bitte den laufenden Dateivorgang abwarten.')
            return
        from organize_dialog import OrganizeDialog
        journal = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'organize-undo.json'
        root = self.current_path
        dialog = OrganizeDialog(paths or self.selected_paths(), root, mode, journal, self,
                                per_source=virtual(self.current_location))
        dialog.exec_()
        dialog.deleteLater()
        self.refresh()

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

    def open_gallery(self, path, editing=False):
        images = []
        for row in range(self.proxy.rowCount(self.view.rootIndex())):
            index = self.proxy.index(row, 0, self.view.rootIndex())
            candidate = self.proxy.path(index)
            if file_kind(candidate) != 'image':
                continue
            source = self.proxy.mapToSource(index)
            directory = self.fs.isDir(source) if self.proxy.sourceModel() is self.fs else source.sibling(source.row(), 2).data() == 'Ordner'
            if not directory:
                images.append(candidate)
        if path not in images:
            images.append(path)
        self.preview.cancel()
        self.preview_delay.stop()
        dialog = Gallery(images, path, self)
        dialog.editor_button.setChecked(editing)
        dialog.exec_()
        for row in range(self.proxy.rowCount(self.view.rootIndex())):
            index = self.proxy.index(row, 0, self.view.rootIndex())
            if self.proxy.path(index) == dialog.path:
                self.view.setCurrentIndex(index)
                self.file_stack.currentWidget().scrollTo(index)
                break
        dialog.deleteLater()
        self.refresh()
        self.preview_delay.stop()
        self.preview_selection()

    def size_clicked(self, index):
        if index.column() == 1 and self.proxy.directory(index):
            self.open_analysis(self.proxy.path(index), apparent=True)

    def open_analysis(self, path=None, apparent=False):
        if not path and virtual(self.current_location):
            path = self.spaces.choose_target()
            if not path: return
        dialog = DiskAnalysis(path or self.current_path, self, apparent=apparent)
        def sizes_ready(values):
            self.proxy.folder_sizes.update(values)
            self.proxy.invalidate()
        dialog.sizesReady.connect(sizes_ready)
        destination = []
        dialog.openPath.connect(destination.append)
        dialog.exec_()
        dialog.deleteLater()
        if destination:
            self.navigate(destination[0])

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
            target = self.spaces.choose_target() if virtual(self.current_location) else self.current_path
            if target: self.run_operation('move' if cut else 'copy', paths, target)

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
        target = self.spaces.choose_target() if virtual(self.current_location) else self.current_path
        if not target: return
        name, ok = QInputDialog.getText(self, 'Neuer Ordner', 'Name des Ordners:')
        if ok:
            try:
                path = Path(target) / valid_name(name)
                self.run_operation('mkdir', [str(path)])
            except ValueError as exc:
                self.error(str(exc))

    def rename(self):
        paths = self.selected_paths()
        if len(paths) > 1:
            self.organize_files('rename', paths)
            return
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
        view = self.file_stack.currentWidget()
        index = view.indexAt(position)
        if index.isValid() and not self.view.selectionModel().isSelected(index):
            self.view.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        paths = self.selected_paths()
        menu = QMenu(self)
        if paths:
            menu.addAction('Öffnen', self.open_selected)
            if all(Path(p).suffix.lower() == '.pdf' for p in paths):
                self.add_workshop_action(menu, paths)
            menu.addAction('Zur Sammelfläche hinzufügen', lambda: self.spaces.collect(paths))
            menu.addAction('In Ordner kopieren …', self.spaces.copy_to)
            if self.current_location == SHELF:
                menu.addAction('Aus Sammelfläche entfernen (Dateien behalten)', lambda: self.spaces.remove_shelf(paths))
            if len(paths) == 1:
                menu.addAction('Große Vorschau\tLeertaste', self.quicklook)
                menu.addAction('Dateiversionen …', lambda: self.show_versions(paths[0]))
                menu.addAction('Enthaltenden Ordner öffnen', lambda: self.navigate(Path(paths[0]).parent))
                if Path(paths[0]).is_dir():
                    menu.addAction('In neuem Tab öffnen', lambda: self.new_tab(paths[0]))
                    remote = self.network.remote(paths[0])
                    if remote: menu.addAction('Offline verfügbar machen …', lambda: self.offline.add(remote))
                    menu.addAction('Ordnergröße berechnen', lambda: self.open_analysis(paths[0], apparent=True))
                    menu.addAction('Speicher analysieren', lambda: self.open_analysis(paths[0]))
                menu.addAction('Umbenennen\tF2', self.rename)
            menu.addSeparator()
            menu.addAction('Kopieren\tStrg+C', lambda: self.copy(False))
            menu.addAction('Ausschneiden\tStrg+X', lambda: self.copy(True))
            menu.addAction('Pfad kopieren', lambda: QApplication.clipboard().setText('\n'.join(self.network.remote(p) or p for p in paths)))
            menu.addSeparator()
            self.lumen_menu(menu, paths)
            from file_actions import menu as personal_actions_menu
            personal_actions_menu(self, menu, paths)
            menu.addSeparator()
            menu.addAction('In den Papierkorb\tEntf', self.trash)
        menu.addAction('Hier einfügen\tStrg+V', self.paste)
        menu.addAction('Neuer Ordner', self.mkdir)
        menu.addSeparator()
        menu.addAction('Letzte Lumen-Dateiaktion rückgängig …', lambda: self.organize_files('undo'))
        menu.exec_(view.viewport().mapToGlobal(position))

    def refresh(self):
        self.proxy.folder_sizes.clear()
        self.proxy.invalidate()
        self.grid.reset_thumbnails()
        if virtual(self.current_location) or self.search.text().strip():
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
            self.file_stack.currentWidget().setFocus()
        elif self.search.text():
            self.search.clear()
            self.file_stack.currentWidget().setFocus()

    def show_settings(self):
        from settings_dialog import SettingsDialog
        dialog = SettingsDialog(self, files_settings=self.settings, page=1)
        dialog.preferencesChanged.connect(self.reload_settings)
        dialog.exec_()
        dialog.deleteLater()

    def reload_settings(self, filename=None, keys=None):
        if hasattr(self, 'assistant') and filename:
            self.assistant.reload_settings(filename, keys)
        if filename and filename != self.settings.fileName():
            return
        self.settings.sync()
        self.hidden = self.settings.value('hidden', False, type=bool)
        self.hidden_button.setChecked(self.hidden)
        self.apply_hidden()
        self.preview_button.setChecked(self.settings.value('previewVisible', True, type=bool))
        self.preview.setVisible(self.preview_button.isChecked() and not (hasattr(self, 'assistant_dock') and self.assistant_dock.isVisible()))
        self.debounce.setInterval(max(100, min(1500, self.settings.value('searchDelay', 250, type=int))))
        self.populate_places()
        if self.search.text().strip():
            self.queue_search()

    def add_workshop_action(self, menu, paths=()):
        self.settings.sync()
        if self.settings.value('documentWorkshopEnabled', False, type=bool):
            from document_workshop_ui import open_workshop
            menu.addAction('Dokumentenwerkstatt …', lambda: open_workshop(self, paths))

    def show_menu(self):
        menu = QMenu(self)
        menu.addAction('Arbeitsplatz · Projekte & Verlauf', self.show_workplace)
        menu.addAction('Transfers', lambda: self.show_workplace(2))
        menu.addAction('Offline verfügbare Ordner …', self.offline.show)
        menu.addAction('Dateiversionen …', self.show_versions)
        self.add_workshop_action(menu)
        menu.addAction('Einstellungen\tStrg+Komma', self.show_settings)
        menu.addAction('Bibliotheken verwalten …', self.spaces.library_manager)
        menu.addAction('Arbeitsräume …', self.spaces.room_menu)
        menu.addAction('Mit Server verbinden\tStrg+K', self.connect_dialog)
        menu.addAction('Speicher analysieren', self.open_analysis)
        menu.addAction('Aktualisieren\tF5', self.refresh)
        menu.addAction('Versteckte Dateien\tStrg+H', self.toggle_hidden)
        menu.addSeparator()
        menu.addAction('Tastenkürzel & Info', lambda: QMessageBox.information(self, 'Lumen Files',
            'Lumen Files · 0.3\n\nStrg+F  Suchen\nStrg+L  Pfad eingeben\nStrg+K  Server verbinden\n'
            'Strg+T / Strg+W  Tab öffnen / schließen\nAlt+Pfeile  Navigation\n'
            'Leertaste  Große Vorschau\nF2  Umbenennen\nStrg+C / X / V  Kopieren / Ausschneiden / Einfügen\n'
            'Entf  Papierkorb\n\nSuche: Dateinamen im aktuellen Ordner und Unterordnern. '
            'Mehrere Wörter müssen alle im Namen vorkommen. Trefferlimit in den Einstellungen; kein Volltextindex.\n\n'
            'Bilder: Pfeiltasten blättern, R / Umschalt+R drehen, H spiegeln, Strg+Z rückgängig, '
            'Strg+S speichern, Entf Papierkorb, F11 Vollbild. Originale bleiben in .lumen-originals.\n\n'
            'PDFs sind blätterbar. Videos zeigen ein Standbild, Audio eine Wellenform. Wiedergabe in der Standard-App.'))
        menu.exec_(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def show_versions(self, path=None):
        from versions_ui import VersionsDialog
        dialog = VersionsDialog(self, path if isinstance(path, str) else None); dialog.exec_(); dialog.deleteLater()

    def show_workplace(self, tab=0):
        if hasattr(self, 'lumen_host'):
            self.lumen_host.show_page(8)
            self.lumen_host.workplace.tabs.setCurrentIndex(int(tab)); return
        if not hasattr(self, 'workplace_dialog'):
            from lumen_workplace import Workplace
            class WorkplaceDialog(QDialog):
                def reject(dialog):
                    if dialog.page.busy:
                        dialog.page.status.setText('Bitte die laufende Systemaktion abschließen lassen.'); return
                    super().reject()
            self.workplace_dialog = WorkplaceDialog(self)
            self.workplace_dialog.setWindowTitle('Arbeitsplatz — Lumen Files'); self.workplace_dialog.resize(1120, 800)
            layout = QVBoxLayout(self.workplace_dialog)
            self.workplace_dialog.page = Workplace(self.workplace_dialog, files_provider=lambda: self)
            layout.addWidget(self.workplace_dialog.page)
        self.workplace_dialog.page.refresh_projects()
        self.workplace_dialog.page.tabs.setCurrentIndex(int(tab))
        self.workplace_dialog.show(); self.workplace_dialog.raise_(); self.workplace_dialog.activateWindow()

    def error(self, message, detail=''):
        box = QMessageBox(QMessageBox.Warning, 'Lumen Files', message, QMessageBox.Ok, self)
        box.setTextFormat(Qt.PlainText)
        if detail:
            box.setDetailedText(detail)
        box.exec_()

    def closeEvent(self, event):
        if hasattr(self, 'workplace_dialog') and self.workplace_dialog.page.busy:
            self.error('Bitte die laufende Systemaktion zuerst abschließen lassen.'); event.ignore(); return
        if getattr(self, '_closed', False):
            event.accept(); return
        if self.file_job and self.file_job.isRunning():
            self.error('Es läuft noch ein Dateivorgang. Bitte vor dem Schließen abwarten.')
            event.ignore()
            return
        if hasattr(self, 'assistant') and not self.assistant.can_close():
            event.ignore()
            return
        if not self.spaces.save_active_room():
            event.ignore(); return
        self.spaces.close()
        if hasattr(self, 'workplace_dialog'): self.workplace_dialog.page.shutdown()
        self.cancel_search()
        self.cancel_connection()
        self.preview.cancel()
        self.grid.reset_thumbnails()
        for job in self.search_jobs[:]:
            job.stop.set()
            if not job.wait(1500):
                self.activity.setText('Suche wird beendet. Bitte gleich erneut schließen.')
                event.ignore()
                return
        if hasattr(self, 'assistant'):
            self.assistant.tracker.interrupt()
            self.assistant.context_tools.close()
            self.assistant.backend.shutdown()
        self.settings.setValue('last_path', self.current_location)
        self.settings.setValue('geometry', self.saveGeometry())
        self.session_save.stop()
        self.save_session()
        if self.network.mounts:
            self.view.setModel(None); self.grid.setModel(None); self.proxy.setSourceModel(None)
            self.fs.directoryLoaded.disconnect()
            self.fs.setOption(QFileSystemModel.DontWatchForChanges, True)
            self.fs.deleteLater()
        self.offline.close()
        self.network.close()
        self._closed = True
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'view'):
            self.view.setColumnHidden(3, self.width() < 1180)
        if hasattr(self, 'disk_label'):
            self.disk_label.setVisible(self.height() >= 700)


class Application(QApplication):
    def eventFilter(self, receiver, event):
        kind = event.type()
        mouse = (kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick)
                 and event.button() in (Qt.BackButton, Qt.ForwardButton))
        key = kind in (QEvent.KeyPress, QEvent.KeyRelease) and event.key() in (Qt.Key_Back, Qt.Key_Forward)
        if (mouse or key) and isinstance(receiver, QWidget):
            top = receiver.window()
            window = receiver
            while window is not None and not isinstance(window, (Window, Gallery)):
                if window is top: break
                window = window.parentWidget()
            modal = self.activeModalWidget()
            if (not self.activePopupWidget() and (modal is None or modal is top)
                    and isinstance(window, (Window, Gallery))):
                if (mouse and kind == QEvent.MouseButtonRelease) or (key and kind == QEvent.KeyPress and not event.isAutoRepeat()):
                    back = event.button() == Qt.BackButton if mouse else event.key() == Qt.Key_Back
                    direction = -1 if back else 1
                    window.history(direction) if isinstance(window, Window) else window.step(direction)
                event.accept()
                return True
        return False


def apply_system_appearance(app, path):
    kde = QSettings(str(path), QSettings.IniFormat)
    palette = QPalette(app.palette())
    for role, group, key in [
            (QPalette.Window, 'Window', 'BackgroundNormal'),
            (QPalette.WindowText, 'Window', 'ForegroundNormal'),
            (QPalette.Base, 'View', 'BackgroundNormal'),
            (QPalette.AlternateBase, 'View', 'BackgroundAlternate'),
            (QPalette.Text, 'View', 'ForegroundNormal'),
            (QPalette.Button, 'Button', 'BackgroundNormal'),
            (QPalette.ButtonText, 'Button', 'ForegroundNormal'),
            (QPalette.Highlight, 'Selection', 'BackgroundNormal'),
            (QPalette.HighlightedText, 'Selection', 'ForegroundNormal'),
            (QPalette.ToolTipBase, 'Tooltip', 'BackgroundNormal'),
            (QPalette.ToolTipText, 'Tooltip', 'ForegroundNormal'),
            (QPalette.Link, 'View', 'ForegroundLink')]:
        value = kde.value(f'Colors:{group}/{key}')
        if value:
            try:
                palette.setColor(role, QColor(*map(int, value if isinstance(value, list) else value.split(','))))
            except (TypeError, ValueError):
                pass
    base, text = palette.color(QPalette.Base), palette.color(QPalette.Text)
    for role, weight in [(QPalette.Mid, .18), (QPalette.Midlight, .035),
                         (QPalette.Dark, .65), (QPalette.PlaceholderText, .65)]:
        palette.setColor(role, QColor(*(round(a + (b - a) * weight) for a, b in zip(base.getRgb()[:3], text.getRgb()[:3]))))
    palette.setColor(QPalette.Disabled, QPalette.Text, palette.color(QPalette.PlaceholderText))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, palette.color(QPalette.PlaceholderText))
    changed = palette != app.palette()
    if changed:
        # Qt resolves palette(...) when polishing a stylesheet. Drop cached widget
        # colors before applying a different system palette to already open windows.
        app.setStyleSheet('')
    app.setPalette(palette)
    # QSettings exposes keys in the INI [General] section at the root.
    description = kde.value('font')
    if description:
        parts = description if isinstance(description, list) else description.split(',')
        try:
            font = QFont(parts[0])
            font.setPointSizeF(float(parts[1]))
            app.setFont(font)
        except (IndexError, ValueError):
            pass
    theme = kde.value('Icons/Theme', 'breeze-dark' if base.lightness() < 128 else 'breeze')
    # Use the installed variant so a light icon pack stays legible on dark KDE colors.
    if theme.endswith(('-light', '-dark')):
        variant = theme.rsplit('-', 1)[0] + ('-dark' if base.lightness() < 128 else '-light')
        if any((Path(root) / variant / 'index.theme').exists() for root in QIcon.themeSearchPaths()):
            theme = variant
    QIcon.setThemeName(theme)
    if changed or not app.styleSheet():
        from appearance import stylesheet
        app.setStyleSheet(stylesheet('system'))


def create_app(appearance=None):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = Application(sys.argv)
    # An application event filter sees GUI-thread events only. Overriding notify
    # also wraps objects from Qt's network threads in Python and races their deletion.
    app.installEventFilter(app)
    def dispose_windows():
        # Qt processes deferred deletion after all aboutToQuit shutdown slots.
        # Keep QObject owners out of interpreter-exit garbage collection.
        app.removeEventFilter(app)
        for window in app.topLevelWidgets():
            window.deleteLater()
    app.aboutToQuit.connect(dispose_windows)
    app.setApplicationName('lumen-files')
    app.setApplicationDisplayName('Lumen Files')
    app.setDesktopFileName('lumen-files')
    app.translator = QTranslator(app)
    app.translator.load('qtbase_de', QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    app.installTranslator(app.translator)
    kde = QSettings(str(Path.home() / '.config/kdeglobals'), QSettings.IniFormat)
    QIcon.setThemeSearchPaths([str(Path(path) / 'icons') for path in
                             QStandardPaths.standardLocations(QStandardPaths.GenericDataLocation)]
                             + QIcon.themeSearchPaths())
    QIcon.setThemeName(kde.value('Icons/Theme', 'breeze-dark'))
    from appearance import DEFAULT_DESIGN, apply_design, normalize_design
    app.setStyle('Fusion')
    preferences = QSettings('Lumen', 'Assistant')
    apply_design(app, appearance or preferences.value('appearance', DEFAULT_DESIGN))
    paths = [Path.home() / '.config/kdeglobals', Path(preferences.fileName())]
    app.theme_watcher = QFileSystemWatcher(app)
    def watch_theme_paths():
        for path in paths:
            parent = next(p for p in path.parents if p.is_dir())
            for candidate in (parent, path):
                if candidate.exists() and str(candidate) not in app.theme_watcher.files() + app.theme_watcher.directories():
                    app.theme_watcher.addPath(str(candidate))
    def update_theme(changed):
        preferences.sync()
        design = preferences.value('appearance', DEFAULT_DESIGN)
        design = normalize_design(design)
        if design != app.property('lumenDesign') or (design == 'system' and changed == str(paths[0])):
            apply_design(app, design)
        watch_theme_paths()
    app.theme_watcher.fileChanged.connect(update_theme)
    app.theme_watcher.directoryChanged.connect(update_theme)
    app.reload_theme = lambda: update_theme('')
    watch_theme_paths()
    return app


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Lumen Files – Dateimanager mit Lumen-Integration')
    parser.add_argument('location', nargs='?', help='Datei, Ordner oder Netzwerkadresse')
    parser.add_argument('--settings', action='store_true', help='Gemeinsame Lumen-Einstellungen öffnen')
    args = parser.parse_args()
    from lumen_migrate import migrate_user
    migrate_user()
    app = create_app()
    start = args.location
    if start and start.startswith('file:'):
        start = QUrl(start).toLocalFile()
    if start and Path(start).is_file():
        start = str(Path(start).parent)
    window = Window(start)
    window.show()
    from lumen_crash import attach
    attach(app, window, 'files', offer_recovery=not start and not args.settings)
    if args.settings:
        QTimer.singleShot(0, window.show_settings)
    else:
        from setup_dialog import offer_setup
        QTimer.singleShot(250, lambda: offer_setup(window))
    sys.exit(app.exec_())
