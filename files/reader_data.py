"""Private reading copies and the isolated Lumen renderer; annotations stay in SQLite."""
from lumen_i18n import tr
import base64
import html
import json
from pathlib import Path
import sys
import uuid
from tools_data import ArticleParser, fetch_article

MAX_FILE=200*1024**2


# Raised whenever the engine reads other words from the same page, so that notes are anchored again by their quote.
ENGINE='lumen-2'


def validate_epub(path):
    from lumen_reflow import validate_epub as validate
    return validate(path)


def opened(path):
    """An EPUB, text or Office reading copy laid out into pages. PDFs are read by the document core."""
    from lumen_reflow import ReflowBook
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError(tr('Lesedatei fehlt oder ist größer als 200 MiB.'))
    document=ReflowBook(path)
    if not 0<len(document)<=10000:raise ValueError(tr('Das Dokument muss 1 bis 10.000 Seiten enthalten.'))
    return document


def reanchor(document,notes,reflow=False):
    """Keep legacy anchors, and replace coordinates only for an exact unique quote."""
    import re
    result=[];cache={}
    def words(index):
        if index not in cache:cache[index]=document.page(index).words
        return cache[index]
    for original in notes:
        if original.get('engine')==ENGINE:result.append(original);continue
        note=dict(original,legacy_anchor=original.get('legacy_anchor') or {key:original.get(key) for key in ('page','words','selection')},words=[],selection=[],engine=ENGINE)
        quote=re.findall(r'\S+',note.get('text',''));matches=[]
        if quote:
            for index in (range(len(document)) if reflow else [note['page']]):
                if not 0<=index<len(document):continue
                values=words(index);strings=[w[4] for w in values]
                for first in range(len(strings)-len(quote)+1):
                    if strings[first:first+len(quote)]==quote:matches.append((index,first,first+len(quote)))
                if len(matches)>1:break
        if len(matches)==1:
            index,first,end=matches[0];note.update(page=index,words=list(range(first,end)),anchor_status='matched')
            text=document.page(index).text();pattern=r'(?<!\S)'+r'\s+'.join(re.escape(word) for word in quote)+r'(?!\S)';found=list(re.finditer(pattern,text))
            if len(found)==1:
                hit=found[0];note['selection']=[len(text[:offset].encode('utf-16-le'))//2 for offset in (hit.start(),hit.end())]
        elif not quote and not reflow and 0<=note['page']<len(document):note['anchor_status']='page'
        else:note['anchor_status']='unresolved'
        result.append(note)
    return result


def process(payload):
    """The answer for a reading copy that is not a PDF, in the isolated worker."""
    from lumen_office import signature
    from lumen_reflow import png
    path=Path(payload['path']);before=signature(path);expected=payload.get('stamp')
    if expected and expected!=[before[2],before[3]]:raise ValueError(tr('Die Lesekopie wurde extern geändert. Als neue Datei importieren, damit Markierungen korrekt bleiben.'))
    document=opened(path)
    with document:
        result=dict(pages=len(document),toc=document.toc()[:2000],title=document.metadata.get('title') or '',locked=False,engine=ENGINE)
        action=payload['action']
        if action=='text':
            parts=[]; size=0
            for index in range(len(document)):
                text=document.page(index).text(); size+=len(text)
                if size>120000:raise ValueError(tr('Mehr als 120.000 Zeichen; bitte einen kürzeren Auszug importieren.'))
                parts.append(text)
            result=dict(text='\n\n'.join(parts))
        elif action=='search':
            needle=payload['query'].strip().casefold()
            if not needle or len(needle)>200:raise ValueError(tr('Suchbegriff mit 1 bis 200 Zeichen eingeben.'))
            result=[]
            for index in range(len(document)):
                text=document.page(index).text();offset=text.casefold().find(needle)
                if offset>=0:result.append(dict(page=index,text=text[max(0,offset-60):offset+180].replace('\n',' ')))
                if len(result)>=100:break
        elif action=='page':
            index=int(payload.get('page',0))
            if payload.get('legacy'):
                result['notes']=reanchor(document,payload.get('notes',[]),True)
                result['position_changed']=True
                index=min(max(0,index),len(document)-1)
            if not 0<=index<len(document):raise ValueError(tr('Seite nicht vorhanden.'))
            page=document.page(index);scale=min(2,1800/page.width,2600/page.height)
            result.update(page=index,width=page.width,height=page.height,words=page.words[:30000],text=page.text()[:150000],png=base64.b64encode(png(page.render(scale))).decode())
        elif action!='metadata':raise ValueError('Unbekannte Reader-Aktion.')
        if signature(path)!=before:raise ValueError('Lesekopie wurde während des Lesens verändert.')
        return result


class Locked(Exception):
    """The PDF needs a password, or another one."""


def core(job,*arguments,password=''):
    """An answer of Lumen's document core; its reason, translated, when it cannot read the file."""
    from lumen_office import message,program
    from lumen_jobs import worker_environment
    from tools_data import Cancelled
    # A password goes to the core on its standard input, never in the argument list.
    secret=dict(data=(password+'\n').encode(),env=worker_environment()|{'LUMEN_PDF_PASSWORD_STDIN':'1'}) if password else {}
    try:return json.loads(job.command([program(),*arguments],timeout=120,max_output=48*1024**2,**secret))
    except Cancelled:raise
    except (ValueError,OSError) as error:
        job.check()
        if 'PDF-Passwort' in str(error):raise Locked() from error
        raise ValueError(message(error)) from error


class CorePage:
    def __init__(self,words):self.words=words
    def text(self):
        lines={}
        for word in self.words:lines.setdefault(word[6],[]).append(word[4])
        return '\n'.join(' '.join(words) for words in lines.values())


class CoreDocument:
    """The pages of a PDF as the document core reads them, fetched when asked for."""
    def __init__(self,job,path,pages,password=''):self.job,self.path,self.pages,self.cache,self.password=job,path,pages,{},password
    def __len__(self):return self.pages
    def page(self,index):
        if index not in self.cache:
            data=core(self.job,'pdf-words',str(self.path),str(index),'1',password=self.password)
            if 'words' not in data[0]:raise ValueError(tr(data[0].get('error') or 'PDF-Seite konnte nicht gelesen werden.'))
            self.cache[index]=CorePage([word[:5]+[0,word[5]] for word in data[0]['words']])
        return self.cache[index]


def core_process(job,action,path,values):
    """What process() answers for other formats, for a PDF from the document core."""
    from lumen_office import signature
    before=signature(path);expected=values.get('stamp');password=values.get('password') or ''
    if expected and expected!=[before[2],before[3]]:raise ValueError(tr('Die Lesekopie wurde extern geändert. Als neue Datei importieren, damit Markierungen korrekt bleiben.'))
    if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError(tr('Lesedatei fehlt oder ist größer als 200 MiB.'))
    try:
        if action in ('metadata','page'):
            index=int(values.get('page',0));legacy=action=='page' and values.get('legacy')
            # A page answer carries the document's data too; only re-anchoring needs the page count first.
            data=core(job,'pdf-reader',str(path),'metadata',password=password) if action=='metadata' or legacy else core(job,'pdf-reader',str(path),'page',str(index),password=password)
            if not 0<data['pages']<=10000:raise ValueError(tr('Das Dokument muss 1 bis 10.000 Seiten enthalten.'))
            result=dict(pages=data['pages'],toc=data['toc'],title=data['title'],locked=False,engine=ENGINE)
            if action=='page':
                if legacy:
                    result['notes']=reanchor(CoreDocument(job,path,data['pages'],password),values.get('notes',[]),False);result['position_changed']=False
                    index=min(max(0,index),data['pages']-1)
                if not 0<=index<data['pages']:raise ValueError(tr('Seite nicht vorhanden.'))
                shown=core(job,'pdf-reader',str(path),'page',str(index),password=password) if legacy else data
                words=shown['words'][:30000]
                result.update(page=index,width=shown['width'],height=shown['height'],words=words,text=CorePage(shown['words']).text()[:150000],png=shown['png'])
        elif action in ('text','search'):
            pages=core(job,'pdf-words',str(path),'0','10000',password=password)
            unread=next((page for page in pages if 'words' not in page),None)
            if unread is not None:raise ValueError(tr(unread.get('error') or 'PDF-Seite konnte nicht gelesen werden.'))
            texts=[CorePage([word[:5]+[0,word[5]] for word in page['words']]).text() for page in pages]
            if action=='text':
                if sum(map(len,texts))>120000:raise ValueError(tr('Mehr als 120.000 Zeichen; bitte einen kürzeren Auszug importieren.'))
                result=dict(text='\n\n'.join(texts))
            else:
                needle=values['query'].strip().casefold()
                if not needle or len(needle)>200:raise ValueError(tr('Suchbegriff mit 1 bis 200 Zeichen eingeben.'))
                result=[]
                for index,text in enumerate(texts):
                    offset=text.casefold().find(needle)
                    if offset>=0:result.append(dict(page=index,text=text[max(0,offset-60):offset+180].replace('\n',' ')))
                    if len(result)>=100:break
        else:raise ValueError('Unbekannte Reader-Aktion.')
    except Locked:return dict(locked=True)
    if signature(path)!=before:raise ValueError('Lesekopie wurde während des Lesens verändert.')
    return result


def worker(job,action,path,**values):
    # A PDF is read by the document core in this thread; every other format by the isolated Python worker.
    if Path(path).suffix.lower()=='.pdf':return core_process(job,action,Path(path),values)
    payload=dict(action=action,path=str(path),**values)
    return json.loads(job.command([sys.executable,str(Path(__file__))],data=json.dumps(payload).encode(),timeout=120,max_output=32*1024**2))


def import_file(library,path,job):
    path=Path(path).expanduser().resolve(strict=True)
    from lumen_office import OFFICE
    if path.suffix.lower() not in {'.pdf','.epub','.txt','.md','.html','.htm'}|OFFICE:raise ValueError(tr('PDF, EPUB, Text, Markdown, HTML oder ein Office-Dokument auswählen.'))
    if path.suffix.lower() in ('.html','.htm'):
        if path.stat().st_size>2*1024**2:raise ValueError(tr('HTML-Artikel größer als 2 MiB.'))
        parser=ArticleParser();parser.feed(path.read_text(errors='replace'));return import_text(library,path.stem,parser.text(),path.as_uri(),job)
    asset=library.import_file(path,job,limit=MAX_FILE)['asset'];copy=library.asset(asset)
    try:
        metadata=worker(job,'metadata',copy);job.check()
        title=metadata.pop('title','') or path.stem
        return library.create(title,asset=asset,source=path.as_uri(),page=0,scroll=0,notes=[],**metadata,stamp=[copy.stat().st_size,copy.stat().st_mtime_ns])
    except BaseException:copy.unlink(missing_ok=True);raise


def import_text(library,title,text,source,job):
    if not text.strip() or len(text)>120000:raise ValueError(tr('Artikel muss 1 bis 120.000 Zeichen enthalten.'))
    name=uuid.uuid4().hex+'.html';path=library.asset(name)
    # No original tags, scripts, styles, images or external resources enter the renderer.
    paragraphs=[p for p in text.splitlines() if p.strip()]
    if paragraphs and paragraphs[0].strip()==title.strip():paragraphs.pop(0)
    body='<html><head><meta charset="utf-8"></head><body><h1>'+html.escape(title)+'</h1>'+''.join('<p>'+html.escape(p)+'</p>' for p in paragraphs)+'</body></html>'
    with path.open('x') as stream:path.chmod(0o600);stream.write(body)
    try:
        metadata=worker(job,'metadata',path);job.check()
        metadata.pop('title',None)
        return library.create(title,asset=name,source=source,page=0,scroll=0,notes=[],**metadata,stamp=[path.stat().st_size,path.stat().st_mtime_ns])
    except BaseException:path.unlink(missing_ok=True);raise


def import_url(library,url,job):
    article=fetch_article(url,job)
    return import_text(library,article['title'],article['text'],article['url'],job)


def add_note(library,key,page,text='',words=None,selection=None):
    record=library.get(key)
    if not 0<=page<record.get('pages',0) or len(text)>20000:raise ValueError(tr('Ungültige Markierung.'))
    notes=record.get('notes',[])
    if len(notes)>=3000:raise ValueError(tr('Maximal 3000 Markierungen pro Buch.'))
    note=dict(id=uuid.uuid4().hex,engine=ENGINE,page=page,text=text,note='',words=words or [],selection=selection or [])
    library.update(key,notes=notes+[note]);return note


def main():
    from lumen_office import limits
    limits()
    try:print(json.dumps(process(json.load(sys.stdin)),ensure_ascii=False));return 0
    except Exception as error:print(str(error)[:600],file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
