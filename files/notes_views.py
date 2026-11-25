"""Notebook-local saved filters and deterministic list ordering."""
import hashlib
import uuid
from lumen_i18n import tr
from notes_properties import for_note


def key(book):return 'knowledge/views/'+hashlib.sha256((str(book.root)+repr(book.identity)).encode()).hexdigest()

def state(window):return window.store.setting(key(window.book),dict(saved={},active='',sort=''))

def ordered(notes,mode):
    def dated(note):
        props=for_note(note)
        dates={name:item['value'] for name,item in props.items() if item['kind']=='date'}
        value=dates.get('due',dates.get('date',next(iter(sorted(dates.values())),'')))
        return (not bool(value),value,note['title'].casefold(),note['path'])
    if not mode:return list(notes)
    if mode=='date':return sorted(notes,key=dated)
    if mode=='title':return sorted(notes,key=lambda n:(n['title'].casefold(),n['path']))
    return sorted(notes,key=lambda n:(-n.get('modified',0),n['path']))


def choose(window,identity):
    if window.dirty:window.save_note(lambda:choose(window,identity));return
    saved=state(window);view=saved['saved'][identity]
    if view['collection'].startswith('folder:'):window.book.stat(view['collection'][7:],folder=True)
    saved['active']=identity;saved['sort']=view['sort'];window.store.set_setting(key(window.book),saved)
    window.view_sort=view['sort'];window.search.setText(view['query']);window.set_collection(view['collection']);window.views_button.setText(view['name'])
    if view.get('table'):
        from notes_grid import show
        show(window)
    elif getattr(window,'notes_table',None):window.notes_table.close()


def restore(window):
    window.view_sort='';window.restore_table=False;window.views_button.setText(tr('Ansichten'))
    if window.area!='user':return
    window.collection='';window.search.blockSignals(True);window.search.clear();window.search.blockSignals(False)
    saved=state(window);window.view_sort=saved.get('sort','');view=saved.get('saved',{}).get(saved.get('active'))
    if view:
        window.restore_table=bool(view.get('table'))
        window.collection=view['collection'];window.search.blockSignals(True);window.search.setText(view['query']);window.search.blockSignals(False);window.views_button.setText(view['name'])


def sort(window,mode):
    saved=state(window);saved['sort']=mode;saved['active']='';window.store.set_setting(key(window.book),saved);window.view_sort=mode;window.views_button.setText(tr('Ansichten'));window.refresh()


def save(window,table=False):
    from PySide6.QtWidgets import QInputDialog
    if window.area!='user' or not window.book:return
    name,ok=QInputDialog.getText(window,tr('Lumen Notes · Ansicht speichern'),tr('Name · gleicher Name ersetzt die gespeicherte Ansicht'))
    name=name.strip()[:80]
    if not ok or not name:return
    saved=state(window);identity=next((key for key,v in saved['saved'].items() if v['name']==name),uuid.uuid4().hex)
    if identity not in saved['saved'] and len(saved['saved'])>=30:raise ValueError(tr('Maximal 30 gespeicherte Ansichten pro Notizbuch.'))
    saved['saved'][identity]=dict(name=name,query=window.search.text(),collection=window.collection,sort=getattr(window,'view_sort',''),table=table);saved['active']=identity
    window.store.set_setting(key(window.book),saved);window.views_button.setText(name)


def remove(window,identity):
    saved=state(window);saved['saved'].pop(identity,None)
    if saved['active']==identity:saved['active']='';window.views_button.setText(tr('Ansichten'))
    window.store.set_setting(key(window.book),saved)


def populate(window,menu):
    menu.clear()
    if window.area!='user' or not window.book:return
    from notes_grid import show
    menu.addAction(tr('Als Tabelle anzeigen'),lambda:window.safe(show,window));menu.addSeparator()
    saved=state(window)
    for identity,view in saved['saved'].items():
        action=menu.addAction(view['name'],lambda checked=False,i=identity:window.safe(choose,window,i));action.setCheckable(True);action.setChecked(saved['active']==identity)
    if saved['saved']:menu.addSeparator()
    for mode,title in [('recent',tr('Zuletzt bearbeitet')),('title',tr('Nach Titel')),('date',tr('Nach Datum'))]:
        action=menu.addAction(title,lambda checked=False,m=mode:window.safe(sort,window,m));action.setCheckable(True);action.setChecked(getattr(window,'view_sort','')==mode)
    menu.addSeparator();menu.addAction(tr('Aktuelle Ansicht speichern …'),lambda:window.safe(save,window))
    if saved['active'] in saved['saved']:menu.addAction(tr('Diese Ansicht entfernen'),lambda:window.safe(remove,window,saved['active']))
