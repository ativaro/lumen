"""Local devices, contracts, deadlines and receipts."""
from datetime import date
from pathlib import Path
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (QLineEdit, QComboBox, QDateEdit, QFormLayout, QPlainTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog, QScrollArea, QWidget,
    QVBoxLayout, QMessageBox)
from tools_data import document_text, Cancelled
from tools_ui import ToolWindow, button, label, row, open_path


def deadlines(record, today=None):
    today = today or date.today(); lines=[]
    for key, title in [('remind','Erinnerung / Kündigungsfrist'),('until','Garantie / Vertragsende')]:
        if record.get(key):
            value=date.fromisoformat(record[key]); days=(value-today).days
            suffix = f'seit {-days} Tagen überschritten' if days<0 else 'heute' if days==0 else f'in {days} Tagen'
            lines.append(f'{title}: {value.strftime("%d.%m.%Y")} · {suffix}')
    return '\n'.join(lines) or 'Noch keine Fristen hinterlegt.'


class Household(ToolWindow):
    def __init__(self, root=None):
        super().__init__('household','Digitaler Haushalt','Geräte, Verträge und Belege an einem Ort.','go-home',root)
        self.add_button.setText('Gerät / Vertrag hinzufügen'); self.search.setPlaceholderText('Name, Modell oder Belegtext …')
        self.title=QLineEdit(); self.title.setPlaceholderText('Ein Gerät oder einen Vertrag hinzufügen'); self.title.setAccessibleName('Name')
        self.title.textEdited.connect(self.edited); self.content.addWidget(self.title)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        panel=QWidget(); body=QVBoxLayout(panel); body.setContentsMargins(0,0,8,0); body.setSpacing(12)
        scroll.setWidget(panel); self.content.addWidget(scroll,1)
        form=QFormLayout(); form.setRowWrapPolicy(QFormLayout.WrapLongRows); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); body.addLayout(form)
        self.kind=QComboBox(); self.kind.addItems(['Gerät','Vertrag']); self.kind.currentIndexChanged.connect(self.edited); form.addRow('Art',self.kind)
        self.fields={}
        for key,title in [('provider','Hersteller / Anbieter'),('model','Modell / Vertragsnummer'),('serial','Seriennummer / Kundennummer')]:
            field=QLineEdit(); field.setAccessibleName(title); field.textEdited.connect(self.edited); form.addRow(title,field); self.fields[key]=field
        self.dates={}
        for key,title in [('since','Kauf / Beginn'),('until','Garantie / Vertragsende'),('remind','Erinnerung / Kündigungsfrist')]:
            field=QDateEdit(); field.setCalendarPopup(True); field.setDisplayFormat('dd.MM.yyyy'); field.setMinimumDate(QDate(1900,1,1)); field.setSpecialValueText('Nicht gesetzt'); field.setDate(field.minimumDate())
            field.setAccessibleName(title); field.dateChanged.connect(self.edited); self.dates[key]=field
            form.addRow(title,row(field,button('Leeren',lambda _checked=False,f=field:f.setDate(f.minimumDate()),'edit-clear')))
        self.due=label('Noch keine Fristen hinterlegt.'); self.due.setObjectName('muted'); body.addWidget(self.due)
        body.addWidget(label('Fristen werden hier angezeigt; es werden keine automatischen Benachrichtigungen versendet.', 'muted'))
        self.notes=QPlainTextEdit(); self.notes.setPlaceholderText('Notizen, Ansprechpartner, Zubehör …'); self.notes.setAccessibleName('Notizen'); self.notes.setMinimumHeight(100)
        self.notes.textChanged.connect(self.edited); body.addWidget(self.notes)
        body.addWidget(label('Belege & Handbücher','heading'))
        self.attachments=QListWidget(); self.attachments.setObjectName('searchResults'); self.attachments.setMinimumHeight(160)
        self.attachments.itemDoubleClicked.connect(lambda _:self.safe(self.open_attachment)); body.addWidget(self.attachments)
        body.addWidget(row(button('Beleg hinzufügen',lambda:self.safe(self.attach),'document-import',True),
            button('Öffnen',lambda:self.safe(self.open_attachment),'document-open'),button('Entfernen',lambda:self.safe(self.remove_attachment),'list-remove')))
        self.content.addWidget(button('Übersicht exportieren',lambda:self.safe(self.export),'document-export'))
        self.body.setEnabled(False); self.refresh()

    def create(self):
        title,ok=QInputDialog.getText(self,'Neuer Eintrag','Name des Geräts oder Vertrags')
        if ok and title.strip():
            self.save(); self.focus_record(self.library.create(title,kind='Gerät',attachments=[],notes=''))

    def load(self,r):
        self.title.setText(r['title']); self.kind.setCurrentText(r.get('kind','Gerät'))
        for key,field in self.fields.items(): field.setText(r.get(key,''))
        for key,field in self.dates.items(): field.setDate(QDate.fromString(r[key],'yyyy-MM-dd') if r.get(key) else field.minimumDate())
        self.notes.setPlainText(r.get('notes','')); self.due.setText(deadlines(r)); self.attachments.clear()
        for item in r.get('attachments',[]):
            suffix='Text durchsuchbar' if item.get('text') else item.get('error','Datei gespeichert')
            widget=QListWidgetItem(item['name']+'\n'+suffix); widget.setData(Qt.UserRole,item); self.attachments.addItem(widget)
        self.status.setText('Belege bleiben lokal · Änderungen werden automatisch gespeichert')

    def save(self):
        super().save()
        if not self.current or self.loading: return
        values={key:field.text() for key,field in self.fields.items()}
        values.update({key:field.date().toString('yyyy-MM-dd') if field.date()>field.minimumDate() else '' for key,field in self.dates.items()})
        self.library.update(self.current,title=self.title.text(),kind=self.kind.currentText(),notes=self.notes.toPlainText(),**values)
        self.due.setText(deadlines(values)); self.status.setText('Lokal gespeichert'); self.refresh()

    def attach(self):
        path,_=QFileDialog.getOpenFileName(self,'Beleg oder Handbuch hinzufügen',str(Path.home()),'Dokumente (*.pdf *.txt *.md *.png *.jpg *.jpeg *.webp);;Alle Dateien (*)')
        if not path: return
        key=self.current
        def run(job):
            asset=self.library.import_file(path,job,limit=128*1024**2)
            try:
                try: asset['text']=document_text(self.library.asset(asset['asset']),job)
                except Cancelled: raise
                except Exception as error: asset['error']='Ohne Textindex: '+str(error)[:180]
                job.check()
                r=self.library.get(key); self.library.update(key,attachments=r.get('attachments',[])+[asset]); return key
            except BaseException: self.library.asset(asset['asset']).unlink(missing_ok=True); raise
        self.work('Beleg wird kopiert und lokal lesbar gemacht …',run,self.focus_record)

    def open_attachment(self):
        item=self.attachments.currentItem()
        if item: open_path(self.library.asset(item.data(Qt.UserRole)['asset']))

    def remove_attachment(self):
        item=self.attachments.currentItem()
        if not item: return
        asset=item.data(Qt.UserRole)
        if QMessageBox.question(self,'Beleg entfernen','Die importierte Kopie entfernen? Die ursprüngliche Datei bleibt erhalten.')!=QMessageBox.Yes: return
        self.save(); r=self.library.get(self.current)
        self.library.update(self.current,attachments=[a for a in r['attachments'] if a['asset']!=asset['asset']])
        self.library.asset(asset['asset']).unlink(missing_ok=True); self.focus_record(self.current)

    def export(self):
        self.save(); r=self.library.get(self.current)
        text='# '+r['title']+'\n\n'+r.get('kind','')+'\n\n'
        text+='\n'.join(f'{key}: {r.get(key,"")}' for key in self.fields)+'\n\n'+deadlines(r)+'\n\n'+r.get('notes','')
        text+='\n\n## Belege\n\n'+'\n'.join('- '+a['name'] for a in r.get('attachments',[]))
        self.export_text(text,'haushalt.md')
