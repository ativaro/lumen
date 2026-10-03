"""Shared nonvisual Qt 6 APIs and QObject lifetime checks."""
from PySide6.QtCore import (QObject, QProcess, QProcessEnvironment, QSettings,
    QTimer, QThread, QUrl, QUrlQuery, QEvent, QLocale, QLibraryInfo, QTranslator,
    Signal, Slot)
from shiboken6 import isValid


def is_deleted(obj):
    return not isValid(obj)
