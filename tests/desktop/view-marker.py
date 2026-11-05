from PySide6.QtCore import QCoreApplication,QObject,Slot,ClassInfo
from PySide6.QtDBus import QDBusConnection
app=QCoreApplication([]);bus=QDBusConnection.sessionBus()
assert bus.registerService('org.kde.kappmenuview')
@ClassInfo(**{'D-Bus Interface':'org.freedesktop.ScreenSaver'})
class Lock(QObject):
    @Slot(result=bool)
    def GetActive(self):return False
lock=Lock();assert bus.registerService('org.freedesktop.ScreenSaver')
assert bus.registerObject('/ScreenSaver',lock,QDBusConnection.ExportAllSlots)
app.exec()
