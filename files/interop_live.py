"""Read linked notebook collections afresh, keeping their source as the owner."""
from pathlib import Path
from lumen_i18n import tr
from interop_data import Registry
from tools_data import Library


def live_notes(library,key,job,store=None):
    from lumen_store import Store
    from wissen_data import Notebook
    registry=Registry(library.root.parent);record=library.get(key)
    links=record.get('live_sources',[])+[r['target'] for r in record.get('resources',[]) if r.get('kind')=='lumen']
    ref=registry.register(dict(app=library.root.name,kind='record',id=key,title=record['title']))
    links += [r['url'] for r in registry.related(ref) if r['app']=='wissen']
    result={};store=store or Store()
    for url in dict.fromkeys(links):
        job.check();source=registry.resolve(url)
        if source['app']!='wissen' or source['kind'] not in ('note','collection'):continue
        book=Notebook(store,root=source['locator']['root'])
        if source['kind']=='note':notes=[book.read(source['id'])]
        else:
            notes=book.scan()['notes'];collection=source['id'].removeprefix('collection:');kind,_,value=collection.partition(':')
            if kind=='tag':
                from note_tags import matches_tags
                notes=[note for note in notes if matches_tags(note['tags'],[value])]
            elif kind=='folder':notes=[note for note in notes if Path(note['path']).is_relative_to(value)]
            elif kind=='kind':notes=[note for note in notes if note.get('memory',{}).get('kind')==value]
        for note in notes:
            job.check()
            ref=dict(app='wissen',kind='note',id=note['path'],title=note['title'],path=str(book.root/note['path']),locator=dict(root=str(book.root)))
            target=registry.register(ref);result[target]=dict(title=note['title'],text=note['text'],url=target)
            if len(result)>=500:return list(result.values())
    return list(result.values())


def show_live(window):
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QListWidget,QListWidgetItem,QPlainTextEdit,QDialogButtonBox,QLabel
    from tools_ui import Job
    from interop_open import open_url
    if not window.current:raise ValueError(tr('Zuerst einen Eintrag auswählen.'))
    key=window.current
    class Live(QDialog):
        job=None;closing=False
        def reject(self):
            timer.stop()
            if self.job:self.closing=True;self.job.cancelled.set()
            else:super().reject()
        def closeEvent(self,event):self.reject();event.ignore()
    dialog=Live(window);dialog.setWindowTitle(tr('Live aus Lumen Notes'));dialog.resize(780,640)
    layout=QVBoxLayout(dialog);status=QLabel(tr('Notizen werden alle fünf Sekunden neu gelesen. Die Quelle bleibt bearbeitbar.'));layout.addWidget(status)
    listing=QListWidget();listing.setAccessibleName(tr('Verknüpfte Notizen'));layout.addWidget(listing)
    preview=QPlainTextEdit();preview.setReadOnly(True);preview.setAccessibleName(tr('Aktueller Notizinhalt'));layout.addWidget(preview,2)
    def show():
        item=listing.currentItem();preview.setPlainText(item.data(Qt.UserRole)['text'] if item else '')
    listing.currentItemChanged.connect(lambda *_:show())
    from interop_ui import safe_action
    listing.itemActivated.connect(lambda item:safe_action(window,lambda:open_url(item.data(Qt.UserRole)['url'],window.library.root.parent)))
    buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    def refresh(rows):
        item=listing.currentItem();selected=item.data(Qt.UserRole)['url'] if item else ''
        listing.blockSignals(True);listing.clear()
        for row in rows:
            item=QListWidgetItem(row['title']);item.setData(Qt.UserRole,row);listing.addItem(item)
            if row['url']==selected:listing.setCurrentItem(item)
        listing.blockSignals(False)
        if listing.currentRow()<0 and listing.count():listing.setCurrentRow(0)
        show()
    def finished():
        dialog.job.deleteLater();dialog.job=None
        if dialog.closing:dialog.reject()
    def poll():
        if dialog.job:return
        dialog.job=Job(lambda job:live_notes(window.library,key,job,getattr(window,'store',None)),dialog)
        dialog.job.result.connect(refresh);dialog.job.failed.connect(status.setText);dialog.job.finished.connect(finished);dialog.job.start()
    timer=QTimer(dialog);timer.setInterval(5000);timer.timeout.connect(poll);timer.start();poll();dialog.exec()


def show_paths(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QListWidget,QListWidgetItem,QDialogButtonBox
    from interop_open import launch
    record=window.library.get(window.current)
    dialog=QDialog(window);dialog.setWindowTitle(tr('Verknüpfte Ordner und Dateien'));dialog.resize(680,440)
    layout=QVBoxLayout(dialog);listing=QListWidget();layout.addWidget(listing)
    for link in record.get('linked_paths',[]):
        item=QListWidgetItem(link['title']+'\n'+link['path']);item.setData(Qt.UserRole,link['path']);listing.addItem(item)
    from interop_ui import safe_action
    listing.itemActivated.connect(lambda item:safe_action(window,lambda:launch('files',[item.data(Qt.UserRole),'--select'],window.library.root.parent)))
    buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()
