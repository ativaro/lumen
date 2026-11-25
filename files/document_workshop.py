"""PDF workshop on Lumen's document core; immutable sources and atomic exports."""
from pathlib import Path
import json
import os
import subprocess
import sys
from lumen_i18n import tr
from lumen_office import message, program, signature


def core(*arguments):
    """The answer of the document core; its reason, translated, when it refuses."""
    try:result=subprocess.run([program(),*arguments],capture_output=True,stdin=subprocess.DEVNULL,timeout=120)
    except subprocess.TimeoutExpired as error:raise ValueError(tr('Die Verarbeitung hat zu lange gedauert.')) from error
    if result.returncode:
        reason=result.stderr.decode(errors='replace').strip()
        if 'PDF-Passwort' in reason:raise ValueError(tr('Bitte eine unverschlüsselte PDF mit höchstens 2.000 Seiten verwenden.'))
        raise ValueError(message(reason))
    return result.stdout


def inspect(paths):
    pages=[]
    for path in paths:
        source=Path(path)
        if source.is_symlink() or not source.is_file() or source.stat().st_size>512*1024**2:
            raise ValueError(tr('PDF nicht verfügbar, verknüpft oder größer als 512 MiB.'))
        before=signature(path);info=json.loads(core('pdf-cli','info',str(path)))
        if info['encrypted'] or not 1<=info['pages']<=2000:raise ValueError(tr('Bitte eine unverschlüsselte PDF mit höchstens 2.000 Seiten verwenden.'))
        pages.extend(dict(path=path,page=i,rotation=0,boxes=[],stamp=before) for i in range(info['pages']))
        if signature(path)!=before:raise ValueError(tr('Quelldatei während Lesen verändert.'))
    if len(pages)>2000:raise ValueError(tr('Höchstens 2.000 Seiten pro Arbeitsmappe.'))
    return pages


def render(item,target):
    if signature(item['path'])!=item['stamp']:raise ValueError(tr('Eine Quelldatei wurde verändert. Bitte neu öffnen.'))
    if type(item['page']) is not int or type(item['rotation']) is not int:raise ValueError(tr('Ungültige Seitenauswahl oder Qualität.'))
    core('pdf-cli','render',str(item['path']),'--page',str(item['page']),'--rotation',str(item['rotation']),'--scale-to','1400','--max-scale','2','--output',str(target))
    if signature(item['path'])!=item['stamp']:raise ValueError(tr('Quelldatei während Lesen verändert.'))
    return str(target)


def export(pages,target,ocr=False,dpi=200,progress=lambda _:None):
    """Copies, reorders and turns pages into a new file; a redaction rasterises every page. One progress line per page."""
    import threading
    if not isinstance(pages,list) or not 1<=len(pages)<=2000 or dpi not in (150,200,300):raise ValueError(tr('Ungültige Seitenauswahl oder Qualität.'))
    target=Path(target).absolute()
    if os.path.lexists(target):raise FileExistsError(tr('Die PDF-Zieldatei existiert bereits.'))
    request=json.dumps(dict(pages=[dict(item,path=str(Path(item['path']).absolute())) for item in pages],target=str(target),dpi=dpi,
                            **({'ocr':__import__('lumen_ocr').languages()} if ocr else {})))
    with subprocess.Popen([program(),'pdf-export'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as process:
        errors=[];reader=threading.Thread(target=lambda:errors.append(process.stderr.read()));reader.start()
        process.stdin.write(request);process.stdin.close()
        for line in process.stdout:progress(line.strip())
        reader.join()
    if process.returncode:raise ValueError(message(errors[0].strip()[:600]) if errors and errors[0].strip() else tr('PDF-Exportprüfung fehlgeschlagen.'))
    return str(target)


if __name__ == '__main__':
    from lumen_office import limits
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
