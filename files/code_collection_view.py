"""Collection rows keep the native tree's selection, keyboard and accessibility."""
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtGui import QFontMetrics,QPalette,QPainter,QIcon
from PySide6.QtWidgets import QStyledItemDelegate,QStyle,QApplication,QComboBox,QStyleOptionComboBox
from studio_design import font,icon
from code_design import ICONS

QUIET_STYLE='''
QPushButton#codeCollectionQuiet { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 7px 8px; color: palette(placeholder-text); font-size: 12px; }
QPushButton#codeCollectionQuiet:hover { background: palette(alternate-base); color: palette(text); }
QPushButton#codeCollectionQuiet:focus { border-color: palette(highlight); }
'''

STYLE='''
QFrame#codeCollectionList, QFrame#codeCollectionPreview, QFrame#codeCollectionEmpty {
 background: palette(base); border: 1px solid palette(mid); border-radius: 10px;
}
QFrame#codeCollectionPreview QLabel, QFrame#codeCollectionEmpty QLabel { background: transparent; border: none; }
QTreeWidget#codeEntries { background: transparent; border: none; padding: 0; outline: none; }
QLabel#codePreviewTitle { font-size: 24px; font-weight: 500; }
QLabel#codeCollectionCount { font-size: 12px; color: palette(placeholder-text); }
QLabel#codePreviewKind { font-size: 12px; color: palette(link); }
QLabel#codePreviewState { color: palette(link); font-size: 12px; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down {
 subcontrol-origin: padding; subcontrol-position: top right; width: 28px;
 border: none; background: transparent;
}
QComboBox::down-arrow { image: none; }
'''+QUIET_STYLE


class CollectionComboBox(QComboBox):
    """Keep the theme arrow inside the field without a separate native button."""
    def paintEvent(self,event):
        super().paintEvent(event)
        option=QStyleOptionComboBox();self.initStyleOption(option)
        area=self.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxArrow,self)
        painter=QPainter(self)
        rect=QRect(area.center().x()-6,area.center().y()-6,12,12)
        icon('go-down').paint(painter,rect,Qt.AlignCenter,QIcon.Normal if self.isEnabled() else QIcon.Disabled)
        painter.end()


class EntryDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):return QSize(0,94)

    def paint(self,painter,option,index):
        value=index.siblingAtColumn(0).data(Qt.UserRole+1)
        if not value:return
        painter.save();painter.setRenderHint(QPainter.Antialiasing)
        palette=QApplication.palette();rect=option.rect
        selected=bool(option.state & QStyle.State_Selected)
        hover=bool(option.state & QStyle.State_MouseOver)
        painter.fillRect(rect,palette.alternateBase() if selected or hover else palette.base())
        painter.setPen(palette.color(QPalette.Mid));painter.drawLine(rect.bottomLeft(),rect.bottomRight())
        if index.column()==0:
            badge=QRect(rect.left()+12,rect.top()+24,36,42)
            painter.setPen(Qt.NoPen);painter.setBrush(palette.alternateBase());painter.drawRoundedRect(badge,7,7)
            icon('view-split-left-right' if value['kind']=='app' else ICONS[value['kind']]).paint(painter,badge.adjusted(8,11,-8,-11))
            left=rect.left()+62;width=max(0,rect.width()-74)
            self.text(painter,QRect(left,rect.top()+15,width,23),value['title'],15,palette.color(QPalette.Text))
            self.text(painter,QRect(left,rect.top()+39,width,20),value['description'],12,palette.color(QPalette.PlaceholderText))
            self.text(painter,QRect(left,rect.top()+62,width,18),value['context'],10,palette.color(QPalette.PlaceholderText))
        elif index.column()==2:
            painter.setFont(font(10));metrics=QFontMetrics(painter.font());width=max(0,rect.width()-12)
            text=metrics.elidedText(index.data() or '',Qt.ElideRight,max(0,width-18))
            pill=QRect(rect.left()+4,rect.center().y()-13,min(width,metrics.horizontalAdvance(text)+18),26)
            painter.setPen(Qt.NoPen);painter.setBrush(palette.alternateBase());painter.drawRoundedRect(pill,6,6)
            painter.setPen(palette.color(QPalette.Text));painter.drawText(pill,Qt.AlignCenter,text)
        elif index.column()==3:
            painter.setFont(font(21));painter.setPen(palette.color(QPalette.Link if value['favorite'] else QPalette.PlaceholderText))
            painter.drawText(rect,Qt.AlignCenter,'★' if value['favorite'] else '☆')
        if option.state & QStyle.State_HasFocus:
            painter.setPen(palette.color(QPalette.Highlight));painter.setBrush(Qt.NoBrush);painter.drawRoundedRect(rect.adjusted(1,1,-2,-2),4,4)
        painter.restore()

    @staticmethod
    def text(painter,rect,text,size,color):
        painter.setFont(font(size));painter.setPen(color)
        painter.drawText(rect,Qt.AlignLeft|Qt.AlignVCenter,QFontMetrics(painter.font()).elidedText(text,Qt.ElideRight,rect.width()))
