"""Previewed notebook moves with source-preserving link edits and restart recovery."""
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import quote,unquote,urlsplit
from lumen_i18n import tr
from note_tags import body_mask
from wissen_data import digest,resolve_link,draft,MAX_NOTE


def mapped(path,source,target):
    return str(Path(target)/Path(path).relative_to(source)) if Path(path).is_relative_to(source) else path


def rewrite(text,origin,source,target,notes):
    destination=mapped(origin,source,target);mask=body_mask(text)
    # shortcut: reference-style and HTML links need a source-offset parser before migration.
    for match in re.finditer(r'(?m)^ {0,3}\[[^]\n]+\]:|<[^>]*(?:href|src)\s*=',text):
        if mask[match.start():match.end()].strip():raise ValueError(tr('Referenz- oder HTML-Links zuerst in direkte Markdown-Links umwandeln.'))
    pattern=r'(?<!\\)(!?\[\[([^\]\n]+)\]\]|!?\[[^\]\n]*\]\(((?:[^()\n]|\([^()\n]*\))+)\))'
    def change(match):
        if not mask[match.start():match.start()+1].strip():return match[0]
        raw=match[2] or match[3];suffix='';angled=False
        if match[3]:
            destination_match=re.fullmatch('(<[^>]*>|[^\\s]+)([ \\t]+(?:"[^"]*"|\'[^\']*\'))?',raw)
            if not destination_match:raise ValueError(tr('Ein Markdown-Link verwendet eine nicht unterstützte Schreibweise. Vor dem Verschieben korrigieren.'))
            raw=destination_match[1];suffix=destination_match[2] or '';angled=raw.startswith('<')
            if angled:raw=raw[1:-1]
        base,aliasmark,alias=raw.partition('|');path,anchor_mark,anchor=base.partition('#')
        if not path or path.startswith('/?document=') or urlsplit(unquote(path)).scheme:return match[0]
        resolved=resolve_link(origin,base,notes)
        if resolved is None:
            # Preserve relative attachments when their containing note is moved.
            if match[2] and not match[0].startswith('!'):return match[0]
            resolved=os.path.normpath(str(Path(origin).parent/unquote(path)))
            if resolved.startswith(('/', '../')) or resolved=='..':return match[0]
        new=mapped(resolved,source,target)
        if new==resolved and destination==origin:return match[0]
        relative=os.path.relpath(new,str(Path(destination).parent))
        value=quote(relative,safe='/')+('#'+anchor if anchor_mark else '')+('|'+alias if aliasmark else '')
        if angled:value='<'+value+'>'
        value+=suffix
        return match[0][:match.start(2 if match[2] else 3)-match.start()]+value+match[0][match.end(2 if match[2] else 3)-match.start():]
    return re.sub(pattern,change,text)


def key(book):return 'knowledge/move/'+digest(str(book.root).encode())


def pending(book):return book.store.setting(key(book),None)


def plan(book,source,target):
    from drive_local import relative
    source=str(relative(source));target=str(relative(target))
    if source==target or source=='.' or target=='.' or any(p.startswith('.') for p in Path(source).parts+Path(target).parts):raise ValueError(tr('Ungültiges Verschiebeziel.'))
    with book.directory(Path(target).parent) as parent:
        try:os.stat(Path(target).name,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise ValueError(tr('Das Ziel ist bereits vorhanden.'))
    if Path(source).suffix.lower()=='.md':book.read(source);book.relative(target)
    else:
        with book.directory(source):pass
        if Path(target).is_relative_to(source):raise ValueError(tr('Eine Sammlung kann nicht in sich selbst verschoben werden.'))
    scan=book.scan()
    if scan['limited'] or scan['errors']:raise ValueError(tr('Zuerst alle Notizen vollständig und fehlerfrei einlesen.'))
    notes={n['path']:n for n in scan['notes']};changes=[]
    for path,note in notes.items():
        after=rewrite(note['text'],path,source,target,notes)
        if after!=note['text'] or mapped(path,source,target)!=path:
            saved=draft(book.store,book.root,path)
            if saved and saved['text']!=note['text']:raise ValueError(tr('Eine betroffene Notiz hat einen lokalen Entwurf. Zuerst speichern oder auflösen.'))
            before=book.raw(path)
            if digest(before)!=note['hash']:raise ValueError(tr('Notizen wurden geändert. Vorschau erneut öffnen.'))
            body=note['text'].encode();raw_after=before[:-len(body)]+after.encode() if body else before+after.encode()
            if len(raw_after)>MAX_NOTE:raise ValueError(tr('Eine Notiz würde durch die Linkänderungen zu groß.'))
            changes.append(dict(path=path,destination=mapped(path,source,target),before=before.decode(),after=raw_after.decode()))
    info=exists(book,source)
    value=dict(source=source,target=target,identity=book.identity,folder_id=[info.st_dev,info.st_ino] if Path(source).suffix.lower()!='.md' else None,changes=changes,hashes={p:n['hash'] for p,n in notes.items()})
    if len(json.dumps(value).encode())>4*1024**2:raise ValueError(tr('Zu viele Änderungen für einen Vorgang. Bitte in kleineren Schritten verschieben.'))
    return value


def share_rules(book,value,rules):
    def local(rule):return rule['root']==str(book.root) and rule['identity']==book.identity
    def allowed(path,values):
        matched=[r for r in values if local(r) and ((r['directory'] and Path(path).is_relative_to(r['path'])) or (not r['directory'] and r['path']==path))]
        matched.sort(key=lambda r:(len(Path(r['path']).parts),not r['directory']))
        return bool(matched and matched[-1]['allow'])
    result=[dict(r,path=mapped(r['path'],value['source'],value['target'])) if local(r) else r for r in rules]
    for change in value['changes']:
        old,new=change['path'],change['destination']
        if old!=new and allowed(old,rules)!=allowed(new,result):
            result.append(dict(root=str(book.root),identity=book.identity,path=new,directory=False,allow=allowed(old,rules)))
    if len(result)>500:raise ValueError(tr('Zu viele individuelle Freigaben. Bitte die Freigaben vor dem Verschieben vereinfachen.'))
    return result


def exists(book,path):
    with book.directory(Path(path).parent) as parent:
        try:return os.stat(Path(path).name,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:return None


def position(book,value):
    before=exists(book,value['source']);after=exists(book,value['target'])
    if bool(before)==bool(after):raise ValueError(tr('Quelle oder Ziel wurde verändert. Wiederherstellung zuerst prüfen.'))
    present=after or before
    if value.get('folder_id') and [present.st_dev,present.st_ino]!=value['folder_id']:raise ValueError(tr('Der betroffene Ordner wurde ersetzt.'))
    return bool(after)


def raw_write(book,path,before,after):
    if before==after:return
    if book.raw(path)!=before:raise ValueError(tr('Notizen wurden geändert. Vorschau erneut öffnen.'))
    book.backup(path,before)
    with book.directory(Path(path).parent) as parent:
        temporary='.lumen-move-'+uuid.uuid4().hex
        fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(after);stream.flush();os.fsync(stream.fileno())
            if book.raw(path)!=before:raise ValueError(tr('Notizen wurden während des Verschiebens geändert.'))
            os.replace(temporary,Path(path).name,src_dir_fd=parent,dst_dir_fd=parent);os.fsync(parent)
        finally:
            try:os.unlink(temporary,dir_fd=parent)
            except FileNotFoundError:pass


def set_shares(book,rules):
    from memory_local import invalidate
    book.store.set_setting('memory/shares',rules)
    invalidate(book.store.directory/'memory-index')
    for name in ('memory/revision','memory/privacy_revision'):
        book.store.set_setting(name,book.store.setting(name,0)+1)


def execute(book,value=None,rollback=False):
    from drive_local import move
    with book.lock('wissen-sync.lock'),book.lock(),book.lock('memory-state.lock'):
        saved=pending(book)
        if value is not None:
            if saved:raise ValueError(tr('Zuerst den offenen Verschiebevorgang fortsetzen oder zurücknehmen.'))
            if plan(book,value['source'],value['target'])!=value:raise ValueError(tr('Notizen wurden geändert. Vorschau erneut öffnen.'))
            value=dict(value,shares_before=book.store.setting('memory/shares',[]))
            value['shares_after']=share_rules(book,value,value['shares_before'])
            value['shares_paused']=list(value['shares_before'])
            for change in value['changes']:
                if change['path']!=change['destination']:
                    for path in (change['path'],change['destination']):
                        value['shares_paused'].append(dict(root=str(book.root),identity=book.identity,path=path,allow=False,directory=False))
            value['mode']='forward';book.store.set_setting(key(book),value)
        else:
            value=saved
            if not value:raise ValueError(tr('Kein offener Verschiebevorgang.'))
        if value['identity']!=book.identity:raise ValueError(tr('Der Notizordner wurde ersetzt oder getrennt. Erneut auswählen.'))
        if rollback:value['mode']='rollback';book.store.set_setting(key(book),value)
        rollback=value['mode']=='rollback';moved=position(book,value)
        shares=book.store.setting('memory/shares',[])
        if shares not in (value['shares_before'],value['shares_after'],value['shares_paused']):raise ValueError(tr('Freigaben wurden verändert. Wiederherstellung zuerst prüfen.'))
        for change in value['changes']:
            path=change['destination'] if moved else change['path'];raw=book.raw(path)
            if raw not in (change['before'].encode(),change['after'].encode()):raise ValueError(tr('Eine betroffene Notiz wurde geändert. Beide Fassungen bleiben in der Wiederherstellung erhalten.'))
        if not rollback:
            scan=book.scan();actual={n['path']:n['hash'] for n in scan['notes']}
            expected={mapped(p,value['source'],value['target']) if moved else p:h for p,h in value['hashes'].items()}
            changed={c['destination'] if moved else c['path'] for c in value['changes']}
            if scan['limited'] or scan['errors'] or set(actual)!=set(expected) or any(actual[p]!=h for p,h in expected.items() if p not in changed):
                raise ValueError(tr('Weitere Notizen wurden verändert. Vorgang zurücknehmen und neu vorbereiten.'))
        set_shares(book,value['shares_paused'])
        for change in value['changes']:
            path=change['destination'] if moved else change['path'];raw=book.raw(path)
            raw_write(book,path,raw,change['before' if rollback else 'after'].encode())
        if moved==rollback:
            source,target=(value['target'],value['source']) if rollback else (value['source'],value['target'])
            with book.directory() as fd:
                st=os.fstat(fd);move(dict(path=str(book.root),identity=[st.st_dev,st.st_ino]),source,target)
        set_shares(book,value['shares_before' if rollback else 'shares_after'])
        # Keep the last transaction for a guarded undo even after restarting.
        book.store.set_setting(key(book)+'/last',None if rollback else value)
        book.store.set_setting(key(book),None)
        return dict(scan=book.scan(),path=value['source'] if rollback else value['target'],changed=len(value['changes']))


def undo(book):
    with book.lock('wissen-sync.lock'):
        if not pending(book):
            value=book.store.setting(key(book)+'/last',None)
            if not value:raise ValueError(tr('Kein Verschiebevorgang zum Zurücknehmen.'))
            if not position(book,value):raise ValueError(tr('Der letzte Vorgang wurde bereits zurückgenommen.'))
            if book.store.setting('memory/shares',[])!=value['shares_after']:raise ValueError(tr('Freigaben wurden verändert. Wiederherstellung zuerst prüfen.'))
            for change in value['changes']:
                if book.raw(change['destination'])!=change['after'].encode():raise ValueError(tr('Eine betroffene Notiz wurde geändert. Rücknahme würde Änderungen überschreiben.'))
            book.store.set_setting(key(book),value)
    return execute(book,rollback=True)


def completed(window,result,source='',target=''):
    current=window.doc['path'] if window.doc else ''
    chosen=mapped(current,source,target) if current and source else result['path']
    if window.collection.startswith('folder:') and source:window.collection='folder:'+mapped(window.collection[7:],source,target)
    window.scanned(result['scan']);window.refresh()
    if chosen in window.notes:window.show_note(window.notes[chosen])
    window.status.setText(tr('Verschieben abgeschlossen · Verknüpfungen erhalten.'))


def review(window,source=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QInputDialog,QMessageBox
    import difflib
    if window.area!='user' or not window.book:return
    if window.dirty:window.save_note(lambda:review(window,source));return
    if pending(window.book):recover(window);return
    source=source or (window.doc['path'] if window.doc else '')
    if not source:return
    target,ok=QInputDialog.getText(window,tr('Lumen Notes · Verschieben'),tr('Neuer Pfad im Notizbuch · Zielordner muss bereits bestehen'),text=source)
    if not ok or target==source:return
    def preview(value):
        dialog=QMessageBox(window);dialog.setWindowTitle(tr('Lumen Notes · Verschieben prüfen'));dialog.setTextFormat(Qt.PlainText)
        dialog.setText(source+' → '+target)
        dialog.setInformativeText(tr('{0} Notizen betroffen. Verknüpfungen werden angepasst. Freigaben bleiben erhalten; der letzte Vorgang kann zurückgenommen werden.',len(value['changes'])))
        details=[]
        for change in value['changes']:
            details.append(change['path']+' → '+change['destination']+'\n')
            details.extend(difflib.unified_diff(change['before'].splitlines(keepends=True),change['after'].splitlines(keepends=True)))
        dialog.setDetailedText(''.join(details)[:100000]);dialog.setStandardButtons(QMessageBox.Apply|QMessageBox.Cancel);dialog.setDefaultButton(QMessageBox.Cancel)
        if dialog.exec()!=QMessageBox.Apply:return
        launch=lambda:window.action('move_apply',lambda result:completed(window,result,source,target),value=value)
        if window.job:window.after_job=launch
        else:launch()
    window.action('move_plan',preview,source=source,target=target)


def recover(window,rollback=False):
    if window.area!='user' or not window.book:return
    if window.dirty:window.save_note(lambda:recover(window,rollback));return
    value=pending(window.book) or window.book.store.setting(key(window.book)+'/last',None)
    source,target=(value['target'],value['source']) if value and rollback else (value['source'],value['target']) if value else ('','')
    window.action('move_undo' if rollback else 'move_resume',lambda result:completed(window,result,source,target))
