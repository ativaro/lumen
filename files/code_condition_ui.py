"""Native typed condition rows; the stored structure stays visible and editable."""
import copy
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLineEdit,QCheckBox,QDoubleSpinBox
from tools_ui import button,label
from lumen_i18n import tr
from code_conditions import FIELDS,OPERATORS,OP_LABELS,validate


def combo(options, current):
    control=QComboBox()
    for key,text in options:control.addItem(tr(text),key)
    control.setCurrentIndex(max(0,control.findData(current)))
    return control


class ConditionEditor(QWidget):
    changed=Signal()
    def __init__(self,available,value=None,parent=None,depth=0):
        super().__init__(parent);self.available=set(available);self.depth=depth;self.rows=[]
        value=copy.deepcopy(value or {'field':next(iter(k for k in FIELDS if k in available)),'op':'exists','value':True})
        negate='not' in value
        if negate:value=value['not']
        group='all' if 'all' in value else 'any' if 'any' in value else None
        self.original_group=group
        self.box=QVBoxLayout(self);self.box.setContentsMargins(0,0,0,0);self.box.setSpacing(8)
        head=QHBoxLayout();self.mode=combo([('all','Alle Bedingungen'),('any','Mindestens eine Bedingung')],group or 'all');self.mode.setAccessibleName(tr('Bedingungen verknüpfen'));head.addWidget(self.mode,1)
        self.negate=QCheckBox(tr('Nicht'));self.negate.setChecked(negate);head.addWidget(self.negate);self.box.addLayout(head)
        for child in value[group] if group else [value]:self.add(child)
        row=QHBoxLayout();row.addWidget(button(tr('+ Bedingung'),lambda:self.add()));self.group_button=button(tr('+ Gruppe'),self.add_group);self.group_button.setEnabled(depth<3);row.addWidget(self.group_button);row.addStretch();self.box.addLayout(row)
        self.mode.currentIndexChanged.connect(self.changed);self.negate.toggled.connect(self.changed)

    def add(self,value=None):
        if len(self.rows)>=8:return
        value=copy.deepcopy(value or {'field':next(k for k in FIELDS if k in self.available),'op':'exists','value':True})
        frame=QWidget();row=QHBoxLayout(frame);row.setContentsMargins(0,0,0,0);row.setSpacing(8)
        if any(k in value for k in ('all','any','not')):
            editor=ConditionEditor(self.available,value,self,self.depth+1);row.addWidget(editor,1);editor.changed.connect(self.changed)
            getter=editor.value
        else:
            field=combo([(k,text) for k,(text,_) in FIELDS.items() if k in self.available or k==value['field']],value['field']);field.setAccessibleName(tr('Bedingungsfeld'));row.addWidget(field,2)
            op=QComboBox();op.setAccessibleName(tr('Vergleich'));row.addWidget(op,2)
            text=QLineEdit();text.setMaxLength(2000);text.setAccessibleName(tr('Vergleichswert'));row.addWidget(text,2)
            number=QDoubleSpinBox();number.setRange(-1e12,1e12);number.setDecimals(4);number.setAccessibleName(tr('Zahlenwert'));row.addWidget(number,2)
            boolean=combo([(True,'Ja'),(False,'Nein')],True);boolean.setAccessibleName(tr('Ja oder Nein'));row.addWidget(boolean)
            def operator_fields(*_):
                kind='boolean' if op.currentData()=='exists' else FIELDS[field.currentData()][1]
                text.setVisible(kind=='text');number.setVisible(kind=='number');boolean.setVisible(kind=='boolean');self.changed.emit()
            def field_changed(*_):
                old=op.currentData();op.blockSignals(True);op.clear()
                for key in OPERATORS[FIELDS[field.currentData()][1]]:op.addItem(tr(OP_LABELS[key]),key)
                op.setCurrentIndex(max(0,op.findData(old)));op.blockSignals(False);operator_fields()
            field.currentIndexChanged.connect(field_changed);op.currentIndexChanged.connect(operator_fields);field_changed()
            op.setCurrentIndex(op.findData(value['op']))
            if type(value['value']) is bool:boolean.setCurrentIndex(boolean.findData(value['value']))
            elif type(value['value']) in (int,float):number.setValue(value['value'])
            else:text.setText(value['value'])
            text.textChanged.connect(self.changed);number.valueChanged.connect(self.changed);boolean.currentIndexChanged.connect(self.changed)
            def getter():
                kind='boolean' if op.currentData()=='exists' else FIELDS[field.currentData()][1]
                return {'field':field.currentData(),'op':op.currentData(),'value':text.text() if kind=='text' else (value['value'] if type(value['value']) in (int,float) and number.value()==value['value'] else number.value()) if kind=='number' else boolean.currentData()}
            operator_fields()
        remove=button('×',lambda:self.remove(frame));remove.setAccessibleName(tr('Bedingung entfernen'));row.addWidget(remove)
        self.box.insertWidget(self.box.count()-1 if hasattr(self,'group_button') else self.box.count(),frame);self.rows.append((frame,getter));self.changed.emit()

    def remove(self,frame):
        self.rows=[c for c in self.rows if c[0] is not frame];self.box.removeWidget(frame);frame.deleteLater();self.changed.emit()

    def add_group(self):
        if self.depth<3:self.add({'any':[{'field':next(k for k in FIELDS if k in self.available),'op':'exists','value':True}]})

    def resizeEvent(self,event):
        super().resizeEvent(event)
        for frame,_ in self.rows:frame.layout().setDirection(QHBoxLayout.TopToBottom if self.width()<620 else QHBoxLayout.LeftToRight)

    def value(self):
        rows=[get() for _,get in self.rows]
        result=rows[0] if self.original_group is None and len(rows)==1 and self.mode.currentData()=='all' else {self.mode.currentData():rows}
        if self.negate.isChecked():result={'not':result}
        return validate(result,self.available)
