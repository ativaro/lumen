import sys,json
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMainWindow,QLabel
from PySide6.QtCore import QObject,Slot,QTimer,Qt
from PySide6.QtDBus import QDBusConnection
name=sys.argv[1] if len(sys.argv)>1 else 'A'
app=QApplication([])
app.setApplicationName('Lumen Notes' if name=='A' else 'Lumen Menütest '+name)
app.setApplicationDisplayName('Chromium' if name=='Browser' else 'Lumen Notes' if name=='A' else 'Lumen Menütest '+name)
app.setDesktopFileName('lumen-menu-test-'+name.lower())
w=QMainWindow();w.setWindowTitle('Workshop — Chromium' if name=='Browser' else 'Lumen Menütest '+name);w.resize(720,480)
label=QLabel('Synthetische Testdaten: '+name);label.setAlignment(Qt.AlignCenter);w.setCentralWidget(label)
if name!='Empty':
    for title,action in [('Datei','Testdatei speichern'),('Bearbeiten','Testwert ändern'),('Ansicht','Testansicht umschalten'),('Hilfe','Testhilfe öffnen')]:
        menu=w.menuBar().addMenu(title)
        a=menu.addAction(action)
        def hit(checked=False,title=title):
            with Path('/profile/actions.jsonl').open('a') as f:f.write(json.dumps({'app':name,'menu':title})+'\n')
            label.setText('Ausgeführt: '+title)
            if title=='Datei':Path('/profile/saved-'+name+'.txt').write_text('Lumen Testdatei '+name)
        a.triggered.connect(hit)
class Control(QObject):
    @Slot(str)
    def record(self,value):Path("/profile/kwin-geometry.json").write_text(value)
    @Slot(str,result=str)
    def command(self,cmd):
        if cmd=='geometry':
            r=w.frameGeometry();return json.dumps(dict(x=r.x(),y=r.y(),width=r.width(),height=r.height()))
        if cmd=='maximize':w.showMaximized();w.raise_();w.activateWindow()
        elif cmd=='normal':w.showNormal();w.raise_();w.activateWindow()
        elif cmd=='fullscreen':w.showFullScreen();w.raise_();w.activateWindow()
        elif cmd=='activate':w.raise_();w.activateWindow()
        elif cmd=='close':w.close()
        elif cmd=='disable':w.menuBar().actions()[0].menu().actions()[0].setEnabled(False)
        return cmd
control=Control();bus=QDBusConnection.sessionBus()
assert bus.registerService('org.lumen.MenuTest'+name)
assert bus.registerObject('/Control',control,QDBusConnection.ExportAllSlots)
w.showMaximized()
QTimer.singleShot(300, w.activateWindow)
QTimer.singleShot(1200, lambda:print('FIXTURE_STATE',w.isVisible(),w.windowHandle().isExposed(),flush=True))
app.exec()
