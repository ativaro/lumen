"""Safe local Markdown and a small, native notebook connection map."""
from lumen_i18n import tr
import math
import base64
from pathlib import Path
import re
from urllib.parse import quote,unquote
from PySide6.QtCore import Qt,QUrl,QTimer,QEvent,Signal
from PySide6.QtGui import QColor,QBrush,QPen,QImage,QTextDocument,QTextCursor,QPainter
from PySide6.QtWidgets import QTextBrowser,QGraphicsView,QGraphicsScene,QGraphicsEllipseItem,QGraphicsSimpleTextItem
from notes_query import resolve_link


class NoteDocument(QTextDocument):
    def __init__(self,owner):super().__init__(owner);self.owner=owner
    def loadResource(self,kind,url):return self.owner.loadResource(kind,url)


class NotePreview(QTextBrowser):
    note_hash=''
    noteRequested=Signal(str)
    targetRequested=Signal(str,str)
    def __init__(self,parent=None):
        super().__init__(parent);self.book=None;self.notes={};self.origin='';self.images={};self.setDocument(NoteDocument(self))
        self.setOpenLinks(False);self.setOpenExternalLinks(False);self.anchorClicked.connect(self.follow)
        self.setAccessibleName(tr('Notizvorschau mit lokalen Verknüpfungen'))
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.setInterval(80);self.fit_timer.timeout.connect(self.fit_images)

    def display(self,book,note,notes,images=None):
        self.book=book;self.origin=note['path'];self.notes=notes
        self.images=images or {}
        self.document().setBaseUrl(QUrl.fromLocalFile(str(book.root/Path(note['path']).parent)+'/'))
        from notes_render import prepare
        self.setMarkdown(prepare(note['text'],note['path'],notes))
        self.fit_timer.start()

    def fit_images(self):
        block=self.document().begin()
        while block.isValid():
            iterator=block.begin()
            while not iterator.atEnd():
                fragment=iterator.fragment();fmt=fragment.charFormat()
                if fmt.isAnchor():
                    fmt.setForeground(self.palette().link());cursor=QTextCursor(self.document());cursor.setPosition(fragment.position());cursor.setPosition(fragment.position()+fragment.length(),QTextCursor.KeepAnchor);cursor.mergeCharFormat(fmt)
                if fmt.isImageFormat():
                    fmt=fmt.toImageFormat();url=self.document().baseUrl().resolved(QUrl(fmt.name()));img=self.loadResource(QTextDocument.ImageResource,url)
                    if img is not None:
                        width=min(img.width(),max(40,self.viewport().width()-32))
                        if fmt.width()!=width:
                            fmt.setWidth(width);fmt.setHeight(width*img.height()/img.width());cursor=QTextCursor(self.document());cursor.setPosition(fragment.position());cursor.setPosition(fragment.position()+fragment.length(),QTextCursor.KeepAnchor);cursor.mergeCharFormat(fmt)
                iterator+=1
            block=block.next()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'fit_timer'):self.fit_timer.start()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.PaletteChange and hasattr(self,'fit_timer'):self.fit_timer.start()

    def loadResource(self,kind,url):
        if kind!=QTextDocument.ImageResource or not self.book or not url.isLocalFile():return None
        try:
            path=Path(url.toLocalFile()).relative_to(self.book.root)
            raw=base64.b64decode(self.images.get(str(path),''));image=QImage.fromData(raw)
            if image.isNull() or image.width()*image.height()>36_000_000:return None
            return image.scaled(1800,1800,Qt.KeepAspectRatio,Qt.SmoothTransformation) if max(image.width(),image.height())>1800 else image
        except (OSError,ValueError):return None

    def follow(self,url):
        if url.query().startswith('document=') and self.book:
            path=resolve_link(self.origin,'/?'+url.query(),self.notes)
            if path:self.noteRequested.emit(path)
            return
        if url.scheme()=='lumen-note':
            path=unquote(url.path().lstrip('/'))
            if url.fragment():self.targetRequested.emit(path,url.fragment())
            else:self.noteRequested.emit(path)
            return
        if url.scheme() in ('https','http'):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url);return
        if url.scheme()=='lumen':
            from interop_open import open_url
            from interop_ui import safe_action
            safe_action(self.window(),lambda:open_url(url.toString(),getattr(self,'interop_root',None)));return
        if url.isLocalFile() and self.book:
            try:path=str(Path(url.toLocalFile()).relative_to(self.book.root))
            except ValueError:return
        elif not url.scheme():path=resolve_link(self.origin,url.toString(),self.notes)
        else:return
        if path in self.notes:
            if url.fragment():self.targetRequested.emit(path,url.fragment())
            else:self.noteRequested.emit(path)


class GraphNode(QGraphicsEllipseItem):
    def __init__(self,path,note,x,y,view,center=False):
        radius=17 if center else 10
        super().__init__(-radius,-radius,radius*2,radius*2);self.setPos(x,y);self.path=path;self.view=view
        self.setBrush(QBrush(view.palette().highlight().color() if center else view.palette().mid().color()));self.setPen(QPen(Qt.NoPen));self.setCursor(Qt.PointingHandCursor)
        label=QGraphicsSimpleTextItem(note['title'][:32],self);label.setBrush(view.palette().text());label.setPos(-label.boundingRect().width()/2,radius+9)
        self.setToolTip(note['title']+'\n'+path)
    def mousePressEvent(self,event):
        (self.view.objectRequested if self.path.startswith('lumen://') else self.view.noteRequested).emit(self.path);event.accept()


class KnowledgeMap(QGraphicsView):
    noteRequested=Signal(str)
    objectRequested=Signal(str)
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self));self.setRenderHints(self.renderHints()|QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag);self.setAccessibleName(tr('Notizkarte; dieselben Verbindungen sind in der Notizliste per Tastatur erreichbar'))
    def display(self,notes,current,external=()):
        scene=self.scene();scene.clear()
        if not notes:return
        current=current if current in notes else next(iter(notes));edges=set()
        for path,note in notes.items():
            for link in note['links']:
                target=resolve_link(path,link,notes)
                if target and target!=path:edges.add((path,target))
        nodes=dict(notes)
        for value in external:
            target=value['url'];nodes[target]=dict(title=value['app_title']+' · '+value['title']);edges.add((current,target))
        neighbors=sorted({b if a==current else a for a,b in edges if current in (a,b)})[:36]
        positions={current:(0,0)}
        for i,path in enumerate(neighbors):
            angle=i*math.tau/max(1,len(neighbors));positions[path]=(math.cos(angle)*340,math.sin(angle)*250)
        for a,b in edges:
            if a in positions and b in positions:scene.addLine(*positions[a],*positions[b],QPen(self.palette().mid().color(),1.3))
        for path,(x,y) in positions.items():scene.addItem(GraphNode(path,nodes[path],x,y,self,path==current))
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-50,-50,50,50));self.fitInView(scene.sceneRect(),Qt.KeepAspectRatio)
    def resizeEvent(self,event):super().resizeEvent(event);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
