"""One retained window for recordings and personal radio; libraries stay separate."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QTabWidget
from lumen_i18n import tr
from tools_meetings import Meetings
from tools_radio import Radio


class MeetingRadio(QMainWindow):
    def __init__(self, initial='meetings', root=None):
        super().__init__()
        self.setWindowTitle(tr('Lumen Audio Studio'))
        self.setWindowIcon(QIcon.fromTheme('lumen-meetings'))
        self.resize(1180, 860)
        from panorama import install
        install(self, 'meetings')
        self.pages = {'meetings': Meetings(root), 'radio': Radio(root)}
        self.tabs = QTabWidget()
        self.tabs.setObjectName('meetingRadioTabs')
        self.tabs.setAccessibleName(tr('Meeting und Radio'))
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setObjectName('meetingRadioBar')
        self.tabs.setStyleSheet('''
            QTabWidget#meetingRadioTabs::pane { border: none; }
            QTabBar#meetingRadioBar::tab { min-width: 120px; padding: 12px 24px;
                border: none; border-bottom: 2px solid transparent; border-radius: 0; }
            QTabBar#meetingRadioBar::tab:selected { background: palette(base);
                color: palette(text); border-bottom: 2px solid palette(highlight); }
            QTabBar#meetingRadioBar::tab:hover:!selected { background: palette(midlight); }
        ''')
        self.setCentralWidget(self.tabs)
        for key, title in (('meetings', tr('Meeting')), ('radio', tr('Radio'))):
            page = self.pages[key]
            page.setWindowFlags(Qt.Widget)
            page.panorama_bar.hide()
            self.tabs.addTab(page, title)
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
