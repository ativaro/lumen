from pathlib import Path
from PySide6.QtCore import QObject,Slot
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QIcon,QPixmap,QColor
from PySide6.QtWidgets import QApplication,QSystemTrayIcon,QMenu
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
pixmap=QPixmap(32,32);pixmap.fill(QColor('#76b8a9'))
tray=QSystemTrayIcon(QIcon(pixmap));tray.setToolTip('Lumen Tray Test')
menu=QMenu();action=menu.addAction('Tray-Testaktion');action.triggered.connect(lambda:Path('/profile/tray-action.txt').write_text('done'))
tray.setContextMenu(menu);tray.show()
class Control(QObject):
    @Slot()
    def hide(self):tray.hide()
    @Slot()
    def quit(self):app.quit()
control=Control();bus=QDBusConnection.sessionBus();assert bus.registerService('org.lumen.TrayTest');assert bus.registerObject('/Control',control,QDBusConnection.ExportAllSlots)
app.exec()
