"""Native wrapping sentence parts; no browser or second automation model."""
from html import escape
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtWidgets import QLayout,QPushButton,QLabel,QHBoxLayout,QSizePolicy
from studio_design import icon,font

ICONS={'manual':'input-mouse','read_file':'document-open','filter_text':'view-filter',
       'ai':'tools-wizard','ai_check':'tools-wizard','condition':'view-filter',
       'choose':'view-process-tree','for_each':'view-refresh','delay':'chronometer',
       'approval':'dialog-ok','save_file':'document-save','save_note':'document-edit',
       'create_task':'view-task','project_note':'folder','notify':'notifications',
       'if_pdf':'view-process-tree','end_each':'view-list-details'}

ACTIONS={'read_file':'eine Datei lesen','filter_text':'die Textzeilen filtern',
         'ai':'meinen Auftrag bearbeiten','ai_check':'einen Inhalt mit KI prüfen',
         'notify':'mich informieren','save_note':'eine Notiz in Lumen Notes speichern',
         'save_file':'eine Datei speichern','create_task':'eine Aufgabe in Lumen Inbox erstellen',
         'project_note':'eine Projektnotiz ergänzen','approval':'auf meine Bestätigung warten',
         'choose':'einen passenden Weg wählen','for_each':'jede Textzeile durchlaufen',
         'delay':'warten','if_pdf':'PDF-Dateien gesondert behandeln','condition':'eine Bedingung prüfen'}


class SentenceFlow(QLayout):
    def __init__(self,parent=None,spacing=8):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(spacing)
    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientations(Qt.Orientation(0))
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),False)
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,True)
    def sizeHint(self):return self.minimumSize()
    def minimumSize(self):return QSize(0,42)
    def arrange(self,rect,apply):
        x=rect.x();y=rect.y();height=0;space=self.spacing()
        for item in self.items:
            w=item.widget();width=min(max(0,rect.width()),item.sizeHint().width())
            if x>rect.x() and x+width>rect.right()+1:x=rect.x();y+=height+space;height=0
            h=w.heightForWidth(width) if w and w.hasHeightForWidth() else item.sizeHint().height()
            if apply:item.setGeometry(QRect(x,y,width,h))
            x+=width+space;height=max(height,h)
        return y+height-rect.y()


class SentencePart(QPushButton):
    def __init__(self,text,callback,kind='manual'):
        super().__init__();self.setObjectName('sentencePart');self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(text);self.setToolTip('<qt>'+escape(text)+'</qt>');self.clicked.connect(callback)
        policy=self.sizePolicy();policy.setHeightForWidth(True);policy.setVerticalPolicy(QSizePolicy.Preferred);self.setSizePolicy(policy)
        layout=QHBoxLayout(self);layout.setSizeConstraint(QLayout.SetNoConstraint);layout.setContentsMargins(10,4,10,4);layout.setSpacing(8)
        mark=QLabel();mark.setPixmap(icon(ICONS.get(kind,'tools-wizard')).pixmap(20,20));layout.addWidget(mark)
        self.caption=QLabel(text);self.caption.setFont(font(23));self.caption.setTextFormat(Qt.PlainText);self.caption.setWordWrap(True);self.caption.setMinimumWidth(0);layout.addWidget(self.caption,1)
        for child in (mark,self.caption):child.setAttribute(Qt.WA_TransparentForMouseEvents)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return max(42,self.layout().totalHeightForWidth(max(60,width)))
    def sizeHint(self):
        return QSize(min(700,self.caption.fontMetrics().horizontalAdvance(self.caption.text())+50),42)
    def minimumSizeHint(self):return QSize(0,42)


STYLE='''
QFrame#sentence { background:palette(base);border:0;border-top:1px solid palette(mid);border-bottom:1px solid palette(mid); }
QLabel#sentenceText, QPushButton#sentencePart QLabel { font-size:23px;background:transparent;color:palette(text);border:0; }
QPushButton#sentencePart { padding:0;background:palette(midlight);color:palette(text);border:1px solid palette(mid); }
QPushButton#sentencePart:hover, QPushButton#sentencePart:focus { border-color:palette(highlight); }
'''
