"""Native text workbench: translate, rewrite, correct; PDF is an additional view."""
import base64
from pathlib import Path
import uuid
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QPlainTextEdit, QSplitter, QWidget,
    QVBoxLayout, QHBoxLayout, QTabWidget, QFileDialog, QScrollArea, QLabel, QSpinBox)
from tools_ui import ToolWindow, button, label, row
from desktop_design import PAGE_SPACING
from lumen_i18n import tr
from private_input import AssistantInput
import translate_data as data
import translate_pdf as pdf


class Translate(ToolWindow):
    def __init__(self, root=None):
        super().__init__('translate', 'Lumen Compose', tr('Übersetzen. Besser formulieren. Fehler korrigieren.'), 'lumen-translate', root)
        self.queue = []; self.translations = {}; self.batch_index = 0; self.request_options = {}
        self.add_button.setText(tr('Neuer Text')); self.search.setPlaceholderText(tr('Texte und Übersetzungen finden …'))
        self.mode = QComboBox(); self.mode.setAccessibleName(tr('Text bearbeiten'))
        for key, title in data.MODES.items(): self.mode.addItem(tr(title), key)
        self.source_language = QComboBox(); self.source_language.setAccessibleName(tr('Ausgangssprache')); self.source_language.addItem(tr('Automatisch erkennen'), 'auto')
        self.target_language = QComboBox(); self.target_language.setAccessibleName(tr('Zielsprache'))
        for key, title in data.LANGUAGES.items():
            self.source_language.addItem(tr(title), key); self.target_language.addItem(tr(title), key)
        self.style = QComboBox(); self.style.setAccessibleName(tr('Schreibstil'))
        for key, title in data.STYLES.items(): self.style.addItem(tr(title), key)
        self.mode.setCurrentIndex(max(0,self.mode.findData(self.settings.value('translateMode','translate'))))
        self.target_language.setCurrentIndex(max(0,self.target_language.findData(self.settings.value('translateTarget','de'))))
        self.style.setCurrentIndex(max(0,self.style.findData(self.settings.value('translateStyle','neutral'))))
        self.language_arrow=label('→')
        self.content.addWidget(row(self.mode, self.source_language, self.language_arrow, self.target_language, self.style))
        self.tabs = QTabWidget(); self.content.addWidget(self.tabs, 1)
        text_page = QWidget(); text_box = QVBoxLayout(text_page); text_box.setContentsMargins(0, 14, 0, 0)
        self.input = AssistantInput(); self.input.setPlaceholderText(tr('Text eingeben oder einfügen …')); self.input.setAccessibleName(tr('Originaltext'))
        self.output = QPlainTextEdit(); self.output.setReadOnly(True); self.output.setPlaceholderText(tr('Dein Ergebnis erscheint hier.')); self.output.setAccessibleName(tr('Bearbeiteter Text'))
        split = QSplitter();split.setObjectName('composeTextSplit');split.setHandleWidth(PAGE_SPACING)
        split.setStyleSheet('QSplitter#composeTextSplit::handle { background: transparent; }')
        for caption, editor in [(tr('Original'),self.input),(tr('Ergebnis'),self.output)]:
            pane=QWidget();box=QVBoxLayout(pane);box.setContentsMargins(0,0,0,0);box.addWidget(label(caption,'heading'));box.addWidget(editor);split.addWidget(pane)
        split.setSizes([420,420]);text_box.addWidget(split,1)
        self.swap_button=button(tr('Sprachen tauschen'),self.swap,'object-flip-horizontal')
        text_box.addWidget(row(button(tr('Einfügen'),self.paste,'edit-paste'),self.swap_button,
            button(tr('Ergebnis kopieren'),self.copy_result,'edit-copy'),button(tr('Als neuen Text verwenden'),self.use_result,'document-edit')))
        self.tabs.addTab(text_page,tr('Text'))
        document_page=QWidget();document_box=QVBoxLayout(document_page);document_box.setContentsMargins(0,14,0,0)
        self.document_info=label(tr('PDF mit Textschicht öffnen. Bilder und Seitenaufbau bleiben erhalten; Bildtext benötigt OCR.'),'muted')
        document_box.addWidget(self.document_info)
        self.page_number=QSpinBox();self.page_number.setMinimum(1);self.page_number.setAccessibleName(tr('Seite'))
        document_box.addWidget(row(button(tr('PDF öffnen …'),lambda:self.safe(self.choose_pdf),'document-open'),label(tr('Seite')),self.page_number,
                                  button(tr('PDF exportieren …'),lambda:self.safe(self.export_pdf),'document-export')))
        previews=QSplitter();self.pdf_original=self.preview_panel(previews,tr('Original'));self.pdf_result=self.preview_panel(previews,tr('Ergebnis'))
        document_box.addWidget(previews,1);self.tabs.addTab(document_page,'PDF')
        self.run_button=button(tr('Übersetzen'),lambda:self.safe(self.run_translation),'document-edit',True)
        self.count=label('','muted');self.content.addWidget(row(self.count,self.run_button))
        self.provider_note=label(tr('Nur mit dem Startbutton wird Inhalt an deinen eingerichteten KI-Anbieter gesendet. Entwürfe und Ergebnisse bleiben in deiner lokalen Bibliothek.'),'muted');self.content.addWidget(self.provider_note)
        for control in (self.mode,self.source_language,self.target_language,self.style):control.currentIndexChanged.connect(self.changed)
        self.input.textChanged.connect(self.changed);self.tabs.currentChanged.connect(self.update_controls)
        self.page_number.valueChanged.connect(lambda:self.safe(self.render_pages))
        for control in (self.progress,self.cancel_button):
            policy=control.sizePolicy();policy.setRetainSizeWhenHidden(True);control.setSizePolicy(policy)
        QShortcut(QKeySequence('Ctrl+Return'),self,activated=lambda:self.safe(self.run_translation))
        self.status.setWordWrap(False)
        self.refresh()
        records=self.library.all(False,'')
        if records:self.focus_record(records[0]['id'])
        else:self.create()
        self.update_controls()

    def preview_panel(self, split, caption):
        pane=QWidget();box=QVBoxLayout(pane);box.addWidget(label(caption,'heading'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setAlignment(Qt.AlignTop|Qt.AlignHCenter)
        view=QLabel(tr('Noch keine PDF'));view.setAlignment(Qt.AlignTop|Qt.AlignHCenter);scroll.setWidget(view);box.addWidget(scroll,1);split.addWidget(pane);return view

    def current_options(self):
        return data.options(self.source_language.currentData(),self.target_language.currentData(),self.style.currentData(),self.mode.currentData())

    def create(self):
        self.save();self.settings.sync()
        self.current=self.library.create(tr('Neuer Text'),source='',result='',options=dict(source='auto',target=self.settings.value('translateTarget','de'),style=self.settings.value('translateStyle','neutral'),mode=self.settings.value('translateMode','translate')))
        self.refresh();self.load(self.library.get(self.current));self.tabs.setCurrentIndex(0);self.input.setFocus()

    def load(self, record):
        self.loading=True
        try:
            self.input.setPlainText(record.get('source',''));self.output.setPlainText(record.get('result',''))
            values=record.get('options',{})
            for key,control in [('source',self.source_language),('target',self.target_language),('style',self.style),('mode',self.mode)]:
                if key in values:control.setCurrentIndex(max(0,control.findData(values[key])))
            self.document_info.setText((record.get('document_name','') + ' · ' + record.get('manifest',{}).get('notice','')) if record.get('document_name') else tr('PDF mit Textschicht öffnen. Bilder und Seitenaufbau bleiben erhalten; Bildtext benötigt OCR.'))
            self.page_number.setMaximum(record.get('manifest',{}).get('pages',1));self.page_number.setValue(1)
            self.pdf_original.clear();self.pdf_result.clear();self.tabs.setCurrentIndex(1 if record.get('document_asset') else 0)
        finally:self.loading=False
        self.update_controls()
        if record.get('document_asset'):QTimer.singleShot(0,lambda:self.safe(self.render_pages))

    def changed(self, *_):
        if self.loading:return
        self.output.clear()
        if self.current:self.library.update(self.current,result='',pdf_result='',pdf_report={})
        self.pdf_result.clear();self.edited();self.update_controls()

    def update_controls(self, *_):
        mode=self.mode.currentData()
        for control in (self.source_language,self.target_language,self.language_arrow,self.swap_button):control.setVisible(mode=='translate')
        self.style.setEnabled(mode!='correct');self.source_language.setEnabled(mode=='translate');self.target_language.setEnabled(mode=='translate')
        self.run_button.setText(tr(data.MODES[mode]));self.count.setText(tr('{0} / 12.000 Zeichen',len(self.input.toPlainText())))

    def save(self):
        super().save()
        if self.loading or not self.current:return
        text=self.input.toPlainText()
        record=self.library.get(self.current)
        title=record.get('document_name') or text.strip().split('\n',1)[0][:70] or tr('Neuer Text')
        self.library.update(self.current,title=title,source=text,options=dict(source=self.source_language.currentData(),target=self.target_language.currentData(),style=self.style.currentData(),mode=self.mode.currentData()))
        self.refresh()

    def paste(self):
        from clipboard_image import protected_clipboard
        if not protected_clipboard(QApplication.clipboard()):
            self.input.insertPlainText(QApplication.clipboard().text())
    def copy_result(self):
        if self.output.toPlainText():QApplication.clipboard().setText(self.output.toPlainText())
    def use_result(self):
        value=self.output.toPlainText()
        if value:self.create();self.input.setPlainText(value)
    def swap(self):
        source=self.source_language.currentData();target=self.target_language.currentData()
        if source=='auto':self.status.setText(tr('Zum Tauschen zuerst die Ausgangssprache wählen.'));return
        self.source_language.setCurrentIndex(self.source_language.findData(target));self.target_language.setCurrentIndex(self.target_language.findData(source))

    def open_text(self, text):
        data.text_segments(text)
        self.create(); self.input.setPlainText(text); self.save(); self.tabs.setCurrentIndex(0)

    def choose_pdf(self):
        path,_=QFileDialog.getOpenFileName(self,tr('PDF öffnen'),'', 'PDF (*.pdf)')
        if path:self.open_file(path)

    def open_file(self, path):
        self.save()
        def import_pdf(job):
            imported=self.library.import_file(path,job,limit=pdf.MAX_FILE)
            try:manifest=pdf.worker(job,'inspect',path=str(self.library.asset(imported['asset'])))
            except BaseException:self.library.asset(imported['asset']).unlink(missing_ok=True);raise
            return dict(imported,manifest=manifest)
        def done(value):
            self.current=self.library.create(value['name'],source='',result='',document_name=value['name'],document_asset=value['asset'],manifest=value['manifest'],options=dict(source='auto',target=self.target_language.currentData(),style=self.style.currentData(),mode='translate'))
            self.refresh();self.load(self.library.get(self.current))
        self.work(tr('PDF wird vorbereitet …'),import_pdf,done,finished=lambda:QTimer.singleShot(0,lambda:self.safe(self.render_pages)))

    def render_pages(self):
        if self.loading or self.job or (self.engine and self.engine.busy) or not self.current:return
        record=self.library.get(self.current)
        if not record.get('document_asset'):return
        page=self.page_number.value()-1
        def render(job):
            from reader_data import worker
            result=[]
            for name in (record['document_asset'],record.get('pdf_result','')):
                result.append(worker(job,'page',self.library.asset(name),page=page,scale=.8) if name else None)
            return result
        def done(values):
            for view,value in zip((self.pdf_original,self.pdf_result),values):
                if value:
                    pixmap=QPixmap();pixmap.loadFromData(base64.b64decode(value['png']));view.setPixmap(pixmap.scaledToWidth(max(220,view.parentWidget().width()-24),Qt.SmoothTransformation))
                else:view.setText(tr('Nach dem Übersetzen erscheint hier die Vorschau.'))
        self.work(tr('Seitenvorschau wird geladen …'),render,done)

    def run_translation(self):
        if self.job or (self.engine and self.engine.busy):return
        self.save();record=self.library.get(self.current);self.request_options=self.current_options()
        self.document_request=self.tabs.currentIndex()==1
        if self.document_request:
            if not record.get('manifest'):raise ValueError(tr('Bitte zuerst eine PDF öffnen.'))
            segments=record['manifest']['segments']
        else:segments=data.text_segments(self.input.toPlainText())
        self.request_segments=segments
        self.queue=data.batches(segments);self.batch_index=0;self.translations={};self.request_record=self.current
        if not self.engine:
            from assistant_backend import OpenCodeBackend
            self.engine=OpenCodeBackend(self.library.root,self,project_config=False);self.engine.completed.connect(self.batch_done)
        self.begin(tr('Text wird bearbeitet …'));self.next_batch()

    def next_batch(self):
        self.status.setText(tr('Abschnitt {0} von {1} wird bearbeitet …',self.batch_index+1,len(self.queue)))
        self.engine.send(data.prompt(self.queue[self.batch_index],self.request_options),proposal=True,title='Lumen Compose')

    def batch_done(self, success, answer):
        if not success:self.end();self.status.setText(answer or tr('Übersetzung abgebrochen.'));return
        try:self.translations.update(data.parse_result(answer,self.queue[self.batch_index]))
        except (ValueError,TypeError) as error:self.end();self.error(str(error));return
        self.batch_index+=1
        if self.batch_index<len(self.queue):self.next_batch();return
        text=data.joined(self.request_segments,self.translations)
        self.library.update(self.request_record,result=text);self.output.setPlainText(text);self.end()
        if self.document_request:
            record=self.library.get(self.request_record);name=uuid.uuid4().hex+'.pdf'
            manifest=dict(record['manifest'],path=str(self.library.asset(record['document_asset'])))
            def done(report):
                self.library.update(self.request_record,pdf_result=name,pdf_report=report)
                self.document_info.setText(tr('PDF fertig · {0} Textbereiche mit verkleinerter Schrift. Bitte die Vorschau prüfen.',len(report['reduced'])))
            self.work(tr('PDF-Layout wird aufgebaut …'),lambda job:pdf.worker(job,'write',manifest=manifest,translations=self.translations,output=str(self.library.asset(name))),done,
                      finished=lambda:QTimer.singleShot(0,lambda:self.safe(self.render_pages)))
        else:self.status.setText(tr('Fertig · Ergebnis prüfen und kopieren.'))

    def export_pdf(self):
        record=self.library.get(self.current)
        if not record.get('pdf_result'):raise ValueError(tr('Bitte die PDF zuerst vollständig übersetzen.'))
        path,_=QFileDialog.getSaveFileName(self,tr('Übersetzte PDF speichern'),str(Path.home()/((Path(record['document_name']).stem)+'-'+self.target_language.currentData()+'.pdf')),'PDF (*.pdf)')
        if not path:return
        def copy(job):
            from translate_pdf import export_copy
            return export_copy(self.library.asset(record['pdf_result']),path,job)
        self.work(tr('PDF wird exportiert …'),copy,lambda _:self.status.setText(tr('Neue PDF gespeichert. Das Original bleibt unverändert.')))
