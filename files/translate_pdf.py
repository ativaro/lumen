"""Isolated PDF translation layout engine. Never edits the input in place."""
from lumen_i18n import tr
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

MAX_FILE = 50 * 1024**2
MAX_CHARS = 100000


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        total = 0
        while chunk := stream.read(1024**2):
            total += len(chunk)
            if total > MAX_FILE: raise ValueError(tr('PDF ist größer als 50 MiB.'))
            digest.update(chunk)
    return digest.hexdigest()


def _segments(page):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QTransform
    normal=page.transform.inverted()[0]*QTransform(1,0,0,-1,0,page.attrs['MediaBox'][3])
    groups=[]
    for span in page.spans:
        if not span['text'].strip():continue
        box=span.get('layout_bbox',span['bbox']);rect=QRectF(box[0],box[1],box[2]-box[0],box[3]-box[1]);angle=span.get('angle',0)
        if 'layout_bbox' not in span:rect=normal.mapRect(rect)
        style=dict(size=span['size'],color=span['color'],bold=span['bold'],italic=span['italic'])
        if groups and groups[-1]['angle']==angle and abs(groups[-1]['rect'][1]-rect.top())<max(style['size'],groups[-1]['styles'][-1]['size'])*.4 and -.5<=rect.left()-groups[-1]['rect'][2]<=style['size']*2:
            group=groups[-1];gap=rect.left()-group['rect'][2];group['parts'].append((' ' if gap>style['size']*.15 else '')+span['text']);group['styles'].append(style);group['rect']=[min(group['rect'][0],rect.left()),min(group['rect'][1],rect.top()),max(group['rect'][2],rect.right()),max(group['rect'][3],rect.bottom())]
        else:groups.append(dict(rect=[rect.left(),rect.top(),rect.right(),rect.bottom()],parts=[span['text']],styles=[style],angle=angle))
    return groups


def inspect(path):
    from lumen_pdf import Document
    from lumen_pdf_page import Page
    path=Path(path)
    if path.suffix.lower()!='.pdf' or not path.is_file():raise ValueError(tr('Bitte eine PDF-Datei auswählen.'))
    stamp=fingerprint(path);document=Document(path);segments=[];total=0
    if document.encrypted:raise ValueError(tr('Die PDF ist verschlüsselt. Bitte zuerst eine entsperrte Kopie erstellen.'))
    if document.catalog.get('AcroForm') or document.catalog.get('Perms'):raise ValueError(tr('Formulare und signierte PDFs werden nicht verändert. Bitte eine normale PDF-Kopie verwenden.'))
    if not 1<=len(document)<=100:raise ValueError(tr('Bitte eine PDF mit 1 bis 100 Seiten verwenden.'))
    for index,attrs in enumerate(document.pages):
        for reference in document.resolve(attrs.get('Annots',[])):
            annotation=document.resolve(reference)
            if annotation.get('Subtype')!='Link' or annotation.get('AP'):raise ValueError(tr('PDF-Anmerkungen zuerst in einer separaten Kopie entfernen, damit die Übersetzung keine Markierungen verändert.'))
        page=Page(document,index);groups=_segments(page)
        if not groups and page.image_count:raise ValueError(tr('Diese PDF enthält Bildseiten ohne Textschicht. Zuerst OCR ausführen; Bildtext wird nicht automatisch übersetzt.'))
        for group in groups:
            total+=sum(len(p) for p in group['parts'])
            if total>MAX_CHARS or len(segments)>=1500:raise ValueError(tr('PDF enthält zu viel Text. Bitte in kleinere Dokumente teilen.'))
            segments.append(dict(id=str(len(segments)),page=index,**group))
    if not segments:raise ValueError(tr('Keine Textschicht gefunden. Bitte zuerst OCR ausführen.'))
    if fingerprint(path)!=stamp:raise ValueError(tr('Die Quelldatei wurde während des Lesens verändert.'))
    return dict(path=str(path),fingerprint=stamp,pages=len(document),segments=segments,characters=total,notice=tr('Text in Bildern bleibt unverändert. Längere Übersetzungen können kleinere Schrift benötigen.'))


def _without_text(data):
    from lumen_pdf import Syntax,Operator,serialize
    syntax=Syntax(data);start=0;operands=[];output=bytearray()
    while True:
        syntax.skip()
        if syntax.pos==len(data):break
        value=syntax.value()
        if not isinstance(value,Operator):operands.append(value);continue
        if value in ('Tj','TJ'):pass
        elif value=="'":output.extend(b'T*\n')
        elif value=='"':output.extend(serialize(operands[0])+b' Tw '+serialize(operands[1])+b' Tc T*\n')
        else:output.extend(data[start:syntax.pos]+b'\n')
        start=syntax.pos;operands=[]
    return bytes(output)


def write(manifest,translations,output):
    import zlib
    from lumen_pdf import Document,Writer,Stream,Ref,Name,decoded
    from lumen_pdf_text import TextWriter
    source=Path(manifest['path']);target=Path(output)
    if target.suffix.lower()!='.pdf' or target.exists() or target.is_symlink() or source.resolve()==target.resolve():raise ValueError(tr('Bitte einen neuen PDF-Dateinamen wählen. Vorhandene Dateien werden nicht überschrieben.'))
    current=inspect(source)
    if current['fingerprint']!=manifest['fingerprint'] or current['segments']!=manifest['segments']:raise ValueError(tr('Die Quelldatei wurde verändert. Bitte erneut übersetzen.'))
    if not isinstance(translations,dict) or set(translations)!={s['id'] for s in current['segments']}:raise ValueError(tr('Die Übersetzung ist unvollständig. Es wurde keine PDF gespeichert.'))
    for segment in current['segments']:
        parts=translations[segment['id']]
        if not isinstance(parts,list) or len(parts)!=len(segment['parts']) or any(not isinstance(p,str) or (o.strip() and not p.strip()) or len(p)>30000 for p,o in zip(parts,segment['parts'])):raise ValueError(tr('Ungültige Übersetzung für die PDF.'))
    document=Document(source);writer=Writer();text=TextWriter(writer);reduced=[]
    def resolve(value):return writer.objects[value.number-1] if isinstance(value,Ref) else value
    for index in range(len(document)):
        page=writer.copy_page(document,index);page['Contents']=writer.stream(b'q\n'+_without_text(document.contents(index))+b'\nQ\n')
        resources=dict(resolve(page.get('Resources')) or {});resources['Font']=dict(resolve(resources.get('Font')) or {});page['Resources']=resources
        for segment in (s for s in current['segments'] if s['page']==index):
            scale=text.box(page,segment['rect'],translations[segment['id']],segment['styles'],angle=segment.get('angle',0))
            if scale<.99:reduced.append(dict(page=index+1,block=segment['id'],scale=round(scale,3)))
    # Only page/form content streams are transformed; images/vectors/links survive.
    # Remove orphaned original page streams as well; they are not needed in output.
    main_streams=set()
    for attrs in document.pages:
        values=attrs.get('Contents');resolved=document.resolve(values);values=resolved if isinstance(resolved,list) else [values]
        for value in values:
            if isinstance(value,Ref) and (document,value) in writer.imported:main_streams.add(writer.imported[(document,value)].number)
    for number,value in enumerate(writer.objects,1):
        if isinstance(value,Stream) and (number in main_streams or value.attrs.get('Subtype')=='Form'):
            data=_without_text(decoded(value,resolve));attrs={k:v for k,v in value.attrs.items() if k not in ('Length','Filter','DecodeParms')};attrs['Filter']=Name('FlateDecode');writer.objects[number-1]=Stream(attrs,zlib.compress(data))
    text.finalize()
    if fingerprint(source)!=current['fingerprint']:raise ValueError(tr('Die Quelldatei wurde verändert. Bitte erneut übersetzen.'))
    writer.save(target)
    return dict(path=str(target),pages=current['pages'],reduced=reduced,notice=current['notice'])


def export_copy(source, output, job):
    target = Path(output)
    if target.suffix.lower() != '.pdf' or target.exists() or target.is_symlink():
        raise ValueError(tr('Bitte einen neuen PDF-Dateinamen wählen. Vorhandene Dateien werden nicht überschrieben.'))
    with tempfile.NamedTemporaryFile(prefix='.lumen-translate-', suffix='.pdf', dir=target.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            with Path(source).open('rb') as input:
                while chunk := input.read(1024**2): job.check(); stream.write(chunk)
            stream.flush(); os.fsync(stream.fileno()); job.check(); os.link(temp, target)
        finally: temp.unlink(missing_ok=True)
    return str(target)


def worker(job, action, **values):
    output = job.command([sys.executable, str(Path(__file__))], json.dumps(dict(action=action, **values), ensure_ascii=False).encode(), timeout=180, max_output=4*1024**2)
    return json.loads(output)


if __name__ == '__main__':
    from lumen_pdf_worker import limits
    limits()
    try:
        request = json.load(sys.stdin); action = request.pop('action')
        if action == 'inspect': result = inspect(**request)
        elif action == 'write': result = write(**request)
        else: raise ValueError('Unknown PDF action')
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
