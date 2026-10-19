"""Explicit Files transfer activation; old instances cannot silently accept it."""
import subprocess

from PySide6.QtCore import QCoreApplication, ClassInfo, Slot, QTimer
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

from lumen_activation import SingleWindow
from lumen_i18n import tr
from lumen_store import Store
from lumen_transfers import PREFIX
from transfer_followup import identifier


@ClassInfo(**{'D-Bus Interface': 'org.lumen.Application'})
class FilesActivation(SingleWindow):
    def bind_transfer(self, handler):
        self.transfer_handler = handler

    @Slot(str, result=bool)
    def OpenTransfer(self, identity):
        try:
            identity = identifier(identity)
            callback = getattr(self, 'transfer_handler', None)
            if callback is None or not Store().setting(PREFIX + identity):
                return False
            QTimer.singleShot(0, lambda: callback(identity))
            return True
        except ValueError:
            return False


def open_transfer(identity):
    identifier(identity)
    if not Store().setting(PREFIX + identity):
        raise ValueError(tr('Transfer nicht gefunden.'))
    _application = QCoreApplication.instance() or QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    interface = bus.interface()
    if interface and interface.isServiceRegistered('org.lumen.Files').value():
        message = QDBusMessage.createMethodCall('org.lumen.Files', '/Application', 'org.lumen.Application', 'OpenTransfer')
        message.setArguments([identity])
        reply = bus.call(message, QDBus.Block, 5000)
        if reply.type() == QDBusMessage.ErrorMessage or reply.arguments() != [True]:
            raise ValueError(tr('Das laufende Lumen Files kann diesen Transfer nicht anzeigen. Bitte Lumen Files schließen und neu öffnen; die Meldung bleibt erhalten.'))
        return
    from lumen_launch import executable
    subprocess.Popen([executable('lumen-files'), '--transfer', identity], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
