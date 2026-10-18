"""A native reading desk with a static page canvas and accessible text alternative."""
from lumen_i18n import tr
import base64
from pathlib import Path
import uuid
from PySide6.QtCore import Qt, QTimer, QRectF, QEvent, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QKeySequence, QTextCursor, QTextCharFormat
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (QWidget, QScrollArea, QSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit,
    QSplitter, QVBoxLayout, QTabWidget, QListWidget, QListWidgetItem, QFileDialog, QInputDialog, QMessageBox,
    QStackedWidget)
from tools_ui import ToolWindow, AudioPlayer, button, label, row
from tools_data import synthesize
import reader_data as reader


class PageCanvas(QWidget):
    changed=Signal()
    def __init__(self):
        super().__init__();self.setFocusPolicy(Qt.StrongFocus);self.setAccessibleName(tr('Buchseite; für Tastaturauswahl die Textansicht wählen'))
        self.pixmap=QPixmap();self.words=[];self.marks=[];self.first=self.last=-1;self.zoom=1
        QShortcut(QKeySequence.Copy,self,activated=self.copy,context=Qt.WidgetShortcut)
        QShortcut(QKeySequence.SelectAll,self,activated=self.select_all,context=Qt.WidgetShortcut)

    def load(self,data,marks,zoom):
        self.pixmap.loadFromData(base64.b64decode(data['png']));self.words=data['words'];self.marks=marks
        self.page_width=data['width'];self.page_height=data['height'];self.first=self.last=-1;self.resize_page(zoom);self.changed.emit()

    def resize_page(self,zoom):
        self.zoom=zoom
        if not self.pixmap.isNull():self.setFixedSize(round(self.page_width*zoom),round(self.page_height*zoom))
        self.update()

    def selected(self):return list(range(min(self.first,self.last),max(self.first,self.last)+1)) if self.first>=0 and self.last>=0 else []
    def text(self):return ' '.join(self.words[i][4] for i in self.selected())
    def copy(self):
        from PySide6.QtWidgets import QApplication
        if self.text():QApplication.clipboard().setText(self.text())
    def select_all(self):self.first=0;self.last=len(self.words)-1;self.update();self.changed.emit()

    def hit(self,point):
        for i,word in enumerate(self.words):
            if QRectF(word[0]*self.zoom,word[1]*self.zoom,(word[2]-word[0])*self.zoom,(word[3]-word[1])*self.zoom).adjusted(-2,-2,2,2).contains(point):return i
        return -1

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.setFocus();self.first=self.last=self.hit(event.pos());self.update();self.changed.emit()
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.LeftButton:
            index=self.hit(event.pos())
            if index>=0:self.last=index;self.update();self.changed.emit()
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),Qt.white)
        if self.pixmap.isNull():return
        painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.drawPixmap(self.rect(),self.pixmap)
        for indices,color in [(m.get('words',[]),QColor(242,192,71,90)) for m in self.marks]+[(self.selected(),QColor(60,160,210,95))]:
            for i in indices:
                if 0<=i<len(self.words):
                    w=self.words[i];painter.fillRect(QRectF(w[0]*self.zoom,w[1]*self.zoom,(w[2]-w[0])*self.zoom,(w[3]-w[1])*self.zoom),color)


class Reader(ToolWindow):
    def __init__(self,root=None):
        super().__init__('reader',tr('Lumen Reader'),tr('Zeit zum Lesen. Deine Bücher, Gedanken und Fundstellen.'),'lumen-reader',root)
        self.add_button.setText(tr('Buch oder Dokument öffnen'));self.search.setPlaceholderText(tr('In meiner Bibliothek …'))
        self.sidebar.layout().insertWidget(2,button(tr('Artikel speichern'),lambda:self.safe(self.add_article),'internet-web-browser'))
        self.data=None;self.page_index=0;self.note_id='';self.passwords={};self.pending=[];self.restore_scroll=0;self.audio_asset='';self.pending_position={}
        self.title=label(tr('Deine nächste gute Lektüre'),'heading');self.content.addWidget(self.title)
        self.origin=label(tr('PDFs, EPUBs und Artikel hinzufügen. Lesestand und Gedanken bleiben lokal.'),'muted');self.content.addWidget(self.origin)
        self.page_number=QSpinBox();self.page_number.setRange(1,1);self.page_number.setAccessibleName(tr('Seite'));self.page_number.editingFinished.connect(lambda:self.goto(self.page_number.value()-1))
        self.page_count=label('');self.zoom=QComboBox();self.zoom.setAccessibleName(tr('Seitenvergrößerung'))
        for text,value in [(tr('Seitenbreite'),0),('75 %',.75),('100 %',1),('125 %',1.25),('150 %',1.5),('200 %',2)]:self.zoom.addItem(text,value)
        self.zoom.currentIndexChanged.connect(self.set_zoom)
        self.mode=QComboBox();self.mode.setAccessibleName(tr('Leseansicht'));self.mode.addItems([tr('Seitenansicht'),tr('Textansicht')]);self.mode.currentIndexChanged.connect(self.change_mode)
        self.content.addWidget(row(button(tr('Zurück'),lambda:self.goto(self.page_index-1),'go-previous'),self.page_number,self.page_count,
            button(tr('Weiter'),lambda:self.goto(self.page_index+1),'go-next'),self.zoom,self.mode))
        self.book_search=QLineEdit();self.book_search.setPlaceholderText(tr('Im Buch suchen …'));self.book_search.setAccessibleName(tr('Suchbegriff im Buch'));self.book_search.returnPressed.connect(lambda:self.safe(self.find))
        self.content.addWidget(row(self.book_search,button(tr('Suchen'),lambda:self.safe(self.find),'edit-find'),
            button(tr('Lesezeichen'),lambda:self.safe(self.mark,False),'bookmark-new'),button(tr('Markieren'),lambda:self.safe(self.mark,True),'draw-highlight')))
        self.read_split=QSplitter();self.content.addWidget(self.read_split,1)
        self.views=QStackedWidget();self.scroll=QScrollArea();self.scroll.setFrameShape(QScrollArea.NoFrame);self.scroll.setAlignment(Qt.AlignHCenter|Qt.AlignTop)
        self.canvas=PageCanvas();self.scroll.setWidget(self.canvas);self.views.addWidget(self.scroll)
        self.scroll.viewport().installEventFilter(self)
        self.text=QPlainTextEdit();self.text.setReadOnly(True);self.text.setAccessibleName(tr('Auswählbarer Seitentext'));font=self.text.font();font.setPointSize(13);self.text.setFont(font);self.views.addWidget(self.text);self.read_split.addWidget(self.views)
        for view in (self.canvas,self.text):
            QShortcut(QKeySequence('PgDown'),view,activated=lambda:self.goto(self.page_index+1),context=Qt.WidgetShortcut)
            QShortcut(QKeySequence('PgUp'),view,activated=lambda:self.goto(self.page_index-1),context=Qt.WidgetShortcut)
        self.rail=QWidget();rl=QVBoxLayout(self.rail);rl.setContentsMargins(12,0,0,0)
        self.tabs=QTabWidget();self.tabs.setStyleSheet('QTabBar::tab { min-width: 64px; padding: 8px 10px; }');rl.addWidget(self.tabs,1)
        self.notes=QListWidget();self.notes.setAccessibleName(tr('Markierungen und Lesezeichen'));self.notes.currentItemChanged.connect(self.select_note);self.tabs.addTab(self.notes,tr('Gedanken'))
        self.notes.setWordWrap(True);self.notes.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.toc=QListWidget();self.toc.setAccessibleName(tr('Inhaltsverzeichnis'));self.toc.itemActivated.connect(lambda item:self.goto(item.data(Qt.UserRole)));self.tabs.addTab(self.toc,tr('Inhalt'))
        self.hits=QListWidget();self.hits.setAccessibleName(tr('Treffer im Buch'));self.hits.itemActivated.connect(lambda item:self.goto(item.data(Qt.UserRole)));self.tabs.addTab(self.hits,tr('Suche'))
        self.quote=label(tr('Eine Stelle markieren oder ein Lesezeichen setzen.'),'muted');rl.addWidget(self.quote)
        self.note=QPlainTextEdit();self.note.setPlaceholderText(tr('Deine Randnotiz …'));self.note.setAccessibleName(tr('Randnotiz'));self.note.setMaximumHeight(160);self.note.setEnabled(False);self.note.textChanged.connect(self.edited);rl.addWidget(self.note)
        rl.addWidget(button(tr('Markierung entfernen'),lambda:self.safe(self.remove_note),'edit-delete'))
        rl.addWidget(button(tr('Als Notiz speichern …'),lambda:self.safe(self.remember),'document-save'))
        self.read_split.addWidget(self.rail);self.read_split.setSizes([720,280]);self.read_split.setStretchFactor(0,1)
        self.focus_button=button(tr('Lesemodus'),self.focus_mode,'view-fullscreen');self.focus_button.setCheckable(True)
        self._compact=False;self._compact_restore=None
        self.content.addWidget(row(button(tr('Vorlesen'),lambda:self.safe(self.speak),'audio-volume-high'),
            button(tr('Notizen exportieren'),lambda:self.safe(self.export_notes),'document-export'),
            self.focus_button))
        self.player=AudioPlayer();self.content.addWidget(self.player);self.player.hide()
        self.scroll.verticalScrollBar().valueChanged.connect(self.edited);self.text.verticalScrollBar().valueChanged.connect(self.edited)
        self.body.setEnabled(False);self.refresh()
        actions=self.menuBar().addMenu(tr('Dokument & Fundstellen'))
        self.document_menu=actions
        actions.addAction(tr('Original prüfen und Lesekopie aktualisieren'),lambda:self.safe(self.refresh_original))
        actions.addAction(tr('Text dieser Seite lokal erkennen'),lambda:self.safe(self.ocr_current))
        actions.addSeparator()
        actions.addAction(tr('Kapitelmarkierungen als Notiz speichern …'),lambda:self.safe(self.send_marks,True))
        actions.addAction(tr('Alle Markierungen als Notiz speichern …'),lambda:self.safe(self.send_marks,False))
        from interop_reader import send_book_marks
        actions.addAction(tr('Markierungen mehrerer Dokumente an Lumen Audio Studio · Radio'),lambda:self.safe(send_book_marks,self))
        self.body.installEventFilter(self)

    def create(self):
        path,_=QFileDialog.getOpenFileName(self,tr('Buch oder Dokument öffnen'),str(Path.home()),tr('Lesbare Dokumente (*.pdf *.epub *.txt *.md *.html *.htm)'))
        if path:self.open_file(path)

    def open_file(self,path):
        if len(self.pending)>=10:raise ValueError(tr('Bitte den laufenden Import abwarten.'))
        if self.job:self.pending.append(path);return
        self.work(tr('Private Lesekopie wird angelegt …'),lambda job:reader.import_file(self.library,path,job),self.open_imported)

    def open_imported(self,key):
        # Wait for the importer to release the shared job before rendering.
        self.current=key;QTimer.singleShot(0,lambda:self.focus_record(key))

    def job_finished(self):
        super().job_finished()
        if self.pending:
            path=self.pending.pop(0);QTimer.singleShot(0,lambda:self.safe(self.open_file,path))

    def add_article(self):
        value,ok=QInputDialog.getText(self,tr('Artikel speichern'),tr('Webadresse (Abruf ohne Anmeldung)'))
        if ok and value.strip():self.work(tr('Artikel wird als Lesekopie gespeichert …'),lambda job:reader.import_url(self.library,value,job),self.open_imported)

    def load(self,record):
        self.player.stop();self.clear_audio();self.data=None;self.note_id='';self.note.clear();self.note.setEnabled(False);self.hits.clear()
        self.title.setText(record['title']);self.origin.setText(record.get('source',''))
        self.page_index=record.get('page',0);self.restore_scroll=record.get('scroll',0)
        self.mode.blockSignals(True);self.mode.setCurrentIndex(record.get('view',0));self.mode.blockSignals(False);self.views.setCurrentIndex(self.mode.currentIndex())
        self.zoom.blockSignals(True);self.zoom.setCurrentIndex(max(0,self.zoom.findData(record.get('zoom',0))));self.zoom.blockSignals(False)
        self.refresh_notes();QTimer.singleShot(0,self.render_page)

    def goto(self,index):
        if self.job or not self.current:return
        if not 0<=index<self.library.get(self.current).get('pages',1):return
        self.safe(self.save);self.player.stop();self.clear_audio();self.page_index=index;self.restore_scroll=0;self.render_page()

    def focus_position(self,position):
        record=self.library.get(self.current);page=position.get('page',record.get('page',0));note=position.get('note','')
        if note:
            selected=next((n for n in record.get('notes',[]) if n['id']==note),None)
            if selected is None:raise ValueError(tr('Die verknüpfte Markierung ist nicht mehr vorhanden.'))
            page=selected['page']
        if not 0<=page<record.get('pages',1):raise ValueError(tr('Die verknüpfte Seite ist nicht mehr verfügbar.'))
        self.page_index=page;self.restore_scroll=0
        self.pending_position=dict(position)
        if note:self.refresh_notes(note);self.tabs.setCurrentIndex(0);self.rail.show()

    def render_page(self):
        if not self.current:return
        key=self.current;record=self.library.get(key);index=self.page_index
        self.data=None;self.canvas.pixmap=QPixmap();self.canvas.words=[];self.canvas.update();self.text.clear()
        def done(data):
            if data.get('locked'):
                self.status.setText(tr('Passwort für diese Lesesitzung erforderlich.'))
                QTimer.singleShot(0,lambda:self.unlock(key));return
            self.loading=True
            try:
                self.data=data;self.page_index=data['page']
                updates=dict(pages=data['pages'],toc=data['toc'],locked=False,engine=reader.ENGINE)
                if 'notes' in data:
                    if self.library.get(key).get('notes',[])!=record.get('notes',[]):raise ValueError(tr('Notizen wurden inzwischen geändert. Bitte erneut öffnen.'))
                    updates.update(notes=data['notes'],legacy_page=record.get('page',0),position_changed=data.get('position_changed',False))
                    if data.get('position_changed'):updates.update(legacy_ocr_text=record.get('ocr_text',{}),ocr_text={})
                    self.restore_scroll=0
                self.library.update(key,**updates);self.refresh_notes()
                self.page_number.setRange(1,data['pages']);self.page_number.setValue(self.page_index+1);self.page_count.setText(tr('von ')+str(data['pages']))
                marks=[n for n in self.library.get(key).get('notes',[]) if n['page']==self.page_index and n.get('anchor_status')!='unresolved']
                self.canvas.load(data,marks,self.effective_zoom())
                ocr=self.library.get(key).get('ocr_text',{}).get(str(self.page_index))
                if ocr:data['text']=ocr
                self.text.setPlainText(data['text']);self.highlight_text(marks)
                self.toc.clear()
                for level,title,page in data['toc']:
                    item=QListWidgetItem('  '*(min(level,8)-1)+title);item.setData(Qt.UserRole,max(0,page-1));self.toc.addItem(item)
                self.status.setText(tr('Seite ')+str(self.page_index+1)+' · '+(tr('Text auswählen, um zu markieren oder vorzulesen') if data['text'].strip() else tr('Bildseite ohne Textschicht')))
            finally:self.loading=False
            if self.library.get(key).get('position_changed') or any(n.get('anchor_status')=='unresolved' for n in self.library.get(key).get('notes',[])):
                self.status.setText(tr('Neuer Textumbruch: bisherige Stellen bitte prüfen. Nicht eindeutig zugeordnete Notizen bleiben erhalten.'))
            position=self.pending_position;self.pending_position={}
            if ('start' in position or position.get('part','').startswith('words:')) and position.get('engine')!=reader.ENGINE:
                self.status.setText(tr('Älterer Stellenverweis: Die Seite ist geöffnet; die genaue Textstelle bitte neu auswählen.'));position={}
            if 'start' in position:
                from interop_open import focus_text
                self.mode.setCurrentIndex(1);self.safe(focus_text,self.text,position)
            elif position.get('part','').startswith('words:'):
                from interop_open import _index
                parts=position['part'].split(':')
                if len(parts)==3:
                    try:self.canvas.first=_index(parts[1],len(self.canvas.words));self.canvas.last=_index(parts[2],len(self.canvas.words));self.canvas.update()
                    except ValueError as error:self.error(str(error))
            value=self.restore_scroll;QTimer.singleShot(0,lambda:self.restore_position(value));self.restore_scroll=0
        self.work(tr('Seite wird geladen …'),lambda job:reader.worker(job,'page',self.library.asset(record['asset']),page=index,password=self.passwords.get(key,''),stamp=record['stamp'],legacy=record.get('engine')!=reader.ENGINE,notes=record.get('notes',[])),done)

    def restore_position(self,value):
        self.loading=True
        try:
            view=self.scroll if self.mode.currentIndex()==0 else self.text;view.verticalScrollBar().setValue(value)
        finally:self.loading=False
        self.save()

    def unlock(self,key):
        password,ok=QInputDialog.getText(self,tr('Geschütztes PDF'),tr('Passwort (nur für diese Sitzung)'),QLineEdit.Password)
        if ok:self.passwords[key]=password;self.render_page()

    def set_zoom(self):
        self.canvas.resize_page(self.effective_zoom());self.edited()

    def effective_zoom(self):
        return self.zoom.currentData() or max(.15,min(2,(self.scroll.viewport().width()-16)/(self.data['width'] if self.data else 600)))

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Resize and hasattr(self,'canvas') and self.zoom.currentData()==0:self.canvas.resize_page(self.effective_zoom())
        if obj is self.body and event.type()==QEvent.EnabledChange:self.update_reading_layout()
        return super().eventFilter(obj,event)

    def change_mode(self,index):self.views.setCurrentIndex(index);self.edited()
    def focus_mode(self):
        self._compact_restore=None
        focused=not self.rail.isHidden();self.sidebar.setVisible(not focused);self.rail.setVisible(not focused);self.reading_mode_status()

    def reading_mode_status(self):
        focused=self.sidebar.isHidden() and self.rail.isHidden()
        text=tr('Bibliothek und Gedanken anzeigen' if focused else 'Lesemodus')
        self.focus_button.setText(text);self.focus_button.setAccessibleName(text);self.focus_button.setChecked(focused)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_reading_layout()

    def update_reading_layout(self):
        if not hasattr(self,'focus_button') or not self.isWindow():return
        compact=self.width()<1000 and self.body.isEnabled()
        if compact==self._compact:return
        self._compact=compact
        if compact:
            self._compact_restore=(not self.sidebar.isHidden(),not self.rail.isHidden())
            self.sidebar.hide();self.rail.hide();self.reading_mode_status()
        elif self._compact_restore is not None:
            sidebar,rail=self._compact_restore;self._compact_restore=None
            self.sidebar.setVisible(sidebar);self.rail.setVisible(rail);self.reading_mode_status()

    def save(self):
        super().save()
        if not self.current or self.loading or not self.data:return
        record=self.library.get(self.current);notes=record.get('notes',[])
        for note in notes:
            if note['id']==self.note_id:note['note']=self.note.toPlainText()[:20000]
        view=self.scroll if self.mode.currentIndex()==0 else self.text
        self.library.update(self.current,page=self.page_index,scroll=view.verticalScrollBar().value(),zoom=self.zoom.currentData(),view=self.mode.currentIndex(),notes=notes)
        if not self.job:self.status.setText(tr('Lesestand und Notizen lokal gespeichert.'))

    def selection(self):
        if self.mode.currentIndex()==0:return self.canvas.text(),self.canvas.selected(),[]
        cursor=self.text.textCursor();return cursor.selectedText().replace('\u2029','\n'),[],[cursor.selectionStart(),cursor.selectionEnd()] if cursor.hasSelection() else []

    def mark(self,selected=True):
        if not self.data:raise ValueError(tr('Zuerst eine lesbare Seite öffnen.'))
        self.save();text,words,selection=self.selection() if selected else ('',[],[])
        if selected and not text.strip():raise ValueError(tr('Zuerst Text auf der Seite oder in der Textansicht auswählen.'))
        note=reader.add_note(self.library,self.current,self.page_index,text,words,selection);self.refresh_notes(note['id'])
        self.canvas.marks=[n for n in self.library.get(self.current)['notes'] if n['page']==self.page_index];self.canvas.update();self.highlight_text(self.canvas.marks)

    def refresh_notes(self,selected=''):
        self.notes.blockSignals(True);self.notes.clear();current=None
        for note in self.library.get(self.current).get('notes',[]):
            item=QListWidgetItem(tr('S. ')+str(note['page']+1)+' · '+((tr('Zuordnung prüfen · ') if note.get('anchor_status')=='unresolved' else '')+(note['text'] or tr('Lesezeichen')))[:90]);item.setData(Qt.UserRole,note);self.notes.addItem(item)
            if note['id']==(selected or self.note_id):current=item
        self.notes.setCurrentItem(current);self.notes.blockSignals(False)
        if selected and current:self.select_note(current,None)

    def select_note(self,item,old):
        self.safe(self.save);self.loading=True
        try:
            self.note_id='';self.note.clear();self.note.setEnabled(bool(item))
            if item:
                note=next(n for n in self.library.get(self.current)['notes'] if n['id']==item.data(Qt.UserRole)['id'])
                self.note_id=note['id'];self.quote.setText(note['text'][:400] or tr('Lesezeichen'));self.note.setPlainText(note['note'])
            else:self.quote.setText(tr('Eine Stelle markieren oder ein Lesezeichen setzen.'))
        finally:self.loading=False
        if item and note['page']!=self.page_index:self.goto(note['page'])

    def remove_note(self):
        if not self.note_id:return
        self.save();record=self.library.get(self.current);self.library.update(self.current,notes=[n for n in record['notes'] if n['id']!=self.note_id]);self.note_id='';self.note.clear();self.note.setEnabled(False);self.refresh_notes();self.render_page()

    def highlight_text(self,marks):
        selections=[]
        for mark in marks:
            positions=mark.get('selection',[])
            if len(positions)==2 and 0<=positions[0]<positions[1]<self.text.document().characterCount():
                selection=QTextEdit.ExtraSelection();selection.cursor=QTextCursor(self.text.document());selection.cursor.setPosition(positions[0]);selection.cursor.setPosition(positions[1],QTextCursor.KeepAnchor);selection.format.setBackground(QColor(242,192,71,90));selections.append(selection)
        self.text.setExtraSelections(selections)

    def find(self):
        if not self.current:return
        if not self.data:raise ValueError(tr('Das Buch zuerst öffnen beziehungsweise entsperren.'))
        record=self.library.get(self.current);key=self.current;query=self.book_search.text()
        def done(hits):
            from interop_reader import search_ocr
            by_page={hit['page']:hit for hit in hits}
            by_page.update({hit['page']:hit for hit in search_ocr(record,query)})
            hits=[by_page[page] for page in sorted(by_page)][:100]
            self.hits.clear()
            for hit in hits:
                item=QListWidgetItem(tr('S. ')+str(hit['page']+1)+' · '+hit['text']);item.setData(Qt.UserRole,hit['page']);self.hits.addItem(item)
            self.tabs.setCurrentIndex(2);self.rail.show();self.status.setText(str(len(hits))+tr(' Trefferseiten (maximal 100)'))
        self.work(tr('Buch wird durchsucht …'),lambda job:reader.worker(job,'search',self.library.asset(record['asset']),query=query,password=self.passwords.get(key,''),stamp=record['stamp'],legacy=record.get('engine')!=reader.ENGINE,notes=record.get('notes',[])),done)

    def send_marks(self,chapter=False):
        if not self.current:raise ValueError(tr('Zuerst ein Dokument öffnen.'))
        if self.job:raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
        from interop_reader import marks_payload
        from interop_ui import reviewed_send
        self.save();reviewed_send(self,marks_payload(self.library,self.current,chapter),'wissen.import')

    def refresh_original(self):
        if not self.current:raise ValueError(tr('Zuerst ein Dokument öffnen.'))
        from interop_reader import compare_original,refresh_original
        self.save();key=self.current
        def reviewed(status):
            def update():
                if not status['changed']:self.status.setText(tr('Die Lesekopie entspricht dem Original.'));return
                if QMessageBox.question(self,tr('Lesekopie aktualisieren'),tr('Die Originaldatei hat sich geändert. Aktualisieren, wenn Lesestand und alle Markierungen eindeutig zugeordnet werden können?'))!=QMessageBox.Yes:return
                self.work(tr('Seiten und Markierungen werden abgeglichen …'),lambda job:refresh_original(self.library,key,job,self.passwords.get(key,'')),lambda _:self.open_imported(key))
            QTimer.singleShot(0,update)
        self.work(tr('Original und Lesekopie werden verglichen …'),lambda job:compare_original(self.library,key,job),reviewed)

    def ocr_current(self):
        if not self.current or not self.data:raise ValueError(tr('Zuerst eine lesbare Seite öffnen.'))
        from interop_reader import ocr_page
        self.save();key=self.current;page=self.page_index
        def done(text):
            self.mode.setCurrentIndex(1);QTimer.singleShot(0,self.render_page)
        self.work(tr('Text dieser Seite wird lokal erkannt …'),lambda job:ocr_page(self.library,key,page,job,self.passwords.get(key,'')),done)

    def speak(self):
        if not self.data:return
        text=self.selection()[0] or self.data['text']
        if len(text)>24000:raise ValueError(tr('Zum Vorlesen einen kürzeren Abschnitt markieren (maximal 24.000 Zeichen).'))
        self.player.stop();self.clear_audio()
        def done(result):
            self.audio_asset=result['audio'];self.player.load(self.library.asset(self.audio_asset),result['duration']);self.player.show();self.player.play_at()
        self.work(tr('Die lokale Stimme bereitet den Abschnitt vor …'),lambda job:synthesize(text,self.library,job),done)

    def clear_audio(self):
        if self.audio_asset:self.library.asset(self.audio_asset).unlink(missing_ok=True);self.audio_asset=''
        self.player.hide()

    def remember(self):
        self.save();text=self.selection()[0]
        if not text and self.note_id:
            note=next(n for n in self.library.get(self.current)['notes'] if n['id']==self.note_id);text=note['text']+(tr('\n\nMeine Notiz: ')+note['note'] if note['note'] else '')
        if not text.strip():raise ValueError(tr('Eine Textstelle oder eine gespeicherte Markierung auswählen.'))
        from interop_ui import capture,reviewed_send
        previous=getattr(self,'_interop_focus',None)
        self._interop_focus=self.note if previous in (self.note,self.notes) or not self.selection()[0] else self.canvas
        try:payload=capture(self)
        finally:self._interop_focus=previous
        payload['title']=self.library.get(self.current)['title']+tr(' · Seite {0}',payload['source']['position']['page']+1)
        reviewed_send(self,payload,'wissen.import')

    def export_notes(self):
        self.save();record=self.library.get(self.current);lines=['# '+record['title'],record.get('source','')]
        for note in record.get('notes',[]):lines.extend(['',tr('## Seite ')+str(note['page']+1),note['text'],note['note']])
        self.export_text('\n\n'.join(lines),'Lesenotizen.md')

    def closeEvent(self,event):
        super().closeEvent(event)
        if event.isAccepted():self.clear_audio();self.passwords.clear()
