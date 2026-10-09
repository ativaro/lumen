"""Personal memory sync settings and explicit two-version conflict choices."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QCheckBox,QDialogButtonBox,QListWidget,QPlainTextEdit
from lumen_i18n import tr
from tools_ui import button,label
import memory_sync as sync


def run(window,action,done,finished=None,**values):
    window.work(tr('Gedächtnisabgleich …'),lambda job:sync.worker(job,window.store,action,**values),done,finished=finished)


def configure(window):
    if window.job or window.poller:return
    if window.dirty:window.save_note(lambda:configure(window));return
    run(window,'info',lambda info:setattr(window,'after_job',lambda:show(window,info)))


def synchronize(window):
    if window.job or window.poller:return
    def done(result):
        window.status.setText(tr('Gedächtnis abgeglichen · {0} Änderungen · {1} Konflikte',result['changed'],result['conflicts']))
        window.after_job=window.refresh
    run(window,'synchronize',done)


def show(window,info):
    dialog=QDialog(window);dialog.setWindowTitle(tr('Lumen Gedächtnis · Serverabgleich'));dialog.resize(570,400)
    dialog.setWindowModality(Qt.WindowModal);layout=QVBoxLayout(dialog)
    layout.setContentsMargins(24,24,24,24);layout.setSpacing(14)
    layout.addWidget(label(info['server'] or tr('Noch kein Lumen Server verbunden'),'heading'))
    if info['user']:layout.addWidget(label(info['user'],'muted'))
    layout.addWidget(label(tr('Persönliche Erinnerungen werden in beide Richtungen abgeglichen und bleiben offline verfügbar. Lokales Projektwissen bleibt auf diesem Gerät. Änderungen und Vergessen gelten auch auf verbundenen Geräten.')))
    layout.addWidget(label(tr('Abgleichen ist keine KI-Freigabe: neue Server-Erinnerungen prüfst du hier und gibst sie bei Bedarf für Lumen frei. Konflikte werden bis zur Entscheidung nicht als Kontext verwendet.'),'muted'))
    layout.addWidget(label(tr('Auch auf dem Server brauchen neue oder geänderte Kopien eine Freigabe. Dort kannst du mehrere Erinnerungen gemeinsam prüfen.'),'muted'))
    if info['server']:
        def open_review():
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(info['server'].rstrip('/')+'/?app=note&memory=1'))
        layout.addWidget(button(tr('Erinnerungen auf dem Server prüfen'),open_review))
    enabled=QCheckBox(tr('Persönliches Gedächtnis synchronisieren'));enabled.setChecked(info['enabled']);enabled.setEnabled(info['allowed'] or info['enabled']);layout.addWidget(enabled)
    if not info['reachable']:layout.addWidget(label(tr('Server nicht erreichbar. Vorhandene Kopien bleiben erhalten.'),'muted'))
    elif not info['allowed']:layout.addWidget(label(tr('Auf dem Server zuerst „Persönliches Gedächtnis synchronisieren“ freigeben.'),'muted'))
    layout.addWidget(label(tr('{0} Konflikte warten auf deine Entscheidung.',info['conflicts']),'muted'))
    actions=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
    actions.button(QDialogButtonBox.Save).setText(tr('Übernehmen'));actions.rejected.connect(dialog.reject)
    def save():
        value=enabled.isChecked();dialog.accept()
        run(window,'configure',lambda _:setattr(window,'after_job',lambda:synchronize(window) if value else None),enabled=value,expected=info['connection'])
    actions.accepted.connect(save)
    now=button(tr('Jetzt abgleichen'),lambda:(dialog.accept(),synchronize(window)))
    now.setEnabled(info['enabled'] and info['allowed']);actions.addButton(now,QDialogButtonBox.ActionRole)
    def rescan():
        dialog.accept()
        run(window,'rescan',lambda _:setattr(window,'after_job',lambda:synchronize(window)))
    full=button(tr('Vollständig vergleichen'),rescan);full.setEnabled(info['enabled'] and info['allowed'])
    full.setToolTip(tr('Nach einer Server-Wiederherstellung: lokale Erinnerungen erneut abgleichen, fehlende Kopien wieder übertragen und abweichende Fassungen zur Prüfung behalten.'))
    layout.addWidget(full)
    if info['conflicts']:
        review=button(tr('Konflikte prüfen'),lambda:(dialog.accept(),review_conflicts(window)))
        actions.addButton(review,QDialogButtonBox.ActionRole)
    layout.addWidget(actions);window.memory_sync_dialog=dialog;dialog.show()


def review_conflicts(window):
    run(window,'conflicts',lambda entries:setattr(window,'after_job',lambda:conflict_dialog(window,entries)))


def conflict_dialog(window,entries):
    dialog=QDialog(window);dialog.setWindowTitle(tr('Lumen Gedächtnis · Konflikte'));dialog.resize(860,540)
    dialog.setWindowModality(Qt.WindowModal);layout=QVBoxLayout(dialog)
    layout.setContentsMargins(24,24,24,24);layout.setSpacing(12)
    listing=QListWidget();listing.setMaximumHeight(100);listing.setAccessibleName(tr('Gedächtniskonflikte'));layout.addWidget(listing)
    previews=QHBoxLayout();layout.addLayout(previews,1)
    local=QPlainTextEdit();remote=QPlainTextEdit()
    for editor,title in ((local,tr('Auf diesem Desktop')),(remote,tr('Auf dem Server'))):
        column=QVBoxLayout();column.addWidget(label(title,'heading'));editor.setReadOnly(True);editor.setAccessibleName(title);column.addWidget(editor);previews.addLayout(column)
    current=[]
    def loaded(value):
        if value['id']!=entries[listing.currentRow()]['id']:return
        current[:]=[value];local.setPlainText(value['local']['text'] if value['local'] else tr('Auf diesem Desktop vergessen'))
        remote.setPlainText(value['remote']['body']);ours.setEnabled(True);theirs.setEnabled(bool(value['local']))
    def select(index):
        current.clear();ours.setEnabled(False);theirs.setEnabled(False)
        if index<0:return
        listing.setEnabled(False)
        run(window,'conflicts',loaded,finished=lambda:listing.setEnabled(True),identity=entries[index]['id'])
    def resolve(use_server):
        if not current:return
        value=current[0];dialog.accept()
        run(window,'resolve',lambda _:setattr(window,'after_job',lambda:synchronize(window)),
            identity=value['id'],use_server=use_server,expected_revision=value['remote']['revision'],
            expected_hash=value['local']['hash'] if value['local'] else '')
    actions=QHBoxLayout();ours=button(tr('Meine Fassung behalten'),lambda:resolve(False));theirs=button(tr('Serverfassung übernehmen'),lambda:resolve(True))
    actions.addWidget(ours);actions.addWidget(theirs);actions.addStretch();actions.addWidget(button(tr('Schließen'),dialog.reject));layout.addLayout(actions)
    ours.setEnabled(False);theirs.setEnabled(False)
    listing.addItems([entry['title'] for entry in entries]);listing.setCurrentRow(-1);listing.currentRowChanged.connect(select)
    window.memory_conflict_dialog=dialog;dialog.show()
    if entries:listing.setCurrentRow(0)
