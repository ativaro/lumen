"""One explicit notebook/connection choice; existing worker owns cancellation."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QPushButton, QComboBox
from lumen_i18n import tr
from preview import label
from tools_ui import Job
import wissen_data as data
import wissen_sync as sync


def configure(window):
    if window.area!='user' or not window.book or window.job or window.poller:return
    if window.dirty:window.save_note(lambda:configure(window));return
    def loaded(info):window.after_job=lambda:show_dialog(window,info)
    window.action('sync_info',loaded)


def show_dialog(window,info):
    dialog=QDialog(window);dialog.setWindowTitle(tr('Lumen Wissen · Serverabgleich'));dialog.resize(570,380)
    dialog.setWindowModality(Qt.WindowModal)
    box=QVBoxLayout(dialog);box.setContentsMargins(24,24,24,24);box.setSpacing(16)
    box.addWidget(label(info['server']+'\n'+info['user'],'heading'))
    box.addWidget(label(tr('Persönliche Notizen aus diesem Ordner:')+'\n'+str(window.book.root)))
    box.addWidget(label(tr('Markdown-Texte werden in beide Richtungen abgeglichen. Verknüpfte Anhänge kannst du zusätzlich einschließen. Das Lumen-Gedächtnis bleibt getrennt. Änderungen und Löschungen gelten auch auf verbundenen Geräten; Konflikte bleiben als eigene Notizen erhalten.')))
    area=QComboBox();area.setAccessibleName(tr('Serverbereich'))
    area.addItem(tr('Mein privater Serverbereich'),'')
    for space in info.get('workspaces',[]):
        if not space['private']:area.addItem(space['title'],str(space['id']))
    current=info.get('workspace','')
    if current and area.findData(current)<0:area.addItem(tr('Nicht mehr freigegebener Bereich'),current)
    area.setCurrentIndex(max(0,area.findData(current)));box.addWidget(area)
    box.addWidget(label(tr('Gemeinsame Bereiche sind für deren Mitglieder sichtbar. Für einen anderen Bereich einen leeren lokalen Notizordner wählen.'),'muted'))
    enabled=QCheckBox(tr('Diesen Notizordner synchronisieren'));enabled.setChecked(info['enabled'])
    enabled.setEnabled(info['allowed'] or info['enabled']);box.addWidget(enabled)
    assets=QCheckBox(tr('Verknüpfte Bilder und Anhänge mitsynchronisieren'));assets.setChecked(info.get('attachments',False));box.addWidget(assets)
    message=tr('Automatisch auch bei geschlossenem Lumen Wissen über den Verbindungsdienst. Deaktivieren behält vorhandene Kopien.')
    if not info['reachable']:message=tr('Server derzeit nicht erreichbar. Du kannst den Abgleich weiterhin deaktivieren.')
    elif not info['allowed']:message=tr('Auf dem Server unter Geräte die Fähigkeit „Notizen synchronisieren“ freigeben.')
    box.addWidget(label(message,'muted'))
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Save).setText(tr('Übernehmen'))
    buttons.rejected.connect(dialog.reject)
    def save():
        value=enabled.isChecked();dialog.accept()
        def saved(_):
            window.status.setText(tr('Serverabgleich aktiviert') if value else tr('Serverabgleich deaktiviert'))
            if value:window.after_job=lambda:synchronize(window)
        window.action('sync_config',saved,expected=info['scope'],enabled=value,**({'attachments':assets.isChecked()} if assets.isChecked()!=info.get('attachments',False) else {}),**({'target_workspace':area.currentData()} if area.currentData()!=info.get('workspace','') else {}))
    buttons.accepted.connect(save)
    now=QPushButton(tr('Jetzt abgleichen'));now.setEnabled(info['enabled'] and info['allowed'])
    now.clicked.connect(lambda:(dialog.accept(),synchronize(window)));buttons.addButton(now,QDialogButtonBox.ActionRole)
    box.addWidget(buttons);window.sync_dialog=dialog;dialog.show()


def synchronize(window):
    if window.area!='user' or not window.book or window.job or window.poller or window.closing:return
    if getattr(window,'sync_dialog',None) and window.sync_dialog.isVisible():return
    if window.dirty or (window.engine and window.engine.busy):return
    if not sync.enabled(window.book):return
    def done(result):
        window.scanned(result['scan'])
        message=tr('Serverabgleich abgeschlossen · {0} Änderungen',result['changed'])
        if result['conflicts']:
            message=tr('Beide Fassungen erhalten · {0} Konfliktnotizen',len(result['conflicts']))
            window.banner.setText(message);window.banner.show()
        window.status.setText(message)
    book=window.book
    window.poller=Job(lambda job:data.worker(job,window.store,'sync',str(book.root),identity=book.identity),window)
    window.poller.result.connect(lambda result:window.safe(done,result))
    window.poller.failed.connect(lambda message:window.status.setText(tr('Serverabgleich nicht abgeschlossen: ')+message))
    window.poller.finished.connect(window.poll_finished);window.poller.start()


def install(window):
    window.sync_timer=QTimer(window);window.sync_timer.setInterval(60000)
    window.sync_timer.timeout.connect(lambda:window.safe(synchronize,window));window.sync_timer.start()
    window.notebook_menu.addAction(tr('Serverabgleich …'),lambda:window.safe(configure,window))
