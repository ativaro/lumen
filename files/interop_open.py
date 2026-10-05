"""Open allowlisted Lumen object references in the owning native application."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from interop_data import APPS, Registry, TOKEN, validate_ref
from lumen_i18n import tr


def launch(app,args=(),root=None):
    if app not in APPS:raise ValueError(tr('Unbekannte Lumen-Anwendung.'))
    folder=Path(__file__).resolve().parent
    command=[sys.executable,str(folder/('app.py' if app=='files' else 'tools_app.py'))]
    if app!='files':command.append(app)
    command.extend(str(arg) for arg in args)
    env=dict(os.environ)
    if root is not None:env['LUMEN_TOOLS_DATA']=str(root)
    subprocess.Popen(command,env=env,start_new_session=True,stdin=subprocess.DEVNULL)


def open_url(url,root=None):
    registry=Registry(root);parts=urlsplit(url)
    if parts.scheme=='lumen' and parts.netloc=='handoff' and TOKEN.fullmatch(parts.path[1:]) and not parts.query and not parts.fragment:
        request=registry.request(parts.path[1:]);launch(request['target'],['--handoff',request['id']],root);return
    ref=registry.resolve(url)
    launch(ref['app'],['--ref',url] if ref['app']!='files' else [ref.get('path',ref['id']),'--select'],root)


def focus(window,ref):
    """Called only after the target's pending edits have been saved."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItem,QTreeWidgetItemIterator,QMessageBox
    ref=validate_ref(ref);app=ref['app'];position=ref.get('position',{})
    if app!=window.name:raise ValueError(tr('Dieser Verweis gehört zu einer anderen Lumen-Anwendung.'))
    if app=='wissen':
        if ref.get('kind')=='collection':
            locator=ref.get('locator',{});root=locator.get('root');area=locator.get('area','user');key=ref['id'].removeprefix('collection:')
            if window.area==area and window.book and (not root or Path(root)==window.book.root):
                focus_collection(window,key);return
            if area=='user' and root and QMessageBox.question(window,tr('Notizordner öffnen'),tr('Zum verknüpften Notizordner wechseln?')+'\n'+root)!=QMessageBox.Yes:return
            if window.poller:raise ValueError(tr('Aktualisierung kurz abwarten und erneut wählen.'))
            window.interop_pending_collection=(root,area,key)
            if area!=window.area:window.switch_area(area)
            else:
                window.notes={};window.folders=[];window.collection='';window.clear_note(tr('Deine erste Notiz'));window.initialize(root)
            return
        window.interop_pending_position=(ref['id'],position)
        path=ref.get('path') or str(Path(ref.get('locator',{}).get('root',''))/ref['id'])
        root=ref.get('locator',{}).get('root')
        if root and window.book and Path(root)!=window.book.root and ref.get('locator',{}).get('area','user')!='lumen':
            if QMessageBox.question(window,tr('Notizordner öffnen'),tr('Zum verknüpften Notizordner wechseln?')+'\n'+root)!=QMessageBox.Yes:return
            window.pending_file=path;window.initialize(root);return
        window.open_file(path);return
    if app=='inbox' and ref.get('kind')!='record':
        if ref.get('locator',{}).get('account'):window.focus_record(ref['locator']['account'])
        window.reload_other()
        if ref['kind']=='message':
            loc=ref['locator'];item=QTreeWidgetItem();item.setData(0,Qt.UserRole,loc)
            window.tabs.setCurrentIndex(0);window.read_message(item)
            if not window.message or any(str(window.message[k])!=str(loc[k]) for k in ('account','folder','validity','uid')):
                raise ValueError(tr('Die verknüpfte Nachricht ist lokal nicht mehr verfügbar.'))
            if position.get('part','').startswith('attachment:'):
                index=_index(position['part'].split(':',1)[1],window.attachments.count())
                window.attachments.setCurrentIndex(index)
            focus_text(window.reader,position)
            return
        if ref['kind']=='event':
            from interop_targets import event_proposal
            try:proposal=event_proposal(window.library,ref['id'])
            except ValueError:proposal=None
            if proposal:
                window.event_dialog(proposal,window.library.get(proposal['account']));return
        if ref['kind'] in ('task','draft','event'):
            tree={'task':window.tasks,'draft':window.drafts,'event':window.events}[ref['kind']]
            it=QTreeWidgetItemIterator(tree)
            while it.value():
                item=it.value();value=item.data(0,Qt.UserRole) or {}
                ids={str(value.get('id',value.get('uid',''))),str(value.get('uid',''))+'|'+str(value.get('start',''))}
                if ref['id'] in ids and (not ref.get('locator',{}).get('account') or value.get('account')==ref['locator']['account']):
                    tree.setCurrentItem(item);tree.scrollToItem(item)
                    window.tabs.setCurrentIndex({'task':3,'draft':2,'event':1}[ref['kind']]);return
                it+=1
            raise ValueError(tr('Der verknüpfte Eintrag ist nicht mehr verfügbar.'))
    window.focus_record(ref['id'])
    if app=='reader':window.focus_position(position)
    else:focus_part(window,position)
    if app in ('meetings','radio') and 'time' in position:
        player=window.player;player.position=min(position['time'],player.duration);player.seek.setValue(player.position)
        if app=='meetings' and not position.get('part'):
            for row,segment in enumerate(window.library.get(ref['id']).get('segments',[])):
                if segment['start']<=position['time']<=segment['end']:
                    window.transcript.setCurrentCell(row,1);break


def _index(value,count):
    if not str(value).isdigit() or not 0<=int(value)<count:raise ValueError(tr('Die verknüpfte Fundstelle ist nicht mehr vorhanden.'))
    return int(value)


def focus_collection(window,key):
    from PySide6.QtCore import Qt
    window.update_collections()
    if key not in [window.collections.item(index).data(Qt.UserRole) for index in range(window.collections.count())]:
        raise ValueError(tr('Der verknüpfte Eintrag ist nicht mehr verfügbar.'))
    window.search.clear();window.set_collection(key);window.collections.setFocus()


def focus_text(widget,position):
    if 'start' not in position and 'end' not in position:return
    from PySide6.QtGui import QTextCursor
    start,end=position.get('start',0),position.get('end',0)
    if not 0<=start<end<widget.document().characterCount():raise ValueError(tr('Der verknüpfte Textausschnitt ist nicht mehr vorhanden.'))
    cursor=widget.textCursor();cursor.setPosition(start);cursor.setPosition(end,QTextCursor.KeepAnchor);widget.setTextCursor(cursor);widget.ensureCursorVisible();widget.setFocus()


def _select_tree(tree,key):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItemIterator
    items=QTreeWidgetItemIterator(tree)
    while items.value():
        item=items.value()
        if item.data(0,Qt.UserRole)==key:tree.setCurrentItem(item);tree.scrollToItem(item);return
        items+=1
    raise ValueError(tr('Die verknüpfte Fundstelle ist nicht mehr vorhanden.'))


def focus_part(window,position):
    from PySide6.QtCore import Qt
    from interop_parts import match_part,window_parts
    part=position.get('part','');kind,_,value=part.partition(':');app=window.name
    if app=='workbench' and kind=='item':
        window.open_scope(value);return
    if app=='workbench' and kind in ('resource','question'):
        listing=window.resources if kind=='resource' else window.questions
        index=match_part(kind,value,window_parts(window,kind))
        if kind=='question' and hasattr(window,'projects'):
            for item in window.projects.items(window.current)+window.projects.items(window.current,archived=True):
                if item.get('legacy_question')==index and item.get('legacy_text')==listing.item(index).text():
                    listing.setCurrentRow(index);window.open_scope(item['id']);return
        window.tabs.setCurrentIndex(1 if kind=='resource' else 0);listing.setCurrentRow(index);listing.scrollToItem(listing.currentItem());return
    if app=='household' and kind=='attachment':
        for index in range(window.attachments.count()):
            item=window.attachments.item(index)
            if item.data(Qt.UserRole).get('asset')==value:window.attachments.setCurrentItem(item);window.attachments.scrollToItem(item);return
        raise ValueError(tr('Der verknüpfte Beleg ist nicht mehr vorhanden.'))
    if app=='meetings':
        if part=='agenda':window.tabs.setCurrentIndex(2);window.agenda.setFocus();return
        if kind in ('segment','result'):
            index=match_part(kind,value,window_parts(window,kind))
            table=window.transcript if kind=='segment' else window.results;window.tabs.setCurrentIndex(0 if kind=='segment' else 1)
            table.setCurrentCell(index,1);table.scrollToItem(table.item(index,1));return
    if app=='radio':
        if kind=='source':
            index=match_part(kind,value,window_parts(window,kind));window.tabs.setCurrentIndex(0);window.sources.setCurrentRow(index);return
        if 'start' in position:window.tabs.setCurrentIndex(1);focus_text(window.script,position);return
    if app=='sound' and kind=='rule':
        items=window_parts(window,kind);index=match_part(kind,value,items)
        window.tabs.setCurrentIndex(1);_select_tree(window.rules,items[index]['app']);return
    if app=='vault' and kind=='snapshot':
        window.action('snapshots',completed=lambda:_select_tree(window.snapshots,value))
        return
    if part:raise ValueError(tr('Diese verknüpfte Fundstelle wird nicht unterstützt.'))


def main():
    parser=argparse.ArgumentParser(description='Lumen')
    parser.add_argument('url');args=parser.parse_args()
    try:open_url(args.url)
    except (ValueError,OSError) as error:
        from app import create_app
        from PySide6.QtWidgets import QMessageBox
        app=create_app();QMessageBox.warning(None,'Lumen',str(error));return 1
    return 0

if __name__=='__main__':sys.exit(main())
