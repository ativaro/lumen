"""Read-only history of retired native note proposals; dismissal preserves originals."""
import json
import time
from lumen_i18n import tr


def rows(store):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS note_reviews (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        return [json.loads(r['data']) for r in db.execute("SELECT data FROM note_reviews ORDER BY json_extract(data,'$.state')='pending' DESC,rowid DESC LIMIT 200")]


def propose(store, path, revision, reason, text=None, targets=()):
    raise ValueError(tr('Notizänderungen werden auf dem Lumen Server vorgeschlagen. Lokale Notizvorschläge sind stillgelegt.'))


def decide(store, identity, action):
    if action != 'reject':
        raise ValueError(tr('Lokale Notizvorschläge sind nur noch Verlauf. Notizen direkt auf dem Lumen Server bearbeiten.'))
    rows(store)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        record=db.execute('SELECT data FROM note_reviews WHERE id=?',(identity,)).fetchone()
        if not record:raise ValueError(tr('Vorschlag nicht gefunden.'))
        item=json.loads(record['data'])
        if item['state'] != 'pending':raise ValueError(tr('Vorschlag bereits abgeschlossen.'))
        item['state']='revoked';item['decided']=time.time()
        db.execute('UPDATE note_reviews SET data=? WHERE id=?',(json.dumps(item),identity))
    return item


def show_reviews(panel):
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPlainTextEdit, QLabel, QPushButton
    from PySide6.QtCore import Qt
    from datetime import datetime
    store=panel.tracker.store
    dialog=QDialog(panel);dialog.setWindowTitle(tr('Lumen · Frühere Notizvorschläge'));dialog.resize(880,650)
    box=QVBoxLayout(dialog);title=QLabel(tr('Frühere Notizvorschläge'));box.addWidget(title)
    hint=QLabel(tr('Dieser Verlauf bleibt erhalten. Neue Notizvorschläge und Änderungen laufen über den Lumen Server. Lokale Originale bleiben unverändert.'));hint.setWordWrap(True);box.addWidget(hint)
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
        else:error.setText(tr('Keine früheren lokalen Notizvorschläge vorhanden.'))
    def select(current, previous=None):
        item=current.data(Qt.UserRole) if current else None
        before.setPlainText(item['before'] if item else '');after.setPlainText(item['after'] if item else '')
        why.setText((tr('Warum ist das so?')+'\n'+tr('Begründung des Vorschlags')+': '+item['reason']+'\n'+item['path']+' · '+datetime.fromtimestamp(item['created']).strftime('%d.%m.%Y %H:%M')+' · '+item['origin']+'\n'+tr('Ausgangsfassung')+': '+item['revision'][:12]+(' · '+tr('Letzte Entscheidung')+': '+datetime.fromtimestamp(item['decided']).strftime('%d.%m.%Y %H:%M') if item.get('decided') else '')+'\n'+tr('Das gehört zusammen')+': '+', '.join(t['title'] for t in item['targets'])) if item else '')
        for action,button in buttons.items():button.setEnabled(bool(item) and item['state']==('applied' if action=='undo' else 'pending'))
    def act(action):
        if not listing.currentItem():return
        try:decide(store,listing.currentItem().data(Qt.UserRole)['id'],action);error.clear();load()
        except (ValueError,OSError) as exc:error.setText(str(exc))
    for action,text in (('reject','Früheren Vorschlag schließen'),):
        button=QPushButton(tr(text));button.clicked.connect(lambda checked=False,a=action:act(a));buttons[action]=button;actions.addWidget(button)
    refresh=QPushButton(tr('Aktualisieren'));refresh.clicked.connect(load);actions.addWidget(refresh)
    close=QPushButton(tr('Schließen'));close.clicked.connect(dialog.reject);actions.addWidget(close)
    listing.currentItemChanged.connect(select);load();select(listing.currentItem());dialog.exec()
