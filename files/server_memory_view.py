"""Open the account's canonical memory editor, never an old read-only mirror."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from lumen_i18n import tr
from lumen_connect import read_config


def show_server_memory(parent):
    if not QDesktopServices.openUrl(QUrl(read_config()['server']+'/?app=memory')):
        raise ValueError(tr('Das Server-Gedächtnis konnte nicht geöffnet werden.'))
