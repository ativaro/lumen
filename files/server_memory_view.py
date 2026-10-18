"""Confirmed server memory remains a separate, inspectable source."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QCheckBox
from lumen_i18n import tr
from tools_ui import button, label, row
from lumen_connect import shared_memories
from desktop_design import PAGE_MARGIN, PAGE_SPACING


def show_server_memory(parent):
    dialog=QDialog(parent); dialog.setWindowTitle('Lumen · '+tr('Server-Gedächtnis')); dialog.resize(740,580)
    layout=QVBoxLayout(dialog)
    layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
    layout.addWidget(label(tr('Vom Server freigegeben'),'heading'))
    layout.addWidget(label(tr('Diese Erinnerungen bleiben auf dem Server verwaltet. Deine persönlichen Notizen werden nicht verändert. Bei aktivem Gedächtnis kann Lumen sie als Kontext verwenden.'),'muted'))
    listing=QListWidget(); listing.setAccessibleName(tr('Geteilte Erinnerungen')); layout.addWidget(listing)
    text=QPlainTextEdit(); text.setReadOnly(True); text.setAccessibleName(tr('Inhalt und Herkunft')); layout.addWidget(text,2)
    use=QCheckBox(tr('Auf diesem Desktop verwenden')); use.setEnabled(False); layout.addWidget(use)
    notes=shared_memories()
    def selected():
        item=listing.currentItem()
        if not item:return
        note=item.data(Qt.UserRole); key=note['source']+'#'+note['id']
        text.setPlainText(note['body']+'\n\n'+tr('Herkunft: ')+note['source']+'\n'+tr('Revision: ')+str(note['revision']))
        use.blockSignals(True);use.setChecked(key not in parent.store.setting('memory/server_hidden',[]));use.blockSignals(False);use.setEnabled(True)
    def changed(allowed):
        item=listing.currentItem()
        if not item:return
        note=item.data(Qt.UserRole);key=note['source']+'#'+note['id']
        hidden=set(parent.store.setting('memory/server_hidden',[]))
        if allowed:hidden.discard(key)
        else:hidden.add(key)
        parent.store.set_setting('memory/server_hidden',sorted(hidden))
        parent.store.set_setting('memory/privacy_revision',parent.store.setting('memory/privacy_revision',0)+1)
    listing.currentItemChanged.connect(selected);use.toggled.connect(changed)
    for note in notes:
        item=QListWidgetItem(note['title']);item.setToolTip(note['title']);item.setData(Qt.UserRole,note);listing.addItem(item)
    if notes:listing.setCurrentRow(0)
    else:text.setPlainText(tr('Noch keine bestätigten Server-Erinnerungen vorhanden. Verbinde diesen Desktop und gib im Server einzelne Erinnerungen frei.'))
    layout.addWidget(row(button(tr('Fertig'),dialog.accept,'dialog-ok')),0,Qt.AlignRight)
    dialog.exec()
