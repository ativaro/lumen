"""Render the real native UI with isolated synthetic tasks; never touches user data."""
import os, tempfile, sys, json
from pathlib import Path
home = tempfile.TemporaryDirectory(prefix='lumen-design-render-')
os.environ.update(HOME=home.name, XDG_CONFIG_HOME=home.name+'/config', XDG_DATA_HOME=home.name+'/data', QT_QPA_PLATFORM='offscreen', LUMEN_LANGUAGE=os.environ.get('LUMEN_LANGUAGE','de'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'files'))
from test_studio import StudioTest
from PySide6.QtTest import QTest
StudioTest.setUpClass(); t=StudioTest(); t.setUp()
w=t.window; chat=w.chat; space=w.workspace
from appearance import apply_design
apply_design(t.app, os.environ.get('LUMEN_RENDER_THEME', 'glass'))
out=Path(os.environ.get('LUMEN_RENDER_OUTPUT','/tmp/lumen-desktop-render')); out.mkdir(parents=True,exist_ok=True)
downloads=Path(t.tmp)/'Downloads'; downloads.mkdir(); chat.backend.new_conversation(str(downloads))
chat.backend.session='design-preview'; chat.backend.message_id='preview-turn'
chat.tracker.started('Downloads aufräumen', [], 'plan')
text='## Mehr Ordnung.\nAlles bleibt auffindbar.\n\n128 Dateien geprüft. Die PDFs lassen sich nach Jahr sortieren. Drei mögliche Duplikatgruppen solltest du vor dem Löschen prüfen.\n\n### Downloads\n\n- Dokumente / 2026 — 28 PDFs\n- Dokumente / 2025 — 14 PDFs\n- Bilder — 18 Dateien\n- Weitere Dateien — 68 Dateien\n\n---\n\nDies ist ein Vorschlag. Es wurde keine Datei verschoben oder gelöscht.'
chat.backend.messages=[{'info':{'role':role,'id':key,'parentID':'preview-turn'},'parts':[{'type':'text','text':body}]} for role,key,body in [('user','preview-turn','Prüfe meine Downloads, gruppiere die PDFs nach Jahr und finde doppelte Dateien. Bitte noch nichts verschieben.'),('assistant','preview-answer',text)]]
chat.show_messages(chat.backend.messages); chat.tracker.finished(True,text)
chat.backend.sessionsChanged.emit([{'id':'design-preview','title':'Downloads aufräumen','time':{'updated':20}}] + [{'id':f'preview-{i}','title':title,'time':{'updated':19-i}} for i,title in enumerate(['Notizen zusammenfassen','Reise vorbereiten','Fotos ordnen','Wochenplan erstellen','Dokumente vergleichen','Backup prüfen'])])
from lumen_projects import save_project
for name in ('Work', 'Privat', 'Homelab'):
    save_project(space.store, None, name, [dict(label=name, location=str(downloads))], [], [], '')
w.workspace_bar.refresh()
chat.heading.setText('Downloads aufräumen'); chat.context_chip.setText('Downloads')
space.store.create_task('Rechnungen benennen', directory=str(downloads),status='needs_input')
running=space.store.create_task('Downloads aufräumen',directory=str(downloads),status='running',steps=[{'action':'open','path':t.tmp+'/Dokumente'},{'action':'open','path':t.tmp+'/Bilder'},{'action':'open','path':t.tmp+'/Weitere Dateien'}])
space.store.update_task(running,cursor=1,session='design-preview',result='128 Dateien · 42 PDFs\n\nOrdnerüberblick vorbereitet.')
done=space.store.create_task('Backups prüfen',directory=str(downloads),status='completed'); space.store.update_task(done,result='Prüfbericht bereit.')
space.select_task(running)
for page,name in [(0,'chat'),(4,'auftraege'),(10,'ergebnisse')]:
    w.show_page(page); w.resize(1360,722); QTest.qWait(200)
    if page == 0: chat.transcript.verticalScrollBar().setValue(0); QTest.qWait(30)
    w.grab().save(str(out/(name+'.png')))
    print(name, 'window',w.size().toTuple(),'nav',w.navigation.width(),'chat',chat.width(),'inspector',space.task_inspector.width())
for page,name in [(0,'chat-schmal'),(4,'auftraege-schmal'),(10,'ergebnisse-schmal')]:
    w.show_page(page); w.navigation.maintenance.setChecked(page == 4); w.resize(760,600); QTest.qWait(150); w.grab().save(str(out/(name+'.png')))
    print(name,w.size().toTuple())
t.tearDown();t.doCleanups();home.cleanup()
