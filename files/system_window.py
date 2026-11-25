"""Retained System and Sound pages in one native window."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSettings, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QTabWidget
from PySide6.QtQuickWidgets import QQuickWidget
from lumen_i18n import tr
from tools_sound import Sound


class SystemWindow(QMainWindow):
    def __init__(self, controller, initial='system', root=None, store=None):
        super().__init__()
        self.controller = controller
        self.setWindowTitle('Lumen System')
        self.setWindowIcon(QIcon.fromTheme('lumen-system'))
        self.resize(1280, 940); self.setMinimumSize(850, 680)
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setObjectName('systemSections')
        self.tabs.setStyleSheet('QTabBar#systemSections::tab { padding: 12px 10px; min-width: 66px; border-radius: 0; border: none; border-bottom: 2px solid transparent; } QTabBar#systemSections::tab:selected { background: palette(base); color: palette(text); border-bottom: 2px solid palette(highlight); } QTabBar#systemSections::tab:hover:!selected { background: palette(midlight); }')
        self.tabs.setAccessibleName(tr('Systembereiche'))
        self.setCentralWidget(self.tabs)
        self.system = QQuickWidget()
        self.system.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.system.setInitialProperties({'controller': controller})
        self.system.setSource(QUrl.fromLocalFile(str(Path(__file__).with_name('qml')/'system'/'System.qml')))
        if self.system.status() == QQuickWidget.Error:
            raise RuntimeError('Lumen System QML failed to load')
        self.system.setFocusPolicy(Qt.StrongFocus)
        self.sound = Sound(root); self.sound.setWindowFlags(Qt.Widget)
        from server_devices import ServerDevices
        self.server_devices = ServerDevices(self)
        from updater_app import UpdaterPage
        from system_diagnostics import DiagnosticsPage
        self.updates = UpdaterPage()
        self.diagnostics = DiagnosticsPage(self, store)
        self.pages = {'updates': self.updates, 'diagnostics': self.diagnostics, 'server': self.server_devices, 'system': self.system, 'sound': self.sound}
        for key, title in (('system', tr('System')), ('sound', tr('Sound')), ('server', tr('Server & Geräte')), ('updates', tr('Updates')), ('diagnostics', tr('Diagnose'))):
            self.tabs.addTab(self.pages[key], title.replace('&', '&&'))
        self.select(initial)
        self.state = QSettings('Lumen', 'System')
        from lumen_apps import startup_preference
        if startup_preference('sound' if initial == 'sound' else 'system', 'restoreGeometry'):
            geometry = self.state.value('geometry')
            if geometry: self.restoreGeometry(geometry)

    def select(self, page):
        if page == 'tasks':
            self.diagnostics.open_tasks(); page = 'diagnostics'
        if page not in self.pages: raise ValueError(tr('Unbekannter Systembereich.'))
        self.tabs.setCurrentWidget(self.pages[page])

    def activate(self, page=None):
        from lumen_activation import present
        if page is not None: self.select(page)
        present(self)

    def activate_sound(self, request):
        if not isinstance(request, dict): raise ValueError(tr('Ungültige App-Anfrage.'))
        from interop_ui import controller
        if request: controller(self.sound).enqueue(request)
        self.activate('sound')

    def closeEvent(self, event):
        if not self.diagnostics.system_status.can_close() or not self.diagnostics.task_controller.can_close(): event.ignore(); return
        if self.updates.running:
            self.select('updates')
            self.updates.closeEvent(event)
            return
        if self.sound.job:
            self.select('sound')
            self.sound.timer.start()
            self.sound.status.setText(tr('Bitte den laufenden Vorgang abschließen, bevor du Lumen System schließt.'))
            event.ignore(); return
        # A bounded read-only mixer poll may still own a QThread.
        if self.sound.poller:
            self.sound.timer.stop()
            QTimer.singleShot(80, self.close)
            event.ignore(); return
        try:
            self.sound.save()
        except Exception as error:
            self.sound.timer.start()
            self.select('sound'); self.sound.error(str(error)); event.ignore(); return
        self.sound.closing = True; self.sound.timer.stop()
        self.diagnostics.checks.stop()
        self.diagnostics.task_controller.shutdown()
        self.diagnostics.system_status.shutdown()
        self.controller.shutdown()
        self.state.setValue('geometry', self.saveGeometry()); self.state.sync()
        event.accept()
