"""State and user gestures for the shared native result components."""
import csv
import io
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl
from PySide6.QtGui import QGuiApplication, QDesktopServices
from lumen_i18n import tr
from rich_result import validate, from_messages


class RichController(QObject):
    changed=Signal(); valuesChanged=Signal(); tablesChanged=Signal(); stateChanged=Signal()
    submitted=Signal(str,object); failed=Signal(str)

    def __init__(self, backend, parent=None, file_results=False):
        super().__init__(parent); self.file_results=file_results; self.backend=backend; self.payload=None; self._values={}; self.tables={}; self.sent=False; self.revision=0
        backend.rich_results_enabled=True
        backend.messagesChanged.connect(self.update_messages)
        backend.busyChanged.connect(lambda _:self.stateChanged.emit())

    blocks=Property('QVariantList',lambda s:s.payload['blocks'] if s.payload else [],notify=changed)
    title=Property(str,lambda s:s.payload['title'] if s.payload else '',notify=changed)
    submitLabel=Property(str,lambda s:s.payload['submit_label'] if s.payload else '',notify=changed)
    values=Property('QVariantMap',lambda s:s._values,notify=valuesChanged)
    active=Property(bool,lambda s:bool(s.payload and s.payload['blocks']),notify=changed)
    editable=Property(bool,lambda s:not s.sent,notify=stateChanged)
    canSubmit=Property(bool,lambda s:bool(s.payload and s.payload['submit_label'] and not s.sent and not s.backend.busy),notify=stateChanged)
    tableRevision=Property(int,lambda s:s.revision,notify=tablesChanged)

    @Slot(str,result=str)
    def text(self,value):return tr(value)

    def update_messages(self,messages):self.set_result(from_messages(messages,self.file_results))

    def set_result(self,result):
        if result==self.payload:return
        self.payload=result;self._values={};self.tables={};self.sent=False
        for b in self.blocks:
            if b['type'] in ('slider','select','toggle'):self._values[b['id']]=b['value']
            if b['type']=='table':self.tables[b['id']]=dict(query='',column=-1,descending=False,selected=[])
        self.changed.emit();self.valuesChanged.emit();self.refresh_tables();self.stateChanged.emit()

    def block(self,key):return next((b for b in self.blocks if b['id']==key),None)

    @Slot(str,'QVariant',result=bool)
    def set_value(self,key,value):
        block=self.block(key)
        if not block or self.sent:return False
        kind=block['type']
        if kind=='slider':
            if type(value) not in (int,float) or not float(value).is_integer():return False
            value=int(value)
            if not block['min']<=value<=block['max']:return False
            value=min(block['max'],block['min']+round((value-block['min'])/block['step'])*block['step'])
        elif kind=='select':
            if not isinstance(value,str) or value not in block['options']:return False
        elif kind=='toggle':
            if type(value) is not bool:return False
        else:return False
        self._values[key]=value;self.valuesChanged.emit();return True

    def refresh_tables(self):self.revision+=1;self.tablesChanged.emit()

    @Slot(str,str)
    def filter_table(self,key,query):
        if key in self.tables:self.tables[key]['query']=query[:200];self.refresh_tables()

    @Slot(str,int)
    def sort_table(self,key,column):
        block=self.block(key)
        if key not in self.tables or not 0<=column<len(block['columns']):return
        state=self.tables[key];state['descending']=not state['descending'] if state['column']==column else False
        state['column']=column;self.refresh_tables()

    @Slot(str,int,result='QVariantList')
    def table_rows(self,key,_revision=0):
        block=self.block(key);state=self.tables.get(key)
        if not block or state is None:return []
        rows=[dict(index=i,cells=row,selected=i in state['selected']) for i,row in enumerate(block['rows'])
              if state['query'].casefold() in ' '.join(map(str,row)).casefold()]
        column=state['column']
        if column>=0:
            def key_of(row):
                v=row['cells'][column];return (0,v) if type(v) in (int,float) else (1,str(v).casefold())
            rows.sort(key=key_of,reverse=state['descending'])
        return rows

    @Slot(str,int)
    def select_row(self,key,index):
        block=self.block(key);state=self.tables.get(key)
        if state is None or self.sent or not 0<=index<len(block['rows']):return
        rows=state['selected'];rows.remove(index) if index in rows else rows.append(index);self.refresh_tables()

    @staticmethod
    def safe_cell(value):
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r','\n')):return "'"+value
        return value

    def table_text(self,key,delimiter):
        block=self.block(key)
        if not block or block['type']!='table':return ''
        rows=self.table_rows(key);selected=self.tables[key]['selected']
        if selected:rows=[r for r in rows if r['index'] in selected]
        output=io.StringIO();writer=csv.writer(output,delimiter=delimiter)
        writer.writerow([self.safe_cell(v) for v in block['columns']])
        writer.writerows([[self.safe_cell(v) for v in row['cells']] for row in rows])
        return output.getvalue()

    @Slot(str)
    def copy_table(self,key):QGuiApplication.clipboard().setText(self.table_text(key,'\t'))

    @Slot(str,str)
    def export_table(self,key,url):
        try:
            target=QUrl(url)
            if not target.isLocalFile():raise ValueError(tr('Bitte eine lokale Zieldatei auswählen.'))
            with Path(target.toLocalFile()).open('x',encoding='utf-8',newline='') as f:f.write(self.table_text(key,','))
        except (OSError,ValueError) as e:self.failed.emit(str(e))

    @Slot(str,int)
    def open_file(self,key,index):
        block=self.block(key)
        if block and block['type']=='files' and 0<=index<len(block['paths']):
            # Deliberate user click only; no model-defined command, URL or auto-open.
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(block['paths'][index])):self.failed.emit(tr('Datei konnte nicht geöffnet werden.'))

    @Slot()
    def submit(self):
        if not self.canSubmit:return
        data=dict(view_id=self.payload['id'],title=self.title,action=self.submitLabel,values=self._values,
                  tables={key:[self.block(key)['rows'][i] for i in state['selected']] for key,state in self.tables.items()})
        self.sent=True;self.stateChanged.emit()
        summary=[tr('Meine Auswahl · ')+self.submitLabel]
        for block in self.blocks:
            if block['id'] in self._values:
                value=self._values[block['id']]
                if type(value) is bool:value=tr('Ja') if value else tr('Nein')
                summary.append(block['label']+': '+str(value)+(' '+block['unit'] if block.get('unit') else ''))
        self.submitted.emit('\n'.join(summary),data)

    def recovery_state(self):return dict(payload=self.payload,values=self._values,tables=self.tables,sent=self.sent)

    def restore(self,state):
        if not isinstance(state,dict):return
        try:result=validate(state.get('payload'))
        except (ValueError,TypeError):return
        self.set_result(result)
        values=state.get('values',{})
        if isinstance(values,dict):
            for key,value in values.items():self.set_value(key,value)
        tables=state.get('tables',{})
        if isinstance(tables,dict):
            for key,row in tables.items():
                if key not in self.tables or not isinstance(row,dict):continue
                if isinstance(row.get('query'),str):self.filter_table(key,row['query'])
                column=row.get('column')
                if type(column) is int and 0<=column<len(self.block(key)['columns']):
                    self.tables[key]['column']=column;self.tables[key]['descending']=row.get('descending') is True
                selected=row.get('selected',[])
                if isinstance(selected,list):
                    for i in dict.fromkeys(i for i in selected if type(i) is int):self.select_row(key,i)
        self.sent=state.get('sent') is True;self.refresh_tables();self.stateChanged.emit()
