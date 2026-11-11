"""Local EPUB/HTML/text pagination using Qt text layout, without a PDF engine."""
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote,urlsplit
import xml.etree.ElementTree as ET
import zipfile
from PySide6.QtCore import QByteArray,QRectF,QSizeF,QUrl
from PySide6.QtGui import QFont,QImage,QPainter,QTextDocument
from lumen_pdf import PDFError,integer
from lumen_pdf_page import gui

WIDTH,HEIGHT=600,850


def validate_epub(path):
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>10000 or len({e.filename for e in entries})!=len(entries) or sum(e.file_size for e in entries)>256*1024**2:
            raise PDFError('Dieses EPUB enthält zu viele, doppelte oder zu große Inhalte.')
        if any(e.file_size>32*1024**2 or e.flag_bits&1 for e in entries): raise PDFError('Verschlüsseltes oder übergroßes EPUB nicht unterstützt.')
        if 'mimetype' not in archive.namelist() or archive.read('mimetype')!=b'application/epub+zip': raise PDFError('Keine gültige EPUB-Datei.')
        if 'META-INF/encryption.xml' in archive.namelist(): raise PDFError('Verschlüsseltes EPUB wird nicht unterstützt.')


def xml(raw):
    if b'<!ENTITY' in raw.upper(): raise PDFError('XML-Entitäten im EPUB werden nicht geladen.')
    return ET.fromstring(raw)


def local_name(base,href):
    url=urlsplit(href)
    if url.scheme or url.netloc or url.query: raise PDFError('Externe EPUB-Inhalte werden nicht geladen.')
    name=posixpath.normpath(posixpath.join(posixpath.dirname(base),unquote(url.path)))
    if name.startswith(('../','/')) or name=='..' or '\x00' in name or '\\' in name: raise PDFError('Ungültiger EPUB-Pfad.')
    return name


class LocalText(QTextDocument):
    def __init__(self,archive=None):
        super().__init__(); self.archive=archive; self.pixels=0; self.resource_error=None

    def loadResource(self,kind,url):
        # QTextDocument's default file loader must never see a document URL.
        if self.archive is None or url.scheme()!='lumen-epub' or kind!=QTextDocument.ResourceType.ImageResource: return QByteArray()
        name=posixpath.normpath(unquote(url.path()).lstrip('/'))
        if name.startswith('../') or name not in self.archive.namelist(): return QByteArray()
        try:
            raw=self.archive.read(name)
            from PySide6.QtCore import QBuffer,QIODevice
            from PySide6.QtGui import QImageReader
            buffer=QBuffer();buffer.setData(raw);buffer.open(QIODevice.OpenModeFlag.ReadOnly);reader=QImageReader(buffer)
            size=reader.size(); self.pixels+=max(0,size.width()*size.height())
            if size.width()<=0 or size.height()<=0 or self.pixels>40000000: raise PDFError('EPUB-Bildbudget überschritten.')
            return reader.read()
        except Exception as error:
            self.resource_error=error;return QByteArray()



class ReflowBook:
    def __init__(self,path):
        gui();path=Path(path);self.metadata={'title':''};self.outline=[];self.pages=[];self.documents=[];self.archive=None
        try:
            if path.suffix.lower()=='.epub':
                validate_epub(path); self.archive=zipfile.ZipFile(path)
                container=xml(self.archive.read('META-INF/container.xml')); roots=container.findall('.//{*}rootfile')
                if not roots: raise PDFError('EPUB-Inhaltsverzeichnis fehlt.')
                package=local_name('',roots[0].attrib['full-path']); opf=xml(self.archive.read(package))
                title=opf.find('.//{*}title');self.metadata['title']=title.text or '' if title is not None else ''
                manifest={item.attrib['id']:item for item in opf.findall('.//{*}manifest/{*}item')}
                spine=opf.find('.//{*}spine')
                if spine is None: raise PDFError('EPUB-Lesereihenfolge fehlt.')
                starts={}
                for entry in spine:
                    if entry.attrib.get('linear','yes')=='no': continue
                    item=manifest.get(entry.attrib.get('idref'))
                    if item is None: raise PDFError('EPUB-Kapitel fehlt.')
                    name=local_name(package,item.attrib['href']);starts[name]=len(self.pages)
                    self._add(self.archive.read(name).decode('utf-8-sig'),name,rich=True)
                toc=manifest.get(spine.attrib.get('toc'))
                if toc is not None:
                    name=local_name(package,toc.attrib['href']); ncx=xml(self.archive.read(name))
                    def walk(node,level=0):
                        if level>16 or len(self.outline)>2000: raise PDFError('EPUB-Inhaltsverzeichnis zu groß.')
                        for child in node:
                            if child.tag.endswith('navPoint'):
                                label=child.find('./{*}navLabel/{*}text');content=child.find('./{*}content')
                                if label is not None and content is not None:
                                    target=local_name(name,content.attrib['src'])
                                    if target in starts:self.outline.append([max(1,level),label.text or '',starts[target]+1])
                            walk(child,level+1 if child.tag.endswith(('navMap','navPoint')) else level)
                    walk(ncx)
            elif path.suffix.lower() in ('.docx','.docm','.xlsx','.xlsm','.pptx','.pptm','.odt','.ods','.odp'):
                import lumen_office
                # The document core has checked the archive; it is opened here only to hand its pictures to the layout.
                self.metadata['title'],parts=lumen_office.read(path);self.archive=zipfile.ZipFile(path)
                for part in parts:self._add(part,'office',rich=True)
            else:
                text=path.read_text(encoding='utf-8-sig',errors='replace')
                if len(text)>2*1024**2: raise PDFError('Textdokument größer als 2 MiB.')
                if path.suffix.lower()=='.md':
                    self._add(text,'',markdown=True)
                else:self._add(text,'',rich=path.suffix.lower() in ('.html','.htm'))
            if not 1<=len(self.pages)<=10000: raise PDFError('Das Dokument muss 1 bis 10.000 Seiten enthalten.')
        except BaseException:self.close();raise

    def _add(self,text,name,rich=False,markdown=False):
        doc=LocalText(self.archive);font=QFont('sans-serif');font.setPixelSize(14);doc.setDefaultFont(font);doc.setDocumentMargin(32);doc.setPageSize(QSizeF(WIDTH,HEIGHT))
        doc.setDefaultStyleSheet('body { color: black; background: white; }')
        if name:doc.setBaseUrl(QUrl('lumen-epub:/'+name))
        if markdown:doc.setMarkdown(text)
        elif rich:doc.setHtml(text)
        else:doc.setPlainText(text)
        count=doc.pageCount()
        if doc.resource_error and name!='office':raise PDFError('EPUB-Bild konnte nicht geladen werden: '+str(doc.resource_error))
        if not 1<=count<=10000 or len(self.pages)+count>10000:raise PDFError('Zu viele EPUB-/Textseiten.')
        if name=='office':
            # Office files carry no page targets; the headings become the contents, each with the page it landed on.
            block=doc.begin()
            while block.isValid() and len(self.outline)<2000:
                level=block.blockFormat().headingLevel()
                if level and block.text().strip():self.outline.append([level,block.text().strip()[:200],len(self.pages)+int(block.layout().position().y()//HEIGHT)+1])
                block=block.next()
        self.documents.append(doc);self.pages.extend((doc,i) for i in range(count))
        if not self.metadata['title']:self.metadata['title']=doc.metaInformation(QTextDocument.MetaInformation.DocumentTitle)

    def toc(self):return self.outline

    def page(self,index):
        integer(index,0,len(self.pages)-1);doc,number=self.pages[index];return ReflowPage(doc,number)
    def __len__(self):return len(self.pages)
    def close(self):
        if self.archive:self.archive.close();self.archive=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class ReflowPage:
    width,height=WIDTH,HEIGHT
    def __init__(self,document,number):
        self.document=document;self.number=number;self.words=[];self.spans=[];self.image_count=0
        block=document.begin();line_number=0;page_top=number*HEIGHT
        while block.isValid():
            layout=block.layout();position=layout.position();blocktext=block.text().encode('utf-16-le')
            for i in range(layout.lineCount()):
                line=layout.lineAt(i);top=position.y()+line.y()
                if page_top<=top<page_top+HEIGHT:
                    text=blocktext[line.textStart()*2:(line.textStart()+line.textLength())*2].decode('utf-16-le')
                    for match in re.finditer(r'[^\s\ufffc]+',text):  # U+FFFC stands for an embedded picture, not a word
                        start=line.textStart()+len(text[:match.start()].encode('utf-16-le'))//2;end=line.textStart()+len(text[:match.end()].encode('utf-16-le'))//2
                        left=line.cursorToX(start)[0]+position.x();right=line.cursorToX(end)[0]+position.x()
                        self.words.append([min(left,right),top-page_top,max(left,right),top-page_top+line.height(),match[0],block.blockNumber(),line_number])
                    line_number+=1
            block=block.next()
        if len(self.words)>30000:raise PDFError('Zu viele Wörter auf einer Textseite.')
    def text(self):
        lines={}
        for word in self.words:lines.setdefault(word[6],[]).append(word[4])
        return '\n'.join(' '.join(line) for line in lines.values())
    def render(self,scale=1):
        if not 0<scale<=4:raise PDFError('Ungültiger Textseitenmaßstab.')
        image=QImage(round(WIDTH*scale),round(HEIGHT*scale),QImage.Format.Format_RGB888);image.fill(0xffffffff);painter=QPainter(image)
        try:
            painter.scale(scale,scale);painter.translate(0,-self.number*HEIGHT);self.document.drawContents(painter,QRectF(0,self.number*HEIGHT,WIDTH,HEIGHT))
        finally:painter.end()
        return image
