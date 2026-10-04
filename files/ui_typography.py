"""Shared typography metrics for Studio and the Qt Quick search surface."""
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase, QFont, QTextCursor, QTextBlockFormat


def metrics(settings=None):
    settings = settings if settings is not None else QSettings('Lumen', 'Assistant')
    settings.sync()
    size = max(14, min(22, settings.value('textSize', 17, type=int)))
    compact = settings.value('contentDensity', 'comfortable') == 'compact'
    family = 'Adwaita Sans' if 'Adwaita Sans' in QFontDatabase.families() else 'Noto Sans'
    return dict(fontFamily=family, fontSize=size, spacing=12 if compact else 20,
                rowHeight=size+23 if compact else size+35, compact=compact)


def font(settings=None):
    values = metrics(settings); result = QFont(values['fontFamily'])
    result.setPixelSize(values['fontSize']); return result


def format_document(document, settings=None):
    values = metrics(settings)
    cursor = QTextCursor(document); cursor.select(QTextCursor.Document)
    block = QTextBlockFormat(); block.setLineHeight(140 if values['compact'] else 150, QTextBlockFormat.ProportionalHeight.value)
    block.setBottomMargin(8 if values['compact'] else 12)
    cursor.mergeBlockFormat(block)
