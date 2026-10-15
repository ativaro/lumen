"""Reviewable batch tag changes with the existing note history and revision checks."""
from note_tags import identity, rename_tag
from lumen_i18n import tr


def plan(book, old, new):
    old=identity(old);new=identity(new) if new.strip() else ''
    if new==old or new.startswith(old+'/'):
        raise ValueError(tr('Bitte einen anderen Tag außerhalb dieses Untertags wählen.'))
    scan=book.scan()
    if scan['limited'] or scan['errors']:
        raise ValueError(tr('Zuerst alle Notizen vollständig und fehlerfrei einlesen.'))
    changes=[]
    for note in scan['notes']:
        if not any(tag==old or tag.startswith(old+'/') for tag in note['tags']):continue
        after=rename_tag(note['text'],old,new)
        if after!=note['text']:
            changes.append(dict(path=note['path'],title=note['title'],hash=note['hash'],after=after))
    return changes


def apply(book, changes):
    # Validate the entire preview before the first write; each write checks again.
    for change in changes:
        current=book.read(change['path'])
        if current['hash']!=change['hash'] and current['text']!=change['after']:
            raise ValueError(tr('CONFLICT: Notizen wurden geändert. Tag-Vorschau erneut öffnen.'))
    completed=[]
    try:
        for change in changes:
            current=book.read(change['path'])
            if current['text']!=change['after']:
                book.write(change['path'],change['after'],change['hash'])
            completed.append(change['path'])
    except (OSError,ValueError) as error:
        raise ValueError(tr('{0} Notizen geändert; Vorgang gestoppt. Frühere Fassungen bleiben im Verlauf. {1}',len(completed),str(error))) from error
    return dict(changed=len(completed),scan=book.scan())


def review(window):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    if window.area!='user' or not window.book:return
    if window.dirty:window.save_note(lambda:review(window));return
    choices=sorted({'/'.join(tag.split('/')[:i]) for note in window.notes.values() for tag in note['tags'] for i in range(1,len(tag.split('/'))+1)})
    if not choices:return
    old,ok=QInputDialog.getItem(window,tr('Lumen Notes · Tags bearbeiten'),tr('Tag mit Untertags'),choices,0,False)
    if not ok:return
    new,ok=QInputDialog.getText(window,tr('Lumen Notes · Tags bearbeiten'),tr('Neuer Tag · leer lassen zum Entfernen'))
    if not ok:return
    new=identity(new) if new.strip() else ''
    def preview(changes):
        if not changes:
            window.status.setText(tr('Keine betroffenen Notizen.'));return
        dialog=QMessageBox(window)
        dialog.setWindowTitle(tr('Lumen Notes · Tag-Änderung prüfen'))
        dialog.setText(tr('{0} Notizen: #{1} → {2}',len(changes),old,'#'+new if new else tr('Entfernen')))
        dialog.setInformativeText(tr('Untertags werden mitgeändert. Bestehende Ziel-Tags werden zusammengeführt. Frühere Fassungen bleiben im Verlauf.'))
        dialog.setDetailedText('\n'.join(change['path'] for change in changes))
        dialog.setStandardButtons(QMessageBox.Apply|QMessageBox.Cancel)
        dialog.setDefaultButton(QMessageBox.Cancel)
        if dialog.exec()!=QMessageBox.Apply:return
        def done(result):
            window.scanned(result['scan'])
            window.refresh()
            window.status.setText(tr('{0} Notizen geändert.',result['changed']))
        if window.job:window.after_job=lambda:window.action('apply_tags',done,changes=changes)
        else:window.action('apply_tags',done,changes=changes)
    window.action('plan_tags',preview,old=old,new=new)
