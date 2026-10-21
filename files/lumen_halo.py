"""Decorative working mark, shared by native conversation surfaces."""
from pathlib import Path
import time
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QWidget


class LumenHalo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.mark = QIcon(str(Path(__file__).with_name('lumen-mark.svg')))
        self.active = False
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.hints = QApplication.styleHints()
        self.accessibility = self.hints.accessibility() if hasattr(self.hints, 'accessibility') else None
        if self.accessibility:
            self.accessibility.motionPreferenceChanged.connect(self.update_running)

    def setActive(self, active):
        self.active = bool(active)
        self.update_running()

    def update_running(self, *_):
        animate = (self.active and self.isVisible()
                   and not (self.accessibility and self.accessibility.motionPreference() == Qt.ReducedMotion)
                   and QApplication.style().styleHint(QStyle.SH_Widget_Animate))
        if animate: self.timer.start()
        else: self.timer.stop(); self.angle = 0; self.update()

    def showEvent(self, event):
        super().showEvent(event); self.update_running()

    def hideEvent(self, event):
        super().hideEvent(event); self.update_running()

    def tick(self):
        self.angle = time.monotonic() % 1.6 * 225
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.translate(self.width()/2, self.height()/2)
        painter.rotate(self.angle)
        painter.translate(-self.width()/2, -self.height()/2)
        self.mark.paint(painter, self.rect())
