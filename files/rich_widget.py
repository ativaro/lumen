"""Embed the same Qt Quick result components used by Search into Studio."""
from pathlib import Path
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtQuickWidgets import QQuickWidget
from ui_typography import metrics


def palette_theme(settings):
    from PySide6.QtWidgets import QApplication
    palette = QApplication.palette()
    roles = (QPalette.Window, QPalette.Base, QPalette.AlternateBase, QPalette.Text,
             QPalette.Button, QPalette.Mid, QPalette.PlaceholderText, QPalette.Highlight, QPalette.HighlightedText)
    result = dict(zip(('window','base','hover','text','button','border','muted','accent','onAccent'),
                      (palette.color(role).name() for role in roles)))
    result.update(metrics(settings));result['radius']=10
    return result


class RichWidget(QQuickWidget):
    def __init__(self, controller, settings, parent=None):
        super().__init__(parent)
        self.controller=controller;self.settings=settings
        self.resize_timer=QTimer(self);self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.fit)
        self.setResizeMode(QQuickWidget.SizeRootObjectToView)
        theme=palette_theme(settings)
        # Results share the chat background; transparency needlessly retains
        # underlying pixels when the scroll area moves/resizes the Quick layer.
        self.setClearColor(QColor(theme['window']))
        self.setInitialProperties(dict(view=controller,theme=theme))
        self.setSource(QUrl.fromLocalFile(str(Path(__file__).parent/'qml/search/ResultView.qml')))
        root=self.rootObject()
        if root:root.implicitHeightChanged.connect(lambda:self.resize_timer.start(0))
        controller.changed.connect(lambda:self.resize_timer.start(0));self.fit()

    def fit(self):
        self.setVisible(self.controller.active)
        if self.rootObject():
            height=max(1,round(self.rootObject().implicitHeight()))
            if self.height()!=height:self.setFixedHeight(height)

    def refresh(self):
        theme=palette_theme(self.settings)
        self.setClearColor(QColor(theme['window']))
        if self.rootObject():self.rootObject().setProperty('theme',theme)
        self.fit()
