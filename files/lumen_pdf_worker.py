"""Isolated Lumen PDF operations; JSON for apps, bounded CLI for file workers."""
import base64
import json
import math
import os
from pathlib import Path
import sys

from lumen_pdf import Document, Name, PDFError, Writer, integer, serialize


def signature(path):
    info=Path(path).stat()
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


def raster_page(writer,image,width,height):
    from PySide6.QtGui import QImage
    from lumen_pdf import MAX_STREAM
    if image.width()*image.height()*3>MAX_STREAM: raise PDFError('Raster-PDF-Seite zu groß; niedrigere Auflösung wählen.')
    image=image.convertToFormat(QImage.Format.Format_RGB888)
    stride=image.bytesPerLine(); raw=bytes(image.constBits())
    pixels=b''.join(raw[y*stride:y*stride+image.width()*3] for y in range(image.height()))
    reference=writer.stream(pixels,Type=Name('XObject'),Subtype=Name('Image'),Width=image.width(),Height=image.height(),ColorSpace=Name('DeviceRGB'),BitsPerComponent=8)
    content=b'q '+serialize(width)+b' 0 0 '+serialize(height)+b' 0 0 cm /LumenImage Do Q\n'
    return writer.add_page(width,height,content,{'XObject':{'LumenImage':reference}})


def ocr_text(text_writer,page,image,dpi):
    import csv,io,subprocess,tempfile
    from lumen_ocr import languages
    with tempfile.TemporaryDirectory(prefix='lumen-pdf-ocr-') as folder:
        path=Path(folder)/'page.png'
        if not image.save(str(path),'PNG'):raise PDFError('OCR-Bild konnte nicht gespeichert werden.')
        result=subprocess.run(['tesseract',str(path),'stdout','-l',languages(),'--dpi',str(dpi),'tsv'],capture_output=True,timeout=120,check=True)
        if len(result.stdout)>4*1024**2:raise PDFError('OCR-Ergebnis zu groß.')
        for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')),delimiter='\t'):
            if row['level']!='5' or not row['text'].strip():continue
            x,y,w,h=[int(row[k])*72/dpi for k in ('left','top','width','height')]
            if min(x,y)<0 or w<=0 or h<=0 or x+w>page['MediaBox'][2]+1 or y+h>page['MediaBox'][3]+1:raise PDFError('Ungültige OCR-Textposition.')
            text_writer.box(page,[x,y,x+w,y+h+2], [row['text']], [dict(size=max(1,h*.85))],min_scale=.1,invisible=True)


def export(pages,target,dpi=200,ocr=False,progress=lambda _:None):
    """Copy/reorder/rotate pages; rasterize selected redactions into new objects."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor,QPainter
    from lumen_pdf_page import Page
    if not isinstance(pages,list) or not 1<=len(pages)<=2000 or dpi not in (150,200,300): raise PDFError('Ungültige Seitenauswahl oder Qualität.')
    target=Path(target).absolute()
    if os.path.lexists(target): raise FileExistsError('Die PDF-Zieldatei existiert bereits.')
    writer=Writer(); documents={}; stamps={}
    from lumen_pdf_text import TextWriter
    text_writer=TextWriter(writer) if ocr else None
    # Unchanged pages may share an unused resource containing redacted text.
    # Until resource pruning exists, any redaction rebuilds the entire export.
    rasterize=any(item.get('boxes') for item in pages)
    for position,item in enumerate(pages):
        progress(f'Seite {position+1} von {len(pages)}')
        path=Path(item['path']).absolute()
        if path.is_symlink() or not path.is_file() or path==target: raise PDFError('PDF-Original unverändert lassen; neue Zieldatei wählen.')
        stamp=signature(path)
        if stamp!=item['stamp']: raise PDFError('PDF-Quelle wurde verändert.')
        if path not in documents: documents[path]=Document(path); stamps[path]=stamp
        document=documents[path]; index=integer(item['page'],0,len(document)-1); rotation=item.get('rotation',0)
        if type(rotation) is not int or rotation not in (0,90,180,270): raise PDFError('Ungültige PDF-Drehung.')
        boxes=item.get('boxes',[])
        if not isinstance(boxes,list) or len(boxes)>10000: raise PDFError('Ungültige PDF-Schwärzungsbereiche.')
        for box in boxes:
            if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in box) or box[0]>=box[2] or box[1]>=box[3]: raise PDFError('Ungültiger PDF-Schwärzungsbereich.')
        page=Page(document,index,rotation) if rasterize or ocr else None
        recognize=ocr and (rasterize or not page.text().strip())
        if rasterize or recognize:
            image=page.render(dpi/72); painter=QPainter(image)
            try:
                for x0,y0,x1,y1 in boxes:
                    left,top=math.floor(x0*image.width()),math.floor(y0*image.height())
                    right,bottom=math.ceil(x1*image.width()),math.ceil(y1*image.height())
                    painter.fillRect(QRect(left,top,right-left,bottom-top),QColor('black'))
            finally: painter.end()
            output_page=raster_page(writer,image,page.width,page.height)
            if recognize:ocr_text(text_writer,output_page,image,dpi)
        else: writer.copy_page(document,index,rotation)
    if text_writer:text_writer.finalize()
    # Validate and serialize before the final source check, then publish atomically.
    data=writer.bytes(); check=Document(data)
    if len(check)!=len(pages): raise PDFError('PDF-Exportprüfung fehlgeschlagen.')
    for path,stamp in stamps.items():
        if signature(path)!=stamp: raise PDFError('PDF-Quelle während des Exports verändert.')
    return writer.save(target)


def process(request):
    from lumen_pdf_page import Page,png
    action=request['action']
    if action=='export': return {'path':export(request['pages'],request['target'],request.get('dpi',200))}
    path=Path(request['path']); before=signature(path); expected=request.get('stamp')
    if expected and expected!=[before[2],before[3]]: raise PDFError('Lesekopie wurde verändert.')
    document=Document(path); result={'pages':len(document),'title':document.metadata.get('title',''),'locked':False,'backend':'lumen-pdf'}
    if action=='metadata': pass
    elif action=='text':
        chunks=[]; size=0
        for index in range(len(document)):
            text=Page(document,index).text(); size+=len(text)
            if size>120000: raise PDFError('Mehr als 120.000 PDF-Textzeichen.')
            chunks.append(text)
        result={'text':'\n\n'.join(chunks)}
    elif action=='page':
        index=integer(request.get('page',0),0,len(document)-1); page=Page(document,index); scale=min(2,1800/page.width,2600/page.height)
        result.update(page=index,width=page.width,height=page.height,words=page.words[:30000],text=page.text()[:150000],png=base64.b64encode(png(page.render(scale))).decode())
    elif action=='inspect':
        result={'pages':[{'path':str(path),'page':index,'rotation':0,'boxes':[],'stamp':before} for index in range(len(document))]}
    else: raise PDFError('Unbekannte PDF-Aktion.')
    if signature(path)!=before: raise PDFError('PDF-Quelle während des Lesens verändert.')
    return result


def limits():
    import resource
    for kind,budget in ((resource.RLIMIT_AS,3*1024**3),(resource.RLIMIT_CPU,90)):
        soft,hard=resource.getrlimit(kind)
        bound=min(budget,hard) if hard!=resource.RLIM_INFINITY else budget
        if soft!=resource.RLIM_INFINITY:bound=min(bound,soft)
        resource.setrlimit(kind,(bound,bound))


def cli():
    import argparse
    from lumen_pdf_page import Page
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('text','info','render'));parser.add_argument('path');parser.add_argument('--page',type=int,default=0);parser.add_argument('--pages',type=int,default=10000);parser.add_argument('--scale-to',type=int,default=1500);parser.add_argument('--output');parser.add_argument('--limit',type=int,default=2*1024**2);parser.add_argument('--characters',type=int)
    args=parser.parse_args();before=signature(args.path);document=Document(args.path)
    if args.action=='info':print(json.dumps(dict(pages=len(document),title=document.metadata.get('title',''))))
    elif args.action=='render':
        page=Page(document,integer(args.page,0,len(document)-1));scale=min(4,integer(args.scale_to,1,6000)/max(page.width,page.height));image=page.render(scale)
        if signature(args.path)!=before:raise PDFError('PDF-Quelle wurde verändert.')
        if not args.output or not image.save(args.output,'PNG'):raise PDFError('PDF-Vorschau konnte nicht gespeichert werden.')
    else:
        remaining=integer(args.limit,1,16*1024**2);characters=0
        if args.characters is not None:integer(args.characters,1,1000000)
        for index in range(min(len(document),integer(args.pages,1,10000))):
            value=Page(document,index).text()+'\f';characters+=len(value)
            if args.characters is not None and characters>args.characters:raise PDFError('Mehr als '+str(args.characters)+' PDF-Textzeichen; bitte einen kürzeren Auszug importieren.')
            chunk=value.encode('utf-8');sys.stdout.buffer.write(chunk[:remaining]);sys.stdout.buffer.flush();remaining-=len(chunk)
            if remaining<=0:break
    if signature(args.path)!=before:raise PDFError('PDF-Quelle wurde verändert.')
    return 0


def main():
    limits()
    try:
        if len(sys.argv)>1:return cli()
        request=sys.stdin.buffer.read(4*1024**2+1)
        if len(request)>4*1024**2: raise PDFError('PDF-Auftrag zu groß.')
        print(json.dumps(process(json.loads(request)),ensure_ascii=False)); return 0
    except Exception as error:
        print(str(error)[:600],file=sys.stderr); return 1


if __name__=='__main__': sys.exit(main())
