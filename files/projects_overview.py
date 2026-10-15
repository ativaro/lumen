"""Native counterpart of the server's full-width project card overview."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFontDatabase, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPushButton, QScrollArea
from lumen_i18n import tr, language
from tools_ui import label, button, row


STYLE = '''
QWidget#projectHome,QWidget#projectHome QWidget { font-family:'DM Sans 9pt'; }
QWidget#projectHome { background:#1e2122;color:#ecf0ee; }
QWidget#projectHome QLabel { color:#ecf0ee;background:transparent; }
QWidget#projectHome QLabel#overviewEyebrow { color:#8dac9f;font-size:10px;font-weight:600;letter-spacing:2px; }
QWidget#projectHome QLabel#overviewTitle { font-size:34px;font-weight:500; }
QWidget#projectHome QLabel#overviewMuted { color:#a3afac;font-size:13px; }
QWidget#projectHome QLabel#overviewSmall { color:#a3afac;font-size:11px; }
QWidget#projectHome QPushButton#overviewNew { background:#aed5c8;color:#172c24;border:0;border-radius:8px;padding:12px 18px;font-size:13px; }
QWidget#projectHome QPushButton#overviewFilter { border:0;border-radius:18px;padding:9px 13px;font-size:12px;color:#a3afac;background:transparent; }
QWidget#projectHome QPushButton#overviewFilter:checked { background:#303d37;color:#aed5c8;border:0;border-radius:18px;min-height:18px; }
QWidget#projectHome QLineEdit#overviewSearch { border:0;border-bottom:1px solid #353d3e;border-radius:0;background:transparent;color:#ecf0ee;padding:11px 0;font-size:13px; }
QWidget#projectHome QPushButton#projectCard { background:#25292a;border:1px solid #353d3e;border-radius:12px;padding:0;text-align:left;min-height:256px; }
QWidget#projectHome QPushButton#projectCard:hover,QWidget#projectHome QPushButton#projectCard:focus { border:1px solid #aed5c8; }
QWidget#projectHome QLabel#projectCardTitle { font-size:20px;font-weight:500; }
QWidget#projectHome QPushButton#recentProject { background:transparent;border:0;border-bottom:1px solid #353d3e;border-radius:0;padding:0;text-align:left;min-height:74px; }
QWidget#projectHome QPushButton#recentProject:focus { border:1px solid #aed5c8; }
QWidget#projectHome QLabel#recentTitle { font-size:13px;font-weight:500; }
QWidget#projectHome QWidget#overviewRecent { border-top:1px solid #353d3e; }
QWidget#projectHome QLabel#recentHeading { font-size:18px;font-weight:500; }
QWidget#projectHome QScrollArea,QWidget#overviewPage { border:0;background:#1e2122; }
'''


_fonts_loaded = False


def load_fonts():
    global _fonts_loaded
    if not _fonts_loaded:
        for path in (Path(__file__).parent/'project_fonts').glob('*.woff2'):
            QFontDatabase.addApplicationFont(str(path))
        _fonts_loaded = True


class ProjectGlyph(QWidget):
    def __init__(self, parent=None, compact=False):
        super().__init__(parent);self.compact=compact;self.setFixedSize(20,20) if compact else self.setFixedSize(40,40)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        if self.compact:painter.translate(-8,-8);painter.scale(.9,.9)
        else:
            painter.setPen(Qt.NoPen);painter.setBrush(QColor('#303d37'));painter.drawRoundedRect(QRectF(0,0,40,40),12,12)
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(QColor('#aed5c8'),1.5))
        painter.drawLine(10,16,10,11);painter.drawLine(10,11,17,11);painter.drawLine(17,11,20,15);painter.drawLine(20,15,30,15)
        painter.drawLine(10,16,30,16);painter.drawLine(30,16,27,29);painter.drawLine(27,29,10,29);painter.drawLine(10,29,10,16)


def stamp(value):
    try:return datetime.fromtimestamp(value).strftime('%d/%m/%Y' if language()=='en' else '%d.%m.%Y') if value else ''
    except (ValueError,TypeError,OSError):return ''


class ProjectOverview(QWidget):
    selected=Signal(str)

    def __init__(self, window):
        super().__init__();self.window=window;self.signature=None;self.cards=[];self.columns=0
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        toolbar=QHBoxLayout();toolbar.setContentsMargins(0,35,0,22);toolbar.setSpacing(24)
        self.search=QLineEdit();self.search.setObjectName('overviewSearch');self.search.setPlaceholderText(tr('Projekte suchen …'));self.search.setAccessibleName(tr('Projekte suchen'));self.search.setMaximumWidth(360);self.search.addAction(QIcon.fromTheme('edit-find'),QLineEdit.LeadingPosition)
        toolbar.addWidget(self.search,1);toolbar.addStretch(1)
        self.active=button(tr('Aktiv'),lambda:self.filter(False));self.archive=button(tr('Archiv'),lambda:self.filter(True))
        for control in (self.active,self.archive):control.setObjectName('overviewFilter');control.setCheckable(True);toolbar.addWidget(control)
        self.active.setChecked(True);outer.addLayout(toolbar);self.search.textChanged.connect(self.refresh)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);outer.addWidget(scroll,1)
        self.page=QWidget();self.page.setObjectName('overviewPage');scroll.setWidget(self.page)
        self.body=QVBoxLayout(self.page);self.body.setContentsMargins(0,0,0,0);self.body.setSpacing(0)
        self.grid=QGridLayout();self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(20);self.body.addLayout(self.grid)
        self.empty=label('','overviewMuted');self.body.addWidget(self.empty)
        self.body.addSpacing(38);self.recent=QWidget();self.recent.setObjectName('overviewRecent');self.recent.setAttribute(Qt.WA_StyledBackground);self.recent_box=QVBoxLayout(self.recent);self.recent_box.setContentsMargins(0,26,0,0);self.recent_box.setSpacing(0);self.body.addWidget(self.recent);self.body.addStretch(1)
        self.refresh()

    def filter(self, archived):
        self.archive.setChecked(archived);self.active.setChecked(not archived);self.refresh()

    def refresh(self, *_):
        records=self.window.library.all(self.archive.isChecked())
        with self.window.library.connect() as db:dates={r['id']:r['updated'] for r in db.execute('SELECT id,updated FROM records')}
        records=[dict(r,updated=dates.get(r['id'])) for r in records if self.search.text().casefold() in (r['title']+' '+r.get('notes','')).casefold()]
        signature=repr((records,self.archive.isChecked(),self.search.text()))
        if signature==self.signature:return
        self.signature=signature
        for card in self.cards:self.grid.removeWidget(card);card.deleteLater()
        self.cards=[]
        while self.recent_box.count():
            item=self.recent_box.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.empty.setVisible(not records)
        self.empty.setText(tr('Noch keine archivierten Projekte.' if self.archive.isChecked() else 'Keine passenden Projekte gefunden.' if self.search.text() else 'Lege dein erstes Projekt an und sammle alles, was dazugehört.'))
        self.recent.setVisible(bool(records))
        if records:
            hint=label(tr('Deine Projekte im Blick'),'overviewSmall');hint.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            heading=row(label(tr('Zuletzt bearbeitet'),'recentHeading'),hint);self.recent_box.addWidget(heading)
        for record in records:
            card=QPushButton();card.setObjectName('projectCard');card.setAccessibleName(record['title']);card.setCursor(Qt.PointingHandCursor);card.setMinimumHeight(256);card.setMinimumWidth(0)
            box=QVBoxLayout(card);box.setContentsMargins(24,24,24,24);box.setSpacing(0)
            date=label(stamp(record['updated']),'overviewSmall');date.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            top=row(ProjectGlyph(),date);box.addWidget(top);box.addSpacing(26)
            title=label(record['title'],'projectCardTitle');title.setMinimumWidth(0);box.addWidget(title);box.addSpacing(13)
            description=label(record.get('notes') or tr('Quellen, Gespräche und Aufgaben an einem Ort sammeln.'),'overviewMuted');description.setMaximumHeight(66);description.setMinimumWidth(0);box.addWidget(description);box.addStretch(1);box.addSpacing(25)
            arrow=label('→','overviewMuted');arrow.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            box.addWidget(row(label(tr('Archiviert' if self.archive.isChecked() else 'Projekt öffnen'),'overviewMuted'),arrow))
            for child in card.findChildren(QWidget):child.setAttribute(Qt.WA_TransparentForMouseEvents)
            card.clicked.connect(lambda checked=False,key=record['id']:self.selected.emit(key));self.cards.append(card)
        for record in records[:3]:
            recent=QPushButton();recent.setObjectName('recentProject');recent.setAccessibleName(record['title']);recent.setCursor(Qt.PointingHandCursor)
            line=QHBoxLayout(recent);line.setContentsMargins(0,17,0,17);line.setSpacing(15);line.addWidget(ProjectGlyph(compact=True))
            text=QWidget();box=QVBoxLayout(text);box.setContentsMargins(0,0,0,0);box.setSpacing(7);box.addWidget(label(record['title'],'recentTitle'));box.addWidget(label(tr('Projektjournal öffnen'),'overviewSmall'))
            line.addWidget(text,1);line.addWidget(label(stamp(record['updated']),'overviewSmall'));line.addWidget(label('→','overviewSmall'))
            for child in recent.findChildren(QWidget):child.setAttribute(Qt.WA_TransparentForMouseEvents)
            recent.clicked.connect(lambda checked=False,key=record['id']:self.selected.emit(key));self.recent_box.addWidget(recent)
        self.reflow()

    def reflow(self):
        columns=3 if self.width()>1050 else 2 if self.width()>600 else 1
        for card in self.cards:self.grid.removeWidget(card)
        for index in range(3):self.grid.setColumnStretch(index,1 if index<columns else 0)
        for index,card in enumerate(self.cards):self.grid.addWidget(card,index//columns,index%columns)
        self.columns=columns

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()
