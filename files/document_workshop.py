"""PDF workshop using Lumen's own engine; immutable sources and atomic exports."""
from pathlib import Path
import json
import sys
from lumen_i18n import tr
from lumen_pdf import Document,integer
from lumen_pdf_page import Page
from lumen_pdf_worker import signature,export as pdf_export


def opened(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>512*1024**2:
        raise ValueError(tr('PDF nicht verfügbar, verknüpft oder größer als 512 MiB.'))
    document=Document(path)
    if document.encrypted or not 1<=len(document)<=2000:raise ValueError(tr('Bitte eine unverschlüsselte PDF mit höchstens 2.000 Seiten verwenden.'))
    return document


def core(*arguments):
    """The answer of the document core, or None where it does not read the file; the Python engine reads it then."""
    import subprocess
    from lumen_office import program
    from lumen_pdf import PDFError
    try:result=subprocess.run([program(),'pdf-cli',*arguments],capture_output=True,stdin=subprocess.DEVNULL,timeout=120)
    except (PDFError,subprocess.TimeoutExpired):return None
    return None if result.returncode else result.stdout


def inspect(paths):
    pages=[]
    for path in paths:
        before=signature(path);info=core('info',str(path)) if Path(path).is_file() and not Path(path).is_symlink() and Path(path).stat().st_size<=512*1024**2 else None
        if info:
            info=json.loads(info);count=info['pages']
            if info['encrypted'] or not 1<=count<=2000:raise ValueError(tr('Bitte eine unverschlüsselte PDF mit höchstens 2.000 Seiten verwenden.'))
        else:count=len(opened(path))
        pages.extend(dict(path=path,page=i,rotation=0,boxes=[],stamp=before) for i in range(count))
        if signature(path)!=before:raise ValueError(tr('Quelldatei während Lesen verändert.'))
    if len(pages)>2000:raise ValueError(tr('Höchstens 2.000 Seiten pro Arbeitsmappe.'))
    return pages


def render(item,target):
    if signature(item['path'])!=item['stamp']:raise ValueError(tr('Eine Quelldatei wurde verändert. Bitte neu öffnen.'))
    drawn=type(item['page']) is int and type(item['rotation']) is int and core('render',str(item['path']),'--page',str(item['page']),'--rotation',str(item['rotation']),'--scale-to','1400','--max-scale','2','--output',str(target)) is not None
    if not drawn:
        document=opened(item['path']);page=Page(document,integer(item['page'],0,len(document)-1),item['rotation'])
        image=page.render(min(2,1400/max(page.width,page.height)))
    if signature(item['path'])!=item['stamp']:raise ValueError(tr('Quelldatei während Lesen verändert.'))
    if not drawn and not image.save(str(target),'PNG'):raise ValueError(tr('Vorschau konnte nicht gespeichert werden.'))
    return str(target)


def export(pages,target,ocr=False,dpi=200,progress=lambda _:None):
    return pdf_export(pages,target,dpi=dpi,ocr=ocr,progress=progress)


if __name__ == '__main__':
    import os
    from lumen_pdf_worker import limits
    os.setsid();limits()
    try:
        request = json.loads(sys.stdin.readline())
        def progress(message): print(json.dumps({'progress': message}), flush=True)
        if request['action'] == 'inspect': result = inspect(request['paths'])
        elif request['action'] == 'render': result = render(request['page'], request['target'])
        elif request['action'] == 'export': result = export(request['pages'], request['target'], request['ocr'], request['dpi'], progress)
        else: raise ValueError(tr('Unbekannte Dokumentenaktion.'))
        print(json.dumps({'result': result}), flush=True)
    except Exception as error: print(json.dumps({'error': str(error)}), flush=True); sys.exit(1)
