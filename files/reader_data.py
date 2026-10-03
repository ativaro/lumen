"""Private reading copies and an isolated MuPDF renderer; annotations stay in SQLite."""
import base64
import html
import json
from pathlib import Path
import sys
import uuid
import zipfile
from tools_data import ArticleParser, fetch_article

MAX_FILE=200*1024**2


def validate_epub(path):
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>10000 or sum(e.file_size for e in entries)>256*1024**2:
            raise ValueError('Dieses EPUB enthält zu viele oder zu große Inhalte.')
        if any(e.file_size>32*1024**2 or e.flag_bits&1 for e in entries):
            raise ValueError('Verschlüsseltes oder übergroßes EPUB nicht unterstützt.')
        if 'mimetype' not in archive.namelist() or archive.read('mimetype')!=b'application/epub+zip':
            raise ValueError('Keine gültige EPUB-Datei.')


def opened(path,password=''):
    import pymupdf
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError('Lesedatei fehlt oder ist größer als 200 MiB.')
    if path.suffix.lower()=='.epub':validate_epub(path)
    document=pymupdf.open(path)
    if document.needs_pass and not document.authenticate(password):document.close();return None
    if document.is_reflowable:document.layout(width=600,height=850,fontsize=14)
    if not 0<len(document)<=10000:document.close();raise ValueError('Das Dokument muss 1 bis 10.000 Seiten enthalten.')
    return document


def process(payload):
    import pymupdf
    path=Path(payload['path']);expected=payload.get('stamp')
    if expected and expected!=[path.stat().st_size,path.stat().st_mtime_ns]:raise ValueError('Die Lesekopie wurde extern geändert. Als neue Datei importieren, damit Markierungen korrekt bleiben.')
    document=opened(path,payload.get('password',''))
    if document is None:return dict(locked=True)
    with document:
        result=dict(pages=len(document),toc=document.get_toc()[:2000],title=document.metadata.get('title') or '',locked=False)
        action=payload['action']
        if action=='metadata':return result
        if action=='search':
            needle=payload['query'].strip().casefold()
            if not needle or len(needle)>200:raise ValueError('Suchbegriff mit 1 bis 200 Zeichen eingeben.')
            hits=[]
            for index in range(len(document)):
                text=document[index].get_text();offset=text.casefold().find(needle)
                if offset>=0:hits.append(dict(page=index,text=text[max(0,offset-60):offset+180].replace('\n',' ')))
                if len(hits)>=100:break
            return hits
        index=int(payload.get('page',0))
        if not 0<=index<len(document):raise ValueError('Seite nicht vorhanden.')
        page=document[index];words=[]
        for word in page.get_text('words',sort=True)[:30000]:
            rect=pymupdf.Rect(word[:4])*page.rotation_matrix;words.append([*rect,word[4],word[5],word[6]])
        scale=min(2,1800/max(page.rect.width,1),2600/max(page.rect.height,1))
        if scale<=0:raise ValueError('Ungültige Seitengröße.')
        pixmap=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False,colorspace=pymupdf.csRGB)
        result.update(page=index,width=page.rect.width,height=page.rect.height,words=words,text=page.get_text(sort=True)[:150000],png=base64.b64encode(pixmap.tobytes('png')).decode())
        return result


def worker(job,action,path,**values):
    payload=dict(action=action,path=str(path),**values)
    return json.loads(job.command([sys.executable,str(Path(__file__))],data=json.dumps(payload).encode(),timeout=120,max_output=32*1024**2))


def import_file(library,path,job):
    path=Path(path).expanduser().resolve(strict=True)
    if path.suffix.lower() not in ('.pdf','.epub','.txt','.md','.html','.htm'):raise ValueError('PDF, EPUB, Text, Markdown oder HTML auswählen.')
    if path.suffix.lower() in ('.html','.htm'):
        if path.stat().st_size>2*1024**2:raise ValueError('HTML-Artikel größer als 2 MiB.')
        parser=ArticleParser();parser.feed(path.read_text(errors='replace'));return import_text(library,path.stem,parser.text(),path.as_uri(),job)
    asset=library.import_file(path,job,limit=MAX_FILE)['asset'];copy=library.asset(asset)
    try:
        metadata=worker(job,'metadata',copy);job.check()
        title=metadata.pop('title','') or path.stem
        return library.create(title,asset=asset,source=path.as_uri(),page=0,scroll=0,notes=[],**metadata,stamp=[copy.stat().st_size,copy.stat().st_mtime_ns])
    except BaseException:copy.unlink(missing_ok=True);raise


def import_text(library,title,text,source,job):
    if not text.strip() or len(text)>120000:raise ValueError('Artikel muss 1 bis 120.000 Zeichen enthalten.')
    name=uuid.uuid4().hex+'.html';path=library.asset(name)
    # No original tags, scripts, styles, images or external resources enter the renderer.
    body='<html><head><meta charset="utf-8"></head><body><h1>'+html.escape(title)+'</h1>'+''.join('<p>'+html.escape(p)+'</p>' for p in text.splitlines() if p.strip())+'</body></html>'
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
    if not 0<=page<record.get('pages',0) or len(text)>20000:raise ValueError('Ungültige Markierung.')
    notes=record.get('notes',[])
    if len(notes)>=3000:raise ValueError('Maximal 3000 Markierungen pro Buch.')
    note=dict(id=uuid.uuid4().hex,page=page,text=text,note='',words=words or [],selection=selection or [])
    library.update(key,notes=notes+[note]);return note


def main():
    try:print(json.dumps(process(json.load(sys.stdin)),ensure_ascii=False));return 0
    except Exception as error:print(str(error)[:600],file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
