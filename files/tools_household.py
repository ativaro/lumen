"""Local devices, contracts, deadlines and receipts."""
from lumen_i18n import tr
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
    for key, title in [('remind',tr('Erinnerung / Kündigungsfrist')),('until',tr('Garantie / Vertragsende'))]:
        if record.get(key):
            value=date.fromisoformat(record[key]); days=(value-today).days
            suffix = tr('seit {0} Tagen überschritten' , -days) if days<0 else tr('heute') if days==0 else tr('in {0} Tagen' , days)
            lines.append(f'{title}: {value.strftime("%d.%m.%Y")} · {suffix}')
    return '\n'.join(lines) or tr('Noch keine Fristen hinterlegt.')


class Household(ToolWindow):
    def __init__(self, root=None):
        super().__init__('household',tr('Lumen Digitaler Haushalt'),tr('Geräte, Verträge und Belege an einem Ort.'),'go-home',root)
        self.add_button.setText(tr('Gerät / Vertrag hinzufügen')); self.search.setPlaceholderText(tr('Name, Modell oder Belegtext …'))
        self.title=QLineEdit(); self.title.setPlaceholderText(tr('Ein Gerät oder einen Vertrag hinzufügen')); self.title.setAccessibleName(tr('Name'))
        self.title.textEdited.connect(self.edited); self.content.addWidget(self.title)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        panel=QWidget(); body=QVBoxLayout(panel); body.setContentsMargins(0,0,8,0); body.setSpacing(12)
        scroll.setWidget(panel); self.content.addWidget(scroll,1)
        form=QFormLayout(); form.setRowWrapPolicy(QFormLayout.WrapLongRows); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); body.addLayout(form)
        self.kind=QComboBox(); self.kind.addItem(tr('Gerät'),'Gerät'); self.kind.addItem(tr('Vertrag'),'Vertrag'); self.kind.currentIndexChanged.connect(self.edited); form.addRow(tr('Art'),self.kind)
        self.fields={}
        for key,title in [('provider',tr('Hersteller / Anbieter')),('model',tr('Modell / Vertragsnummer')),('serial',tr('Seriennummer / Kundennummer'))]:
            field=QLineEdit(); field.setAccessibleName(title); field.textEdited.connect(self.edited); form.addRow(title,field); self.fields[key]=field
        self.dates={}
        for key,title in [('since',tr('Kauf / Beginn')),('until',tr('Garantie / Vertragsende')),('remind',tr('Erinnerung / Kündigungsfrist'))]:
            field=QDateEdit(); field.setCalendarPopup(True); field.setDisplayFormat('dd.MM.yyyy'); field.setMinimumDate(QDate(1900,1,1)); field.setSpecialValueText(tr('Nicht gesetzt')); field.setDate(field.minimumDate())
            field.setAccessibleName(title); field.dateChanged.connect(self.edited); self.dates[key]=field
            form.addRow(title,row(field,button(tr('Leeren'),lambda _checked=False,f=field:f.setDate(f.minimumDate()),'edit-clear')))
        self.due=label(tr('Noch keine Fristen hinterlegt.')); self.due.setObjectName('muted'); body.addWidget(self.due)
        body.addWidget(label(tr('Fristen werden hier angezeigt; es werden keine automatischen Benachrichtigungen versendet.'), 'muted'))
        self.notes=QPlainTextEdit(); self.notes.setPlaceholderText(tr('Notizen, Ansprechpartner, Zubehör …')); self.notes.setAccessibleName(tr('Notizen')); self.notes.setMinimumHeight(100)
        self.notes.textChanged.connect(self.edited); body.addWidget(self.notes)
        body.addWidget(label(tr('Belege & Handbücher'),'heading'))
        self.attachments=QListWidget(); self.attachments.setObjectName('searchResults'); self.attachments.setMinimumHeight(160)
        self.attachments.itemDoubleClicked.connect(lambda _:self.safe(self.open_attachment)); body.addWidget(self.attachments)
        body.addWidget(row(button(tr('Beleg hinzufügen'),lambda:self.safe(self.attach),'document-import',True),
            button(tr('Öffnen'),lambda:self.safe(self.open_attachment),'document-open'),button(tr('Entfernen'),lambda:self.safe(self.remove_attachment),'list-remove')))
        self.content.addWidget(button(tr('Übersicht exportieren'),lambda:self.safe(self.export),'document-export'))
        self.body.setEnabled(False); self.refresh()

    def create(self):
        title,ok=QInputDialog.getText(self,tr('Neuer Eintrag'),tr('Name des Geräts oder Vertrags'))
        if ok and title.strip():
            self.save(); self.focus_record(self.library.create(title,kind='Gerät',attachments=[],notes=''))

    def load(self,r):
        self.title.setText(r['title']); self.kind.setCurrentIndex(max(0,self.kind.findData(r.get('kind','Gerät'))))
        for key,field in self.fields.items(): field.setText(r.get(key,''))
        for key,field in self.dates.items(): field.setDate(QDate.fromString(r[key],'yyyy-MM-dd') if r.get(key) else field.minimumDate())
        self.notes.setPlainText(r.get('notes','')); self.due.setText(deadlines(r)); self.attachments.clear()
        for item in r.get('attachments',[]):
            suffix=tr('Text durchsuchbar') if item.get('text') else item.get('error',tr('Datei gespeichert'))
            widget=QListWidgetItem(item['name']+'\n'+suffix); widget.setData(Qt.UserRole,item); self.attachments.addItem(widget)
        self.status.setText(tr('Belege bleiben lokal · Änderungen werden automatisch gespeichert'))

    def save(self):
        super().save()
        if not self.current or self.loading: return
        values={key:field.text() for key,field in self.fields.items()}
        values.update({key:field.date().toString('yyyy-MM-dd') if field.date()>field.minimumDate() else '' for key,field in self.dates.items()})
        self.library.update(self.current,title=self.title.text(),kind=self.kind.currentData(),notes=self.notes.toPlainText(),**values)
        self.due.setText(deadlines(values)); self.status.setText(tr('Lokal gespeichert')); self.refresh()

    def attach(self):
        path,_=QFileDialog.getOpenFileName(self,tr('Beleg oder Handbuch hinzufügen'),str(Path.home()),tr('Dokumente (*.pdf *.txt *.md *.png *.jpg *.jpeg *.webp);;Alle Dateien (*)'))
        if not path: return
        key=self.current
        def run(job):
            asset=self.library.import_file(path,job,limit=128*1024**2)
            try:
                try: asset['text']=document_text(self.library.asset(asset['asset']),job)
                except Cancelled: raise
                except Exception as error: asset['error']=tr('Ohne Textindex: ')+str(error)[:180]
                job.check()
                r=self.library.get(key); self.library.update(key,attachments=r.get('attachments',[])+[asset]); return key
            except BaseException: self.library.asset(asset['asset']).unlink(missing_ok=True); raise
        self.work(tr('Beleg wird kopiert und lokal lesbar gemacht …'),run,self.focus_record)

    def open_attachment(self):
        item=self.attachments.currentItem()
        if item: open_path(self.library.asset(item.data(Qt.UserRole)['asset']))

    def remove_attachment(self):
        item=self.attachments.currentItem()
        if not item: return
        asset=item.data(Qt.UserRole)
        if QMessageBox.question(self,tr('Beleg entfernen'),tr('Die importierte Kopie entfernen? Die ursprüngliche Datei bleibt erhalten.'))!=QMessageBox.Yes: return
        self.save(); r=self.library.get(self.current)
        self.library.update(self.current,attachments=[a for a in r['attachments'] if a['asset']!=asset['asset']])
        self.library.asset(asset['asset']).unlink(missing_ok=True); self.focus_record(self.current)

    def export(self):
        self.save(); r=self.library.get(self.current)
        text='# '+r['title']+'\n\n'+{'Gerät':tr('Gerät'),'Vertrag':tr('Vertrag')}.get(r.get('kind'),r.get('kind',''))+'\n\n'
        text+='\n'.join(f'{key}: {r.get(key,"")}' for key in self.fields)+'\n\n'+deadlines(r)+'\n\n'+r.get('notes','')
        text+=tr('\n\n## Belege\n\n')+'\n'.join('- '+a['name'] for a in r.get('attachments',[]))
        self.export_text(text,'haushalt.md')
