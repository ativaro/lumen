"""Open the account's canonical memory editor, never an old read-only mirror."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QListWidget,QListWidgetItem,QDialogButtonBox,QMessageBox
from lumen_i18n import tr
from lumen_connect import read_config
from tools_ui import label,button
from desktop_design import PAGE_MARGIN,PAGE_SPACING
from uuid import UUID


def show_server_memory(parent):
    config=read_config()
    def open_editor(identity=''):
        if not QDesktopServices.openUrl(QUrl(config['server']+'/?app=memory'+('&document='+identity if identity else ''))):
            raise ValueError(tr('Das Server-Gedächtnis konnte nicht geöffnet werden.'))
    hidden=[]
    for key in parent.store.setting('memory/server_hidden',[]):
        if not isinstance(key,str) or not key.startswith(config['server']+'#'):continue
        try:UUID(key.rsplit('#',1)[-1])
        except ValueError:continue
        hidden.append(key)
    if not hidden:open_editor();return
    # Keep existing device opt-outs reversible without retaining a second content viewer.
    dialog=QDialog(parent);dialog.setWindowTitle(tr('Server-Gedächtnis'));dialog.resize(740,580)
    layout=QVBoxLayout(dialog);layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
    layout.addWidget(label(tr('Auf diesem Desktop ausgeblendet'),'heading'))
    layout.addWidget(label(tr('Diese früheren Ausblendungen bleiben wirksam. Öffne die Erinnerung auf dem Server oder lasse sie hier wieder als Kontext zu. Inhalte und Freigaben verwaltest du auf dem Server.'),'muted'))
    listing=QListWidget();listing.setAccessibleName(tr('Ausgeblendete Erinnerungen'));listing.setSpacing(PAGE_SPACING//2);layout.addWidget(listing)
    for key in hidden:
        item=QListWidgetItem(tr('Erinnerung {0}',key.rsplit('#',1)[-1]));item.setToolTip(key);listing.addItem(item)
    listing.setCurrentRow(0)
    def selected():return hidden[listing.currentRow()] if listing.currentRow()>=0 else ''
    layout.addWidget(button(tr('Auf dem Server öffnen'),lambda:open_editor(selected().rsplit('#',1)[-1])))
    def restore():
        if read_config()!=config:
            QMessageBox.warning(dialog,tr('Server-Gedächtnis'),tr('Die Serververbindung wurde geändert. Bitte erneut öffnen.'));dialog.reject();return
        key=selected()
        if not key:return
        parent.store.set_setting('memory/server_hidden',[v for v in parent.store.setting('memory/server_hidden',[]) if v!=key])
        parent.store.set_setting('memory/privacy_revision',parent.store.setting('memory/privacy_revision',0)+1)
        dialog.accept()
    layout.addWidget(button(tr('Auf diesem Desktop wieder verwenden'),restore))
    actions=QDialogButtonBox(QDialogButtonBox.Close);actions.button(QDialogButtonBox.Close).setText(tr('Schließen'));actions.rejected.connect(dialog.reject);layout.addWidget(actions)
    dialog.exec()
