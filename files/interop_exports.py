"""Atomic portable exports of explicitly selected Lumen content."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from lumen_i18n import tr
from interop_data import validate_payload


def export_payload(payload,destination,job):
    payload=validate_payload(payload);parent=Path(destination).resolve(strict=True)
    if not parent.is_dir():raise ValueError(tr('Einen vorhandenen Zielordner wählen.'))
    title=re.sub(r'[^\w .-]','_',payload['title']).strip(' .')[:80] or 'Lumen'
    final=parent/(title+'-'+uuid.uuid4().hex[:8]);total=0;count=0;manifest=[]
    with tempfile.TemporaryDirectory(prefix='.lumen-export-',dir=parent) as tmp:
        stage=Path(tmp);(stage/'files').mkdir(mode=0o700)
        text=payload.get('text','')
        if payload.get('source_url'):text+='\n\n'+tr('Quelle: ')+payload['source_url']
        (stage/'document.md').write_text('# '+payload['title']+'\n\n'+text,encoding='utf-8');(stage/'document.md').chmod(0o600)
        for index,source in enumerate(payload.get('paths',[])):
            source=Path(source)
            if source.is_symlink() or not source.is_file():raise ValueError(tr('Nur reguläre ausgewählte Dateien exportieren.'))
            before=source.stat();name=f'{index+1:03d}-'+source.name;target=stage/'files'/name;digest=hashlib.sha256()
            with source.open('rb') as inp,target.open('xb') as out:
                target.chmod(0o600)
                while data:=inp.read(1024*1024):
                    job.check();total+=len(data)
                    if total>512*1024**2:raise ValueError(tr('Export größer als 512 MiB. Bitte die Auswahl verkleinern.'))
                    out.write(data);digest.update(data)
                out.flush();os.fsync(out.fileno())
            after=source.stat()
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                raise ValueError(tr('Eine Quelldatei wurde während des Exports verändert.'))
            manifest.append(dict(name=source.name,file='files/'+name,sha256=digest.hexdigest(),size=after.st_size))
        (stage/'manifest.json').write_text(json.dumps(dict(version=1,title=payload['title'],source=payload.get('source_url',''),files=manifest,items=payload.get('items',[])),ensure_ascii=False,indent=2),encoding='utf-8')
        (stage/'manifest.json').chmod(0o600);job.check()
        stage.rename(final)
    return str(final)
