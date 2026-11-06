"""Shared desktop sizing: useful defaults, remembered geometry and visible controls."""
from PySide6.QtCore import QByteArray, QRect, QSize
from PySide6.QtGui import QGuiApplication


def fit(window, default=None):
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is None: return
    available = screen.availableGeometry().adjusted(24, 24, -24, -24)
    if available.width() < 1 or available.height() < 1: return
    if window.isMaximized() or window.isFullScreen(): return
    window.setMinimumSize(window.minimumSize().boundedTo(available.size()))
    size = (QSize(*default) if default else window.size()).boundedTo(available.size())
    window.resize(size)
    bounds = QRect(window.pos(), window.size())
    if default: bounds.moveCenter(available.center())
    bounds.moveLeft(max(available.left(), min(bounds.left(), available.right()-bounds.width()+1)))
    bounds.moveTop(max(available.top(), min(bounds.top(), available.bottom()-bounds.height()+1)))
    window.move(bounds.topLeft())


def restore(window, settings, key, default, enabled=True):
    geometry = settings.value(key) if enabled else None
    restored = bool(isinstance(geometry,(QByteArray,bytes,bytearray)) and geometry and window.restoreGeometry(geometry))
    fit(window, None if restored else default)


def remember(window, settings, key):
    settings.setValue(key, window.saveGeometry())
    settings.sync()
