"""A debounced rendered view next to the original Markdown editor."""
import re
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QSplitter
from wissen_views import NotePreview
from tools_ui import Job
import wissen_data as data


class LivePreview(QSplitter):
    def __init__(self,window):
        super().__init__(Qt.Horizontal);self.window=window;self.job=None;self.images={};self.image_key=None;self.rendered=None;self.stopping=False
        self.addWidget(window.editor);self.preview=NotePreview();self.preview.setObjectName('wissenPreview');self.addWidget(self.preview)
        self.setObjectName('notesLiveSplit');self.setChildrenCollapsible(False);self.setHandleWidth(5);self.setSizes([450,450])
        self.preview.interop_root=window.library.root.parent
        self.preview.noteRequested.connect(lambda path:window.safe(window.open_note_target,path))
        self.preview.targetRequested.connect(lambda path,anchor:window.safe(window.open_note_target,path,anchor))
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(250);self.timer.timeout.connect(self.refresh)
        window.editor.textChanged.connect(self.schedule);window.title.textChanged.connect(self.schedule)
        self.enabled=bool(window.settings.value('notes/livePreview',False,type=bool));self.preview.setVisible(self.enabled)

    def set_enabled(self,enabled):
        self.enabled=enabled;self.preview.setVisible(enabled);self.window.settings.setValue('notes/livePreview',enabled)
        if enabled:self.refresh()

    def schedule(self):
        if not self.stopping:self.timer.start()

    def refresh(self):
        w=self.window
        if self.stopping:return
        if not w.doc or not w.book:
            self.preview.clear();self.rendered=None;return
        text=w.document_text();book=w.book;path=w.doc['path']
        from notes_render import prepare
        rendered_text=prepare(text,path,w.notes)
        links=tuple(re.findall(r'!\[[^\]\n]*\]\(([^)\n]+)\)',rendered_text)[:16])
        key=(str(book.root),book.identity,path,links)
        if self.image_key!=key:
            self.images={};self.image_key=key
            if links:self.load_images(book,path,rendered_text,key)
        snapshot=(str(book.root),path,rendered_text)
        if snapshot!=self.rendered:
            scroll=self.preview.verticalScrollBar().value();self.preview.display(book,dict(w.doc,text=w.editor.toPlainText()),w.notes,self.images)
            if self.rendered and self.rendered[:2]==snapshot[:2]:self.preview.verticalScrollBar().setValue(scroll)
            self.rendered=snapshot
        if hasattr(w,'rich_editor'):w.rich_editor.set_images(self.images)

    def load_images(self,book,path,text,key):
        if self.job:
            self.image_key=None;return
        job=Job(lambda job:data.worker(job,self.window.store,'preview',str(book.root),identity=book.identity,path=path,text=text),self)
        self.job=job
        def loaded(images):
            if self.image_key==key and not self.stopping:self.images=images;self.rendered=None;self.refresh()
        job.result.connect(loaded)
        job.failed.connect(lambda message:self.preview.setToolTip(message))
        job.finished.connect(self.finished);job.start()

    def finished(self):
        self.job.deleteLater();self.job=None
        if self.stopping:
            self.stopping=False;QTimer.singleShot(0,self.window.close)
        elif self.image_key is None:self.schedule()

    def shutdown(self):
        self.stopping=bool(self.job);self.timer.stop()
        if self.job:self.job.cancelled.set();return False
        return True

    def resizeEvent(self,event):
        super().resizeEvent(event)
        orientation=Qt.Horizontal if self.width()>=780 else Qt.Vertical
        if self.orientation()!=orientation:self.setOrientation(orientation);self.setSizes([400,400])
