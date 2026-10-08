"""Review bounded learned suggestions in the existing Wissen window."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QListWidget
from lumen_i18n import tr
from lumen_memory import worker
from tools_ui import button,label


def review(window):
    if window.job or window.poller:return
    if window.dirty:window.save_note(lambda:review(window));return
    def ready(rows):window.after_job=lambda:show(window,rows)
    window.work(tr('Gedächtnisvorschläge laden …'),lambda job:worker(job,window.store,'proposals'),ready)


def show(window,rows):
    dialog=QDialog(window);dialog.setWindowTitle(tr('Lumen Gedächtnis · Vorschläge'));dialog.resize(620,540);dialog.setWindowModality(Qt.WindowModal)
    layout=QVBoxLayout(dialog);layout.setContentsMargins(24,24,24,24);layout.setSpacing(12)
    layout.addWidget(label(tr('Erst deine Freigabe macht einen Vorschlag zur Erinnerung.'),'muted'))
    listing=QListWidget();listing.setAccessibleName(tr('Gedächtnisvorschläge'));listing.setMaximumHeight(100);layout.addWidget(listing)
    preview=QPlainTextEdit();preview.setReadOnly(True);preview.setAccessibleName(tr('Vorschlag und Beleg'));layout.addWidget(preview,1)
    def select(index):
        if index<0:return
        item=rows[index]
        accept.setText(tr('Erinnerung vergessen') if item.get('operation')=='forget' else tr('Genau so übernehmen'))
        preview.setPlainText(item['text']+'\n\n'+tr('Deine Aussage:')+'\n'+item['evidence']+'\n\n'+item['source'])
        accept.setEnabled(True);reject.setEnabled(True)
    def decide(value):
        index=listing.currentRow()
        if index<0:return
        identity=rows[index]['id'];dialog.accept()
        window.work(tr('Gedächtnisvorschlag prüfen …'),lambda job:worker(job,window.store,'review',identity=identity,accept=value),lambda _:setattr(window,'after_job',window.refresh))
    actions=QHBoxLayout();accept=button(tr('Genau so übernehmen'),lambda:decide(True));reject=button(tr('Ablehnen'),lambda:decide(False))
    accept.setEnabled(False);reject.setEnabled(False)
    actions.addWidget(accept);actions.addWidget(reject);actions.addStretch();actions.addWidget(button(tr('Schließen'),dialog.reject));layout.addLayout(actions)
    listing.addItems([r['title'] for r in rows]);listing.setCurrentRow(-1);listing.currentRowChanged.connect(select)
    if rows:listing.setCurrentRow(0)
    else:preview.setPlainText(tr('Keine Gedächtnisvorschläge vorhanden.'))
    window.memory_review_dialog=dialog;dialog.show()
