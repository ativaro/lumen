"""Shared native application themes; never writes KDE settings."""
from lumen_i18n import tr
from pathlib import Path
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap

DEFAULT_DESIGN = 'glass'
DESIGNS = [(tr('Glas'), 'glass'), (tr('Graphit'), 'graphite'), (tr('Atelier'), 'atelier'), (tr('Mitternacht'), 'midnight')]
DESCRIPTIONS = {
    'glass': tr('Rauchblau, Mint und weiche Konturen · Standard'),
    'graphite': tr('Matte Flächen, Jade und ruhige Kontraste'),
    'atelier': tr('Warmes Elfenbein, Oliv und feine Kanten'),
    'midnight': tr('Tiefes Nachtblau und klare Linien'),
}
# Window, content, hover, text, button, border, muted, accent, on-accent.
COLORS = {
    'glass': ('#20343f', '#182b35', '#344f5d', '#f0f6f8', '#2b4350', '#526d79', '#b1c5cf', '#9be5d8', '#123a38'),
    'graphite': ('#252b2e', '#1e2427', '#35403f', '#edf1ef', '#2e3638', '#485453', '#aebcb8', '#72c9b1', '#16372e'),
    'atelier': ('#f2efe8', '#fcfaf5', '#e5e1d6', '#302e29', '#ebe7dd', '#c4bfb2', '#645e54', '#52634f', '#ffffff'),
    'midnight': ('#10151f', '#141c29', '#29364e', '#eef1fa', '#1d283b', '#3d4c65', '#a9b7ce', '#a7b6ff', '#18203d'),
    # Retain the earlier light choice for saved settings and system-style fallback.
    'clear': ('#f5f7fa', '#ffffff', '#eef2f6', '#192333', '#edf1f6', '#dce3ec', '#647184', '#1969d9', '#ffffff'),
}
RADII = {'glass': 16, 'graphite': 10, 'atelier': 8, 'midnight': 6, 'clear': 8, 'system': 8}


def normalize_design(name):
    name = {'lumen': 'graphite', 'studio': 'atelier'}.get(name, name)
    return name if name in COLORS or name == 'system' else DEFAULT_DESIGN


def stylesheet(name):
    name = normalize_design(name)
    radius = RADII[name]
    danger = 'palette(text)' if name == 'system' else '#ab3539' if name in ('atelier', 'clear') else '#ffb9b4'
    style = Path(__file__).with_name('files.qss').read_text() + Path(__file__).with_name('gallery.qss').read_text()
    style += f"""
QPushButton {{ border-radius: {radius}px; }}
QPushButton#toolButton, QPushButton#iconButton {{ border-radius: {min(radius, 12)}px; }}
QLineEdit, QComboBox, QPlainTextEdit {{ border-radius: {min(radius, 12)}px; }}
QFrame#searchSurface {{ border-radius: {radius + 10}px; }}
QFrame#searchInput {{ border-radius: {radius + 14}px; }}
QPushButton#searchSend {{ border-radius: {radius + 4}px; }}
QPushButton#themeChoice {{ border-radius: {radius}px; }}
QPushButton#danger, QPushButton#galleryTrash {{ color: {danger}; }}
"""
    if name == 'glass':
        style += """
QFrame#searchSurface {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(57, 85, 100, 230), stop:0.5 rgba(28, 52, 66, 236), stop:1 rgba(41, 73, 89, 230));
    border: 1px solid rgba(173, 208, 224, 125);
}
QFrame#searchInput { background: rgba(190, 225, 239, 12); border-color: rgba(190, 225, 239, 125); }
QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #344f5d, stop:1 #2b4350); }
QPushButton#primary, QPushButton#searchSend {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b5eee2, stop:1 #8bdece);
}
QPushButton#primary:hover, QPushButton#searchSend:hover { background: #b5eee2; }
QPushButton#primary:pressed, QPushButton#searchSend:pressed { background: #7dcebe; }
QPushButton#toolButton, QPushButton#iconButton, QPushButton#quiet,
QPushButton#sideAction, QPushButton#crumb, QPushButton#chip, QPushButton#shelfButton,
QPushButton#assistantButton { background: transparent; }
QPushButton#toolButton:hover, QPushButton#iconButton:hover, QPushButton#quiet:hover,
QPushButton#sideAction:hover, QPushButton#crumb:hover, QPushButton#chip:checked,
QPushButton#shelfButton:hover, QPushButton#assistantButton:hover { background: palette(midlight); }
"""
    return style


def apply_design(app, name):
    name = normalize_design(name)
    app.setProperty('lumenDesign', name)
    if name == 'system':
        from app import apply_system_appearance
        app.setStyleSheet('')
        app.setPalette(app.style().standardPalette())
        apply_system_appearance(app, Path.home() / '.config/kdeglobals')
        return
    window, base, alternate, text, button, border, muted, accent, on_accent = COLORS[name]
    palette = QPalette()
    for role, value in [(QPalette.Window, window), (QPalette.Base, base), (QPalette.AlternateBase, alternate),
        (QPalette.Text, text), (QPalette.WindowText, text), (QPalette.ButtonText, text),
        (QPalette.Button, button), (QPalette.Mid, border), (QPalette.Midlight, alternate),
        (QPalette.Dark, muted), (QPalette.PlaceholderText, muted), (QPalette.Link, accent),
        (QPalette.Highlight, accent), (QPalette.HighlightedText, on_accent),
        (QPalette.ToolTipBase, base), (QPalette.ToolTipText, text)]:
        palette.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(muted))
    app.setStyleSheet(''); app.setPalette(palette)
    QIcon.setThemeName('breeze-dark' if QColor(window).lightness() < 128 else 'breeze')
    app.setStyleSheet(stylesheet(name))


def theme_icon(name):
    """Small native swatch showing the actual surface, accent and button shape."""
    window, base, _, foreground, _, border, _, accent, on_accent = COLORS[name]
    image = QPixmap(200, 120); image.setDevicePixelRatio(2); image.fill(Qt.transparent)
    painter = QPainter(image); painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(border)); painter.setBrush(QColor(base))
    painter.drawRoundedRect(QRectF(1, 1, 98, 58), 8, 8)
    painter.setPen(Qt.NoPen); painter.setBrush(QColor(window))
    painter.drawRoundedRect(QRectF(7, 8, 86, 16), 4, 4)
    painter.setPen(QColor(foreground)); painter.drawLine(13, 16, 62, 16)
    painter.setPen(Qt.NoPen); painter.setBrush(QColor(accent))
    radius = min(RADII[name] / 2, 10)
    painter.drawRoundedRect(QRectF(7, 32, 48, 20), radius, radius)
    painter.setPen(QColor(on_accent)); painter.drawLine(17, 42, 43, 42)
    painter.setPen(QColor(border)); painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(61, 32, 31, 20), radius, radius)
    painter.end()
    return QIcon(image)
