"""One calendar editor for routine creation, edits and block triggers."""
from datetime import datetime
from PySide6.QtCore import Signal,QDate,QTime
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTimeEdit,QDateEdit,QSpinBox,QCheckBox
from tools_ui import label
from code_condition_ui import combo
from code_clock import default,validate,describe,starts,ZONE
from lumen_i18n import tr


class ClockEditor(QWidget):
    changed=Signal()
    def __init__(self,parent=None,directory=False):
        super().__init__(parent);self.columns=QHBoxLayout(self);self.columns.setContentsMargins(0,0,0,0);self.columns.setSpacing(24)
        left=QWidget();box=QVBoxLayout(left);box.setContentsMargins(0,0,0,0);box.setSpacing(8);self.columns.addWidget(left,3)
        right=QWidget();side=QVBoxLayout(right);side.setContentsMargins(0,0,0,0);side.setSpacing(12);self.columns.addWidget(right,2)
        def field(title,control):
            caption=label(tr(title));caption.setBuddy(control);control.caption=caption;box.addWidget(caption);control.setAccessibleName(tr(title));box.addWidget(control);return control
        options=[('weekly','Nach Wochenplan'),('daily','Jeden Tag'),('monthly','Monatlich'),('once','Einmalig'),('interval','In Abständen'),('manual','Nur manuell')]
        if directory:options.append(('directory','Bei Ordneränderung'))
        self.kind=field('Wiederholung',combo(options,'weekly'))
        self.time=field('Uhrzeit',QTimeEdit(QTime(8,30)));self.time.setDisplayFormat('HH:mm')
        self.date=field('Datum',QDateEdit(QDate.currentDate().addDays(1)));self.date.setCalendarPopup(True);self.date.setDisplayFormat('dd.MM.yyyy')
        self.month=field('Tag im Monat',QSpinBox());self.month.setRange(1,31)
        self.minutes=field('Abstand in Minuten',QSpinBox());self.minutes.setRange(15,525600);self.minutes.setValue(60)
        self.days=[];self.days_widget=QWidget();days=QHBoxLayout(self.days_widget);days.setContentsMargins(0,0,0,0)
        for i,title in enumerate(('Mo','Di','Mi','Do','Fr','Sa','So')):
            c=QCheckBox(tr(title));c.setChecked(i<5);days.addWidget(c);self.days.append(c);c.toggled.connect(self.refresh)
        box.addWidget(self.days_widget);box.addStretch();self.summary=label('','codeCardTitle');side.addWidget(self.summary)
        self.preview=label('','codeMuted');self.preview.setAccessibleName(tr('Nächste Starts · Vorschau'));side.addWidget(self.preview)
        self.zone=label('Europe/Zurich','codeMuted');self.zone.setToolTip(tr('Sommer-/Winterzeit berücksichtigt. Fehlende Uhrzeiten und Monatstage werden übersprungen.'));self.zone.setAccessibleDescription(self.zone.toolTip());side.addWidget(self.zone);side.addStretch()
        self.kind.currentIndexChanged.connect(self.refresh);self.time.timeChanged.connect(self.refresh);self.date.dateChanged.connect(self.refresh);self.month.valueChanged.connect(self.refresh);self.minutes.valueChanged.connect(self.refresh);self.refresh()

    def value(self,checked=True):
        value={**default(),'kind':self.kind.currentData(),'time':self.time.time().toString('HH:mm'),'date':self.date.date().toString('yyyy-MM-dd'),'month_day':self.month.value(),'minutes':self.minutes.value(),'days':[i for i,c in enumerate(self.days) if c.isChecked()]}
        return validate(value) if checked and value['kind']!='directory' else value

    def set_value(self,value):
        self.blockSignals(True)
        try:
            self.kind.setCurrentIndex(self.kind.findData(value['kind']));self.time.setTime(QTime.fromString(value['time'],'HH:mm'));self.date.setDate(QDate.fromString(value['date'],'yyyy-MM-dd'));self.month.setValue(value['month_day']);self.minutes.setValue(value['minutes'])
            for i,c in enumerate(self.days):c.setChecked(i in value['days'])
            self.refresh()
        finally:self.blockSignals(False)

    def refresh(self,*_):
        kind=self.kind.currentData()
        for control,visible in ((self.time,kind in ('weekly','daily','monthly','once')),(self.date,kind=='once'),(self.month,kind=='monthly'),(self.minutes,kind in ('interval','directory'))):
            control.setVisible(visible);control.caption.setVisible(visible)
        self.days_widget.setVisible(kind=='weekly');self.zone.setVisible(kind not in ('manual','directory'))
        try:
            value=self.value();self.summary.setText(tr('Bei Ordneränderung') if kind=='directory' else describe(value))
            text=tr('Prüft alle {0} Minuten den ausgewählten Quellordner.',value['minutes']) if kind=='directory' else '\n'.join(datetime.fromtimestamp(v,ZONE).strftime('%d.%m.%Y · %H:%M') for v in starts(value))
            self.preview.setToolTip(text);self.preview.setAccessibleDescription(text)
            self.preview.setText((tr('Nächster Start · Vorschau')+'\n'+text.split('\n')[0]) if text and kind!='directory' else text)
        except ValueError as error:self.summary.setText(tr(str(error)));self.preview.clear()
        self.changed.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.columns.setDirection(QHBoxLayout.TopToBottom if self.width()<620 else QHBoxLayout.LeftToRight)
