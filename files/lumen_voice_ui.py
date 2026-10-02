"""Small native voice activity surface shared by search and Files."""
from collections import deque
import math
import time

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QRadialGradient
from PyQt5.QtWidgets import QWidget


class VoiceActivity(QWidget):
    STATES = {
        'listening': ('Ich höre zu', 'Mikrofon an · Audio bleibt lokal'),
        'transcribing': ('Sprache erkennen', 'Mikrofon aus · lokal verarbeitet'),
        'thinking': ('Lumen denkt nach', 'Mikrofon aus · Antwort entsteht'),
        'preparing': ('Stimme vorbereiten', 'Mikrofon aus · lokale Sprachausgabe'),
        'speaking': ('Lumen spricht', 'Mikrofon aus · du kannst unterbrechen'),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(84)
        self.state = ''; self.level = self.target = 0.; self.updated = 0.
        self.samples = deque([0.] * 25, maxlen=25)
        self.animation = QTimer(self); self.animation.setInterval(33)
        self.animation.timeout.connect(self.tick)
        self.hide()

    def set_state(self, state):
        self.state = state; self.level = self.target = 0.; self.samples = deque([0.] * 25, maxlen=25)
        title, detail = self.STATES.get(state, ('Mikrofon aus', ''))
        self.setAccessibleName(title); self.setAccessibleDescription(detail); self.setToolTip(title + ' · ' + detail)
        self.setVisible(state in self.STATES)
        self.update()

    def set_level(self, value):
        if math.isfinite(value):
            self.target = max(0., min(1., value)); self.updated = time.monotonic()

    def tick(self):
        if time.monotonic() - self.updated > .25: self.target = 0.
        self.level += (self.target - self.level) * .4
        self.samples.append(self.level); self.update()

    def showEvent(self, event):
        if self.state: self.animation.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        if not self.state: return
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette(); accent = palette.color(QPalette.Highlight)
        border = QColor(accent); border.setAlpha(48)
        painter.setPen(QPen(border, 1)); painter.setBrush(palette.base())
        painter.drawRoundedRect(QRectF(.5, .5, self.width()-1, self.height()-1), 16, 16)
        phase = time.monotonic(); center = QPointF(42, 42)
        halo = QRadialGradient(center, 35)
        glow = QColor(accent); glow.setAlpha(45 + int(self.level * 35)); halo.setColorAt(0, glow)
        glow.setAlpha(0); halo.setColorAt(1, glow)
        painter.setPen(Qt.NoPen); painter.setBrush(halo); painter.drawEllipse(center, 35, 35)
        blob = QPainterPath()
        for i in range(81):
            angle = i * math.tau / 80
            radius = 19 + 1.7 * math.sin(angle*3 + phase*1.4) + (1 + self.level*7) * math.sin(angle*2 - phase*1.8)
            point = center + QPointF(math.cos(angle)*radius, math.sin(angle)*radius)
            if i: blob.lineTo(point)
            else: blob.moveTo(point)
        blob.closeSubpath()
        fill = QColor(accent); fill.setAlpha(100 + int(self.level * 110))
        painter.setBrush(fill); painter.setPen(QPen(accent, 1.2)); painter.drawPath(blob)
        title, detail = self.STATES[self.state]
        wide = self.width() >= 440
        text_width = self.width() - 100 - (170 if wide else 0)
        font = self.font(); font.setPixelSize(14); font.setBold(True); painter.setFont(font)
        painter.setPen(palette.color(QPalette.Text))
        painter.drawText(QRectF(82, 20, text_width, 22), Qt.AlignVCenter, painter.fontMetrics().elidedText(title, Qt.ElideRight, text_width))
        font.setPixelSize(11); font.setBold(False); painter.setFont(font); painter.setPen(palette.color(QPalette.Dark))
        painter.drawText(QRectF(82, 44, text_width, 20), Qt.AlignVCenter, painter.fontMetrics().elidedText(detail, Qt.ElideRight, text_width))
        if wide:
            painter.setPen(Qt.NoPen); painter.setBrush(accent)
            if self.state in ('listening', 'speaking'):
                for index, level in enumerate(self.samples):
                    height = 3 + 36 * level
                    painter.drawRoundedRect(QRectF(self.width()-168 + index*6, 42-height/2, 3, height), 1.5, 1.5)
            else:
                for index in range(3):
                    size = 2.5 + .8 * math.sin(phase*3 - index*.8)
                    painter.drawEllipse(QPointF(self.width()-115 + index*14, 42), size, size)
