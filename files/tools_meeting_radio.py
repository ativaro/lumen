"""One retained window for recordings and personal radio; libraries stay separate."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from studio_design import font
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QTabBar, QWidget, QVBoxLayout
from lumen_i18n import tr
from tools_meetings import Meetings
from tools_radio import Radio
from tools_ui import button


class MeetingRadio(QMainWindow):
    def __init__(self, initial='meetings', root=None):
        super().__init__()
        self.setWindowTitle(tr('Lumen Audio Studio'))
        self.setWindowIcon(QIcon.fromTheme('lumen-meetings'))
        self.resize(1180, 860)
        self.setFont(font(14))
        self.pages = {'meetings': Meetings(root), 'radio': Radio(root)}
        self.tabs = QStackedWidget()
        self.modes = QTabBar(); self.modes.setExpanding(False); self.modes.setDrawBase(False)
        self.modes.setAccessibleName(tr('Aufnahmen oder Hörskripte'))
        self.modes.addTab(tr('Aufnahmen')); self.modes.addTab(tr('Hörskripte'))
        self.modes.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.modes.setCurrentIndex)
        from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
        shell=QWidget();box=QVBoxLayout(shell);box.setContentsMargins(PAGE_MARGIN,20,PAGE_MARGIN,20);box.setSpacing(PAGE_SPACING)
        self.app_header=AppHeader(tr('Lumen Audio Studio'),tr('Aufnahmen, Transkripte und Hörskripte.'))
        self.app_header.actions.addWidget(self.modes)
        self.app_header.actions.addWidget(button('Lumen Apps',lambda:self.tabs.currentWidget().safe(self.tabs.currentWidget().open_apps),'view-grid'))
        self.settings_button=button(tr('Einstellungen'),lambda:self.tabs.currentWidget().open_settings(),'configure')
        self.app_header.actions.addWidget(self.settings_button)
        box.addWidget(self.app_header);box.addWidget(self.tabs,1);self.setCentralWidget(shell)
        for key in ('meetings','radio'):
            page = self.pages[key]
            page.setWindowFlags(Qt.Widget)
            page.app_header.hide()
            page.centralWidget().layout().setContentsMargins(0,0,0,0)
            self.tabs.addWidget(page)
        self.select(initial)

    def select(self, name):
        self.tabs.setCurrentWidget(self.pages[name])

    def closeEvent(self, event):
        # Check both pages before shutting either down: a hidden tab can be busy.
        for name, page in self.pages.items():
            if page.job or (page.engine and page.engine.busy):
                self.select(name)
                page.cancel()
                page.status.setText(tr('Abbruch läuft. Danach kann das Fenster geschlossen werden.'))
                event.ignore()
                return
        for name, page in self.pages.items():
            try:
                page.save()
            except Exception as error:
                self.select(name)
                page.error(str(error))
                event.ignore()
                return
        for page in self.pages.values():
            if page.engine:
                page.engine.shutdown()
            page.player.stop()
        event.accept()
