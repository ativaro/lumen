"""Native installed-app associations and explicit file launches for Files."""
from pathlib import Path
from gi.repository import Gio
from PySide6.QtCore import QMimeDatabase, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)
from lumen_i18n import tr


def file_types(names):
    database = QMimeDatabase()
    return tuple(sorted({database.mimeTypeForFile(str(name), QMimeDatabase.MatchExtension).name()
                         for name in names}))


def available(app):
    return (app is not None and app.get_id() and app.should_show()
            and (app.supports_files() or app.supports_uris()))


def applications(types, *, all_apps=False):
    default = Gio.AppInfo.get_default_for_type(types[0], False) if len(types) == 1 else None
    if all_apps:
        values = Gio.AppInfo.get_all()
    else:
        values = Gio.AppInfo.get_all_for_type(types[0]) if types else []
        for mime in types[1:]:
            allowed = {app.get_id() for app in Gio.AppInfo.get_all_for_type(mime)}
            values = [app for app in values if app.get_id() in allowed]
    unique = {app.get_id(): app for app in values if available(app)}
    result = sorted(unique.values(), key=lambda app: app.get_display_name().casefold())
    if default and default.get_id() in unique:
        result.remove(unique[default.get_id()])
        result.insert(0, default)
    return result, default.get_id() if default else None


def launch(app, paths, types=(), *, make_default=False):
    files = [Path(path).absolute() for path in paths]
    if not files or not all(path.is_file() for path in files):
        raise ValueError(tr('Bitte vorhandene Dateien auswählen.'))
    if make_default and (len(types) != 1 or types[0] == 'application/octet-stream'):
        raise ValueError(tr('Eine Standard-App kann nur für einen bekannten Dateityp gesetzt werden.'))
    if not app.launch([Gio.File.new_for_path(str(path)) for path in files], None):
        raise ValueError(tr('Die App konnte nicht gestartet werden.'))
    if make_default and not app.set_as_default_for_type(types[0]):
        raise ValueError(tr('Die App wurde gestartet, die Standard-Zuordnung konnte aber nicht gespeichert werden.'))


def app_icon(app):
    icon = app.get_icon()
    if isinstance(icon, Gio.ThemedIcon):
        for name in icon.get_names():
            value = QIcon.fromTheme(name)
            if not value.isNull():return value
    if isinstance(icon, Gio.FileIcon):
        path = icon.get_file().get_path()
        if path:return QIcon(path)
    return QIcon.fromTheme('application-x-executable')


class AppChooser(QDialog):
    def __init__(self, parent, names, types):
        super().__init__(parent)
        from file_action_menu import ActionResultDelegate
        from studio_design import font
        self.setWindowTitle(tr('Lumen Files · Öffnen mit'))
        self.setFont(font(14)); self.resize(540, 580)
        outer = QVBoxLayout(self); outer.setContentsMargins(24,24,24,24); outer.setSpacing(16)
        heading = QLabel(tr('Öffnen mit')); heading.setFont(font(26)); outer.addWidget(heading)
        title = QLabel(names[0] if len(names)==1 else tr('{0} Dateien',len(names)))
        title.setTextFormat(Qt.PlainText); title.setWordWrap(True); title.setObjectName('muted'); outer.addWidget(title)
        self.search = QLineEdit(); self.search.setPlaceholderText(tr('App suchen …'))
        self.search.setAccessibleName(tr('Installierte Apps durchsuchen')); self.search.setClearButtonEnabled(True)
        self.search.addAction(QIcon.fromTheme('edit-find'),QLineEdit.LeadingPosition); outer.addWidget(self.search)
        self.apps = QListWidget(); self.apps.setAccessibleName(tr('App auswählen'))
        self.apps.setFrameShape(QFrame.NoFrame); self.apps.setStyleSheet('QListWidget { background:transparent; }')
        self.apps.setItemDelegate(ActionResultDelegate(self.apps,14,12)); self.apps.setIconSize(QSize(24,24))
        self.apps.setVerticalScrollMode(QListWidget.ScrollPerPixel); outer.addWidget(self.apps,1)
        values, default = applications(types, all_apps=True)
        for app in values:
            detail = tr('Systemstandard') if app.get_id()==default else app.get_description() or ''
            item = QListWidgetItem(app_icon(app),app.get_display_name()+'\n'+detail)
            item.setData(Qt.UserRole,app); item.setToolTip(app.get_display_name()+'\n'+detail)
            self.apps.addItem(item)
        self.empty = QLabel(tr('Keine passende App gefunden.')); self.empty.setObjectName('muted'); outer.addWidget(self.empty)
        self.always = QCheckBox(tr('Immer für diesen Dateityp verwenden'))
        self.always.setEnabled(len(types)==1 and types[0]!='application/octet-stream')
        self.always.setToolTip(tr('Ändert den Systemstandard für alle Dateien dieses Typs.'))
        outer.addWidget(self.always)
        if self.always.isEnabled():
            hint=QLabel(tr('Systemweit für: {0}',QMimeDatabase().mimeTypeForName(types[0]).comment()))
            hint.setWordWrap(True);hint.setObjectName('muted');outer.addWidget(hint)
        else:
            hint=QLabel(tr('Bei gemischten oder unbekannten Dateitypen bleibt der Systemstandard unverändert.'))
            hint.setWordWrap(True);hint.setObjectName('muted');outer.addWidget(hint)
        footer=QHBoxLayout();footer.addStretch()
        cancel=QPushButton(tr('Abbrechen'));cancel.clicked.connect(self.reject);footer.addWidget(cancel)
        self.open_button=QPushButton(tr('Öffnen'));self.open_button.setObjectName('primary')
        self.open_button.clicked.connect(self.accept);self.open_button.setDefault(True);footer.addWidget(self.open_button)
        outer.addLayout(footer)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.choose_current)
        self.apps.itemActivated.connect(lambda _:self.choose_current())
        self.apps.currentItemChanged.connect(lambda *_:self.open_button.setEnabled(self.selected_app() is not None))
        self.filter('');self.search.setFocus()

    def selected_app(self):
        item=self.apps.currentItem()
        return item.data(Qt.UserRole) if item is not None and not item.isHidden() else None

    def filter(self, query):
        words=query.casefold().split();first=None
        for n in range(self.apps.count()):
            item=self.apps.item(n);item.setHidden(not all(word in item.text().casefold() for word in words))
            if first is None and not item.isHidden():first=item
        self.apps.setCurrentItem(first);self.empty.setVisible(first is None)
        self.open_button.setEnabled(first is not None)

    def choose_current(self):
        if self.selected_app() is not None:self.accept()


def add_to_menu(window, menu, paths, *, drive=False):
    paths=tuple(paths)
    if not paths:return
    if drive and any(window.drive.entries[path][0]!='file' for path in paths):return
    from desktop_design import MENU_STYLE
    submenu=menu.addMenu(QIcon.fromTheme('application-x-executable'),tr('Öffnen mit'))
    submenu.setStyleSheet(MENU_STYLE)

    def names():
        return [window.drive.entries[path][1]['name'] for path in paths] if drive else [Path(path).name for path in paths]

    def start(app, types, make_default=False):
        def done(local_paths):
            try:
                launch(app,local_paths,types,make_default=make_default)
                if drive:window.activity.setText(tr('Lokale Kopie geöffnet · Änderungen bei Bedarf wieder in Drive ablegen.'))
            except Exception as error:window.error(str(error))
        try:
            if drive:window.drive.fetch(list(paths),done)
            else:done(paths)
        except Exception as error:window.error(str(error))

    def choose():
        try:
            selected_names=names();types=file_types(selected_names)
            dialog=AppChooser(window,selected_names,types)
            if dialog.exec()==QDialog.DialogCode.Accepted and dialog.selected_app() is not None:
                start(dialog.selected_app(),types,dialog.always.isChecked())
        except Exception as error:window.error(str(error))

    def populate():
        submenu.clear()
        try:
            types=file_types(names());values,default=applications(types)
            if not values:submenu.addAction(tr('Keine passende App gefunden.')).setEnabled(False)
            for app in values[:5]:
                title=app.get_display_name().replace('&','&&')
                if app.get_id()==default:title+='\t'+tr('Standard')
                submenu.addAction(app_icon(app),title,lambda _=False,a=app,t=types:start(a,t))
        except Exception as error:
            action=submenu.addAction(tr('App-Liste nicht verfügbar.'));action.setEnabled(False);action.setToolTip(str(error))
        submenu.addSeparator()
        submenu.addAction(QIcon.fromTheme('view-grid'),tr('Andere App …'),choose)

    submenu.addAction(QIcon.fromTheme('view-grid'),tr('Andere App …'),choose)
    submenu.aboutToShow.connect(populate)
