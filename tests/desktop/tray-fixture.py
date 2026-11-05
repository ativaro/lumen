from pathlib import Path
from PySide6.QtCore import QObject,Slot,Property,ClassInfo
from PySide6.QtDBus import QDBusConnection,QDBusMessage
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
@ClassInfo(**{'D-Bus Interface':'org.mpris.MediaPlayer2.Player'})
class Player(QObject):
    def __init__(self):super().__init__();self.playing=False
    @Property(str)
    def PlaybackStatus(self):return 'Playing' if self.playing else 'Paused'
    @Property('QVariantMap')
    def Metadata(self):return {'xesam:title':'Quiet Morning','xesam:artist':['Lumen Test']}
    @Property(bool,constant=True)
    def CanControl(self):return True
    CanPlay=CanControl;CanPause=CanControl;CanGoNext=CanControl;CanGoPrevious=CanControl
    def changed(self):
        signal=QDBusMessage.createSignal('/org/mpris/MediaPlayer2','org.freedesktop.DBus.Properties','PropertiesChanged')
        signal.setArguments(['org.mpris.MediaPlayer2.Player',{'PlaybackStatus':self.PlaybackStatus},[]]);bus.send(signal)
    @Slot()
    def PlayPause(self):self.playing=not self.playing;self.changed()
    @Slot()
    def Next(self):Path('/profile/media-next').write_text('done')
    @Slot()
    def Previous(self):Path('/profile/media-previous').write_text('done')
player=Player();assert bus.registerService('org.mpris.MediaPlayer2.lumenTest');assert bus.registerObject('/org/mpris/MediaPlayer2',player,QDBusConnection.ExportAllSlots|QDBusConnection.ExportAllProperties)
app.exec()
