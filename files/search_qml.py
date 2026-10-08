"""Native Qt 6/QML search and conversation surface."""
import argparse
from pathlib import Path
import sys

# Select this process's binding before importing any shared Lumen module.
from PySide6.QtCore import QObject, QTimer, QUrl, QSize, Qt, Slot, ClassInfo, QStandardPaths
from PySide6.QtGui import QGuiApplication, QCursor, QIcon, QPixmap, QColor, QPainter, QPalette
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBus
from lumen_activation import present
from lumen_i18n import install, tr
from search_controller import SearchController


class Icons(QQuickImageProvider):
    def __init__(self): super().__init__(QQuickImageProvider.Pixmap)

    def requestPixmap(self, name, size, requested):
        from urllib.parse import parse_qs
        name, _, query = name.partition('?')
        tint = parse_qs(query).get('tint', [''])[0]
        target = requested if requested.width() > 0 else QSize(24, 24)
        icon = QIcon.fromTheme(name, QIcon.fromTheme('system-search' if name == 'lumen' else 'application-x-executable'))
        pixmap = icon.pixmap(target)
        if pixmap.isNull(): pixmap = QPixmap(target); pixmap.fill(Qt.transparent)
        if tint and QColor(tint).isValid():
            painter = QPainter(pixmap); painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(tint)); painter.end()
        size.setWidth(pixmap.width()); size.setHeight(pixmap.height())
        return pixmap


@ClassInfo(**{'D-Bus Interface': 'org.lumen.Search'})
class Activation(QObject):
    def __init__(self, window, controller):
        super().__init__(); self.window = window; self.controller = controller

    @Slot()
    def Activate(self):
        # Remap a background surface; raising an already-mapped Wayland window
        # alone does not reliably bring it forward after a D-Bus activation.
        if self.window.isVisible() and not self.window.isActive(): self.window.hide()
        self.controller.reload_settings()
        if not self.controller.conversation:
            self.controller.debounce.stop(); self.controller.search()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.window.setWidth(min(1240, max(620, area.width()-30)))
        self.window.setHeight(min(900, max(560, area.height()-70)))
        self.window.setPosition(area.x()+(area.width()-self.window.width())//2, min(area.bottom()-self.window.height(), max(area.y()+12, screen.geometry().y()+70)))
        present(self.window)
        self.controller.focusRequested.emit()

    @Slot()
    def Voice(self):
        self.Activate()
        if not self.controller.voice.active: self.controller.toggle_voice()


def create_window(app, controller):
    paths = [str(Path(__file__).resolve().parents[1]/'icons')]
    paths += [str(Path(root)/'icons') for root in QStandardPaths.standardLocations(QStandardPaths.GenericDataLocation)]
    QIcon.setThemeSearchPaths(paths + QIcon.themeSearchPaths())
    QIcon.setFallbackThemeName('hicolor')
    def icons():
        palette = QGuiApplication.palette()
        for key, role in [('window',QPalette.Window),('base',QPalette.Base),('text',QPalette.WindowText),('text',QPalette.Text),('text',QPalette.ButtonText),('accent',QPalette.Highlight),('onAccent',QPalette.HighlightedText)]:
            palette.setColor(role,QColor(controller.theme[key]))
        app.setPalette(palette)
        QIcon.setThemeName('breeze-dark' if QColor(controller.theme['window']).lightness() < 128 else 'breeze')
    icons(); controller.themeChanged.connect(icons)
    engine = QQmlApplicationEngine()
    engine.addImageProvider('icons', Icons())
    engine.setInitialProperties({'controller': controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('qml')/'search'/'Search.qml')))
    if not engine.rootObjects(): raise RuntimeError('Lumen QML search could not be loaded')
    return engine, engine.rootObjects()[0]


def main():
    parser = argparse.ArgumentParser(description='Lumen search')
    parser.add_argument('--voice', action='store_true')
    parser.add_argument('--restore-state', type=Path)
    args = parser.parse_args()
    from lumen_crash import supervise, attach, read_json, write_json
    supervise('search')
    app = QGuiApplication(sys.argv); app.setApplicationName('lumen-search')
    app.setApplicationDisplayName(tr('Lumen Suche')); app.setDesktopFileName('lumen-search')
    app.setQuitOnLastWindowClosed(False); install(app)
    bus = QDBusConnection.sessionBus()
    service = 'org.lumen.Search'
    if bus.isConnected() and not bus.registerService(service):
        reply = bus.call(QDBusMessage.createMethodCall(service, '/Search', service, 'Voice' if args.voice else 'Activate'), QDBus.Block, 3000)
        if reply.type() != QDBusMessage.ErrorMessage: return 0
        print(tr('Die laufende Suche konnte nicht aktiviert werden.'), file=sys.stderr); return 1
    controller = SearchController()
    engine, window = create_window(app, controller)
    activation = Activation(window, controller)
    if bus.isConnected(): bus.registerObject('/Search', activation, QDBusConnection.ExportAllSlots)
    from lumen_store import state_path
    state_file = state_path()/'search.json'
    saved = read_json(args.restore_state or state_file)
    if not saved and args.restore_state is None:
        saved = read_json(state_path()/'search-preview.json')
    if saved:
        try: controller.restore_recovery(saved)
        except (TypeError, ValueError, KeyError, AttributeError, OSError) as error: controller.show_error(str(error))
    previous = None
    def save():
        nonlocal previous
        try:
            state = controller.recovery_state()
            if state != previous: write_json(state_file, state); previous = state
        except (OSError, TypeError, ValueError): pass
    timer = QTimer(app); timer.setInterval(1000); timer.timeout.connect(save); timer.start()
    window.visibleChanged.connect(save)
    app.aboutToQuit.connect(save); app.aboutToQuit.connect(controller.shutdown)
    attach(app, controller, 'search', offer_recovery=False)
    activation.Voice() if args.voice else activation.Activate()
    code = app.exec()
    # Destroy QML bindings while their controller is still alive.
    engine.deleteLater(); app.sendPostedEvents(None, 0)
    return code


if __name__ == '__main__': sys.exit(main())
