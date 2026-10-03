"""Nonvisual Qt APIs shared by the existing widgets and the optional QML pilot.

The Qt 6 entrypoint imports PySide6.QtCore first. Every other entrypoint keeps
Qt 5. Selection is process-local: child tools keep choosing their own binding.
"""
import sys

QT6 = 'PySide6.QtCore' in sys.modules
if QT6 and 'PyQt5.QtCore' in sys.modules:
    raise RuntimeError('A Lumen process must use only one Qt binding')

if QT6:
    from PySide6.QtCore import (QObject, QProcess, QProcessEnvironment, QSettings,
        QTimer, QThread, QUrl, QUrlQuery, QEvent, QLocale, QLibraryInfo, QTranslator,
        Signal as pyqtSignal, Slot as pyqtSlot)
    from shiboken6 import isValid

    def is_deleted(obj):
        return not isValid(obj)
else:
    from PyQt5.QtCore import (QObject, QProcess, QProcessEnvironment, QSettings,
        QTimer, QThread, QUrl, QUrlQuery, QEvent, QLocale, QLibraryInfo, QTranslator,
        pyqtSignal, pyqtSlot)
    from PyQt5.sip import isdeleted as is_deleted
