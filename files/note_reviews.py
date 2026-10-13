"""Reviewed notebook edits: references, exact previews and conflict-safe history."""
import json
import os
import time
from uuid import uuid4
from urllib.parse import quote
from lumen_i18n import tr
from wissen_data import Notebook


def rows(store):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS note_reviews (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        return [json.loads(r['data']) for r in db.execute("SELECT data FROM note_reviews ORDER BY json_extract(data,'$.state')='pending' DESC,rowid DESC LIMIT 200")]


def shared(store, book, path, memory=None):
    from lumen_memory import Memory, options
    if not options(store)['enabled'] or not (memory or Memory(store)).shared(book, path):
        raise ValueError(tr('Notiz ist nicht mehr für Lumen freigegeben.'))
    return book.read(path)


def propose(store, path, revision, reason, text=None, targets=()):
    if not isinstance(reason, str) or not reason.strip() or len(reason)>2000:
        raise ValueError(tr('Bitte den Zusammenhang begründen.'))
    if not 0 <= len(targets) <= 8 or (text is None and not targets):
        raise ValueError(tr('Eine bis acht Zielnotizen angeben.'))
    book=Notebook(store); source=shared(store, book, path)
    if source['hash'] != revision: raise ValueError(tr('Notiz inzwischen geändert. Bitte erneut lesen.'))
    refs=[]; links=[]
    for target in dict.fromkeys(targets):
        if target == path: raise ValueError(tr('Eine Notiz kann nicht mit sich selbst verknüpft werden.'))
        note=shared(store, book, target); refs.append(dict(path=target, title=note['title'], hash=note['hash']))
        url='/?document='+note['note_id'] if note.get('note_id') else quote(os.path.relpath(target, os.path.dirname(path) or '.'), safe='/')
        label=note['title'].replace('\\','\\\\').replace('[','\\[').replace(']','\\]').replace('\n',' ')
        link='['+label+']('+url+')'
        if ']('+url+')' not in source['text']: links.append('- '+link)
    if targets and not links: raise ValueError(tr('Diese Verknüpfungen bestehen bereits.'))
    after=source['text'].rstrip()+'\n\n'+'\n'.join(links) if targets else text
    if not isinstance(after,str) or max(len(after),len(source['text']))>16000:
        raise ValueError(tr('Vorschauen unterstützen Notizen bis 16.000 Zeichen.'))
    if after == source['text']: raise ValueError(tr('Keine Änderung vorgeschlagen.'))
    item=dict(id=uuid4().hex, root=str(book.root), identity=book.identity, path=path, title=source['title'],
              before=source['text'], after=after, revision=revision, reason=reason, targets=refs,
              created=time.time(), state='pending', origin='Lumen MCP')
    existing=rows(store)
    if sum(r['state']=='pending' for r in existing)>=50: raise ValueError(tr('Bitte zuerst offene Vorschläge prüfen.'))
    duplicate=next((r for r in existing if r['state']=='pending' and all(r[k]==item[k] for k in ('root','identity','path','revision','after','targets'))),None)
    if duplicate:return dict(id=duplicate['id'],state='pending',review='Lumen → Vorschläge & Verlauf')
    with store.connect() as db: db.execute('INSERT INTO note_reviews VALUES (?,?)',(item['id'],json.dumps(item)))
    return dict(id=item['id'],state='pending',review='Lumen → Vorschläge & Verlauf')


def decide(store, identity, action):
    if action not in ('apply','reject','undo'):raise ValueError('Invalid review action')
    rows(store)
    from lumen_memory import Memory
    memory=Memory(store)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        record=db.execute('SELECT data FROM note_reviews WHERE id=?',(identity,)).fetchone()
        if not record:raise ValueError(tr('Vorschlag nicht gefunden.'))
        item=json.loads(record['data'])
        if item['state'] != ('applied' if action=='undo' else 'pending'):
            raise ValueError(tr('Vorschlag bereits abgeschlossen.'))
        if action=='reject':item['state']='revoked'
        else:
            book=Notebook(store)
            if str(book.root)!=item['root'] or list(book.identity)!=list(item['identity']):
                raise ValueError(tr('Der Notizordner wurde gewechselt.'))
            if action=='apply':
                if time.time()-item['created']>86400:raise ValueError(tr('Vorschlag abgelaufen. Bitte neu erstellen.'))
                shared(store,book,item['path'],memory)
                for target in item['targets']:
                    if shared(store,book,target['path'],memory)['hash']!=target['hash']:
                        raise ValueError(tr('Verknüpfungsziel geändert. Bitte neu prüfen.'))
            expected=item['revision'] if action=='apply' else item['applied_hash']
            result=book.write(item['path'],item['after'] if action=='apply' else item['before'],expected)
            item['state']='applied' if action=='apply' else 'undone';item['applied_hash']=result['hash']
        item['decided']=time.time()
        db.execute('UPDATE note_reviews SET data=? WHERE id=?',(json.dumps(item),identity))
    return item


def show_reviews(panel):
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPlainTextEdit, QLabel, QPushButton
    from PySide6.QtCore import Qt
    from datetime import datetime
    store=panel.tracker.store
    dialog=QDialog(panel);dialog.setWindowTitle(tr('Lumen · Vorschläge & Verlauf'));dialog.resize(880,650)
    box=QVBoxLayout(dialog);title=QLabel(tr('Was würde passieren?'));box.addWidget(title)
    hint=QLabel(tr('Prüfe Notizänderungen und Zusammenhänge. Erst „Übernehmen“ verändert deine Notiz.'));hint.setWordWrap(True);box.addWidget(hint)
    listing=QListWidget();listing.setMaximumHeight(140);listing.setAccessibleName(tr('Vorschläge und Verlauf'));box.addWidget(listing)
    comparison=QHBoxLayout();before=QPlainTextEdit();after=QPlainTextEdit()
    for heading,editor in ((tr('Bisher'),before),(tr('Vorgeschlagene Fassung'),after)):
        col=QVBoxLayout();col.addWidget(QLabel(heading));editor.setReadOnly(True);editor.setAccessibleName(heading);col.addWidget(editor);comparison.addLayout(col)
    box.addLayout(comparison,1);why=QLabel();why.setTextFormat(Qt.PlainText);why.setWordWrap(True);box.addWidget(why)
    error=QLabel();error.setTextFormat(Qt.PlainText);error.setWordWrap(True);box.addWidget(error)
    actions=QHBoxLayout();box.addLayout(actions)
    buttons={}
    def load():
        listing.clear()
        for item in rows(store):
            listing.addItem(item['title']+' · '+tr({'pending':'Wartet auf deine Freigabe','applied':'Übernommen','revoked':'Abgelehnt','undone':'Rückgängig gemacht'}[item['state']]))
            listing.item(listing.count()-1).setData(Qt.UserRole,item)
        if listing.count():listing.setCurrentRow(0)
        else:error.setText(tr('Noch keine Vorschläge. Bitte Lumen, eine Notizänderung vorab zu prüfen oder passende Notizen zu verknüpfen.'))
    def select(current, previous=None):
        item=current.data(Qt.UserRole) if current else None
        before.setPlainText(item['before'] if item else '');after.setPlainText(item['after'] if item else '')
        why.setText((tr('Warum ist das so?')+'\n'+tr('Begründung des Vorschlags')+': '+item['reason']+'\n'+item['path']+' · '+datetime.fromtimestamp(item['created']).strftime('%d.%m.%Y %H:%M')+' · '+item['origin']+'\n'+tr('Ausgangsfassung')+': '+item['revision'][:12]+(' · '+tr('Letzte Entscheidung')+': '+datetime.fromtimestamp(item['decided']).strftime('%d.%m.%Y %H:%M') if item.get('decided') else '')+'\n'+tr('Das gehört zusammen')+': '+', '.join(t['title'] for t in item['targets'])) if item else '')
        for action,button in buttons.items():button.setEnabled(bool(item) and item['state']==('applied' if action=='undo' else 'pending'))
    def act(action):
        if not listing.currentItem():return
        try:decide(store,listing.currentItem().data(Qt.UserRole)['id'],action);error.clear();load()
        except (ValueError,OSError) as exc:error.setText(str(exc))
    for action,text in (('apply','Genau so übernehmen'),('reject','Ablehnen'),('undo','Änderung rückgängig machen')):
        button=QPushButton(tr(text));button.clicked.connect(lambda checked=False,a=action:act(a));buttons[action]=button;actions.addWidget(button)
    refresh=QPushButton(tr('Aktualisieren'));refresh.clicked.connect(load);actions.addWidget(refresh)
    close=QPushButton(tr('Schließen'));close.clicked.connect(dialog.reject);actions.addWidget(close)
    listing.currentItemChanged.connect(select);load();select(listing.currentItem());dialog.exec()
