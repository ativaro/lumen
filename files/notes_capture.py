"""Daily notes and explicit template copies in the currently selected notebook."""
from datetime import date,datetime
from pathlib import Path
import re
import uuid
from lumen_i18n import tr
from note_tags import FRONT


def render_template(text,title,now):
    values={'title':title,'date':now.date().isoformat(),'time':now.strftime('%H:%M')}
    # One substitution pass: user text can never become executable template code.
    return re.sub(r'\{\{\s*(title|date|time)\s*\}\}',lambda match:values[match[1]],text)


def daily(book,day,text=''):
    parsed=date.fromisoformat(day)
    if parsed.isoformat()!=day:raise ValueError(tr('Ungültiges Datum.'))
    path='Journal/'+day+'.md'
    with book.lock('notes-daily.lock'):
        try:return book.read(path)
        except FileNotFoundError:pass
        try:book.create_collection('Journal')
        except FileExistsError:pass
        return book.write(path,'# '+day+'\n\n'+text,'',note_id=str(uuid.uuid4()))


def from_template(book,title,template='',expected='',text='',folder='.'):
    title=' '.join(title.split()).strip()[:200]
    if not title:raise ValueError(tr('Bitte einen Titel eingeben.'))
    if template:
        source=book.read(template)
        if source['hash']!=expected:raise ValueError(tr('Die Vorlage wurde geändert. Bitte erneut auswählen.'))
        text=source['text']
    if len(text.encode())>1024*1024:raise ValueError(tr('Vorlage zu groß.'))
    text=render_template(text,title,datetime.now().astimezone())
    # Keep frontmatter at the beginning, including unknown metadata.
    front=FRONT.match(text);prefix=front[0] if front else '';body=text[len(prefix):].lstrip('\n')
    match=re.match(r'^# [^\n]*(?:\n|$)',body)
    if match:body=body[match.end():].lstrip('\n')
    stem=re.sub(r'[^\w .-]','-',title).strip('. ')[:100] or 'Notiz'
    path=str(Path(folder)/(stem+'-'+uuid.uuid4().hex[:8]+'.md'))
    return book.write(path,prefix+'# '+title+'\n\n'+body,'',note_id=str(uuid.uuid4()))


def open_daily(window):
    if window.area!='user' or not window.book:return
    if window.dirty:window.save_note(lambda:open_daily(window));return
    day=datetime.now().astimezone().date().isoformat()
    text='## '+tr('Heute wichtig')+'\n\n- [ ] \n\n## '+tr('Notizen')+'\n\n'
    window.action('daily',window.show_note,day=day,text=text)


def choose_template(window):
    from PySide6.QtWidgets import QInputDialog
    if window.area!='user' or not window.book:return
    if window.dirty:window.save_note(lambda:choose_template(window));return
    builtins=[(tr('Projekt'),'## '+tr('Ziel')+'\n\n\n## '+tr('Nächste Schritte')+'\n\n- [ ] \n\n## '+tr('Quellen')+'\n\n'),
              (tr('Besprechung'),tr('Datum')+': {{date}} · {{time}}\n\n## '+tr('Ergebnisse')+'\n\n\n## '+tr('Aufgaben')+'\n\n- [ ] \n')]
    custom=sorted((note for note in window.notes.values() if Path(note['path']).parts[0]=='Vorlagen'),key=lambda note:note['path'])
    names=[name for name,_ in builtins]+[note['title']+' · '+note['path'] for note in custom]
    chosen,ok=QInputDialog.getItem(window,tr('Lumen Notes · Vorlage'),tr('Vorlage wählen · eigene Notizen im Ordner „Vorlagen“'),names,0,False)
    if not ok:return
    title,ok=QInputDialog.getText(window,tr('Lumen Notes · Neue Notiz'),tr('Titel'))
    if not ok:return
    index=names.index(chosen);folder=window.collection[7:] if window.collection.startswith('folder:') else '.'
    values=dict(title=title,folder=folder)
    if index<len(builtins):values['text']=builtins[index][1]
    else:
        source=custom[index-len(builtins)];values.update(template=source['path'],expected=source['hash'])
    window.action('from_template',window.show_note,**values)
