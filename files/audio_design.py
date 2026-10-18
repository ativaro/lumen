"""Audio Studio's library and reading surface, using the shared native palette."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QStackedWidget, QHeaderView, QListWidgetItem, QTableWidget
from lumen_i18n import tr
from tools_data import clock_text
from tools_ui import ToolWindow, button, label


STYLE = '''
QLineEdit#audioTitle { background:transparent;border:1px solid transparent;padding:4px 0;font-size:26px;font-weight:500; }
QLineEdit#audioTitle:focus { border-bottom-color:palette(highlight); }
QLabel#audioEyebrow { color:palette(link);font-size:11px;font-weight:600;letter-spacing:2px; }
QLabel#audioEmptyTitle { font-size:26px;font-weight:500; }
QLabel#audioEmptyDescription { color:palette(placeholder-text);font-size:14px; }
QTabWidget#audioContent::pane { border:0;background:transparent; }
QTabBar#audioSections::tab { min-width:0;padding:10px 16px;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent; }
QTabBar#audioSections::tab:selected { color:palette(text);border-bottom-color:palette(highlight); }
QTabBar#audioSections::tab:hover { background:palette(midlight); }
QTableWidget#audioTranscript { background:transparent;color:palette(text);border:0;outline:0;font-size:16px; }
QTableWidget#audioTranscript::item { padding:18px 12px;border:0;border-bottom:1px solid palette(mid); }
QTableWidget#audioTranscript::item:selected { background:palette(midlight);color:palette(text); }
QTableWidget#audioResults { background:transparent;color:palette(text);border:0;outline:0; }
QTableWidget#audioResults::item { padding:12px 8px;border:0;border-bottom:1px solid palette(mid); }
QTableWidget#audioResults::item:selected { background:palette(midlight);color:palette(text); }
QPlainTextEdit#audioEditor { background:transparent;color:palette(text);border:1px solid palette(mid);padding:16px;font-size:15px;selection-background-color:palette(highlight);selection-color:palette(highlighted-text); }
QPlainTextEdit#audioEditor:focus { border-color:palette(highlight); }
'''


class AudioEmpty(QFrame):
    def __init__(self, category, title, description, action, callback):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(32,32,32,32); layout.setSpacing(16)
        layout.addStretch(2)
        for text, name in ((category,'audioEyebrow'),(title,'audioEmptyTitle'),(description,'audioEmptyDescription')):
            item = label(text,name); item.setMaximumWidth(480); layout.addWidget(item)
        self.action = button(action,callback,primary=True)
        layout.addWidget(self.action,0,Qt.AlignLeft); layout.addStretch(3)


class AudioWindow(ToolWindow):
    def __init__(self, name, title, tagline, icon, root=None):
        super().__init__(name,title,tagline,icon,root)
        self.centralWidget().setStyleSheet(self.centralWidget().styleSheet()+STYLE)
        self.sidebar.layout().insertWidget(0,label(tr('BIBLIOTHEK'),'eyebrow'))
        self.search.setPlaceholderText(tr('Aufnahmen suchen …') if name=='meetings' else tr('Hörskripte suchen …'))
        self.entries.setWordWrap(True)
        self.content.setSpacing(16)
        self.surface = QStackedWidget()
        self.split.replaceWidget(1,self.surface); self.surface.addWidget(self.body)
        self.split.setStretchFactor(0,0); self.split.setStretchFactor(1,1)
        self.split.setSizes([224,self.width()-272])
        if name=='meetings':
            self.empty = AudioEmpty(tr('AUFNAHMEN'),tr('Aus Zuhören wird Wissen.'),
                tr('Importiere eine Aufnahme. Lies das Transkript mit Zeitstellen, halte Entscheidungen fest und finde offene Aufgaben wieder.'),
                tr('Aufnahme importieren'),lambda:self.safe(self.create))
        else:
            self.empty = AudioEmpty(tr('HÖRSKRIPTE'),tr('Deine Quellen. Zum Anhören.'),
                tr('Sammle Artikel, Dokumente und eigene Texte. Forme daraus ein Hörskript und lass es mit einer lokalen Stimme vorlesen.'),
                tr('Hörskript anlegen'),lambda:self.safe(self.create))
        self.surface.addWidget(self.empty)

    def refresh(self, *_):
        self.entries.blockSignals(True); self.entries.clear(); selected = None
        for record in self.library.all(self.archived.isChecked(),self.search.text()):
            detail = (clock_text(record.get('duration',0))+' · '+tr('{0} Textstellen',len(record.get('segments',[])))) if self.name=='meetings' else tr('{0} Quellen · {1} min',len(record.get('sources',[])),record.get('minutes',5))
            item = QListWidgetItem(record['title']+'\n'+detail); item.setToolTip(record['title']+'\n'+detail)
            item.setData(Qt.UserRole,record['id']); self.entries.addItem(item)
            if record['id']==self.current: selected=item
        self.entries.setCurrentItem(selected); self.entries.blockSignals(False)
        self.archive_button.setEnabled(bool(self.current))
        self.archive_button.setText(tr('Wiederherstellen') if self.archived.isChecked() else tr('Archivieren'))
        self.surface.setCurrentWidget(self.body if self.current else self.empty)

    def begin(self, text):
        super().begin(text); self.empty.setEnabled(False)

    def end(self):
        super().end(); self.empty.setEnabled(True)


def content_tabs(tabs):
    tabs.setObjectName('audioContent'); tabs.setDocumentMode(True)
    tabs.tabBar().setObjectName('audioSections'); tabs.tabBar().setDrawBase(False)


class TranscriptTable(QTableWidget):
    def __init__(self):
        super().__init__(0,2)
        self.setObjectName('audioTranscript'); self.setShowGrid(False)
        self.horizontalHeader().hide(); self.verticalHeader().setMinimumSectionSize(80)
        self.setColumnWidth(0,112); self.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.setAccessibleName(tr('Transkript mit anklickbaren Zeitstellen und bearbeitbarem Text'))
        self.itemChanged.connect(lambda item:self.resizeRowToContents(item.row()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resizeRowsToContents()
