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


ENGINE='lumen-1'


def validate_epub(path):
    from lumen_reflow import validate_epub as validate
    return validate(path)


def opened(path,password=''):
    from lumen_pdf import Document
    from lumen_pdf_security import PasswordRequired
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError(tr('Lesedatei fehlt oder ist größer als 200 MiB.'))
    try:
        if path.suffix.lower()=='.pdf':document=Document(path,password=password)
        else:
            from lumen_reflow import ReflowBook
            document=ReflowBook(path)
    except PasswordRequired:return None
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
    from lumen_pdf_page import png
    from lumen_pdf_worker import signature
    path=Path(payload['path']);before=signature(path);expected=payload.get('stamp')
    if expected and expected!=[before[2],before[3]]:raise ValueError(tr('Die Lesekopie wurde extern geändert. Als neue Datei importieren, damit Markierungen korrekt bleiben.'))
    document=opened(path,payload.get('password',''))
    if document is None:return dict(locked=True)
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
                result['notes']=reanchor(document,payload.get('notes',[]),path.suffix.lower()!='.pdf')
                result['position_changed']=path.suffix.lower()!='.pdf'
                index=min(max(0,index),len(document)-1)
            if not 0<=index<len(document):raise ValueError(tr('Seite nicht vorhanden.'))
            page=document.page(index);scale=min(2,1800/page.width,2600/page.height)
            result.update(page=index,width=page.width,height=page.height,words=page.words[:30000],text=page.text()[:150000],png=base64.b64encode(png(page.render(scale))).decode())
        elif action!='metadata':raise ValueError('Unbekannte Reader-Aktion.')
        if signature(path)!=before:raise ValueError('Lesekopie wurde während des Lesens verändert.')
        return result


def worker(job,action,path,**values):
    payload=dict(action=action,path=str(path),**values)
    return json.loads(job.command([sys.executable,str(Path(__file__))],data=json.dumps(payload).encode(),timeout=120,max_output=32*1024**2))


def import_file(library,path,job):
    path=Path(path).expanduser().resolve(strict=True)
    if path.suffix.lower() not in ('.pdf','.epub','.txt','.md','.html','.htm'):raise ValueError(tr('PDF, EPUB, Text, Markdown oder HTML auswählen.'))
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
    from lumen_pdf_worker import limits
    limits()
    try:print(json.dumps(process(json.load(sys.stdin)),ensure_ascii=False));return 0
    except Exception as error:print(str(error)[:600],file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
