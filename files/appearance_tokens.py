"""Shared colors and geometry for QWidget and QML surfaces."""
from lumen_i18n import tr

DEFAULT_DESIGN = 'glass'
DESIGNS = [(tr('Glas'), 'glass'), (tr('Graphit'), 'graphite'), (tr('Atelier'), 'atelier'), (tr('Mitternacht'), 'midnight')]
DESCRIPTIONS = {
    'glass': tr('Rauchblau, Mint und weiche Konturen · Standard'),
    'graphite': tr('Matte Graphitflächen, Silber und ruhige Kontraste'),
    'atelier': tr('Warmes Elfenbein, Oliv und feine Kanten'),
    'midnight': tr('Tiefes Nachtblau und klare Linien'),
}
# Window, content, hover, text, button, border, muted, accent, on-accent.
COLORS = {
    'glass': ('#20343f', '#182b35', '#344f5d', '#f0f6f8', '#2b4350', '#526d79', '#b1c5cf', '#9be5d8', '#123a38'),
    'graphite': ('#222529', '#1a1c1f', '#2a2e33', '#eff1f3', '#2a2e33', '#393e45', '#aab1ba', '#d7dce2', '#1a1c1f'),
    'atelier': ('#f2efe8', '#fcfaf5', '#e5e1d6', '#302e29', '#ebe7dd', '#c4bfb2', '#645e54', '#52634f', '#ffffff'),
    'midnight': ('#10151f', '#141c29', '#29364e', '#eef1fa', '#1d283b', '#3d4c65', '#a9b7ce', '#a7b6ff', '#18203d'),
    # Retain the earlier light choice for saved settings and system-style fallback.
    'clear': ('#f5f7fa', '#ffffff', '#eef2f6', '#192333', '#edf1f6', '#dce3ec', '#647184', '#1969d9', '#ffffff'),
}
RADII = {'glass': 16, 'graphite': 10, 'atelier': 8, 'midnight': 6, 'clear': 8, 'system': 8}

# The Panorama key faces used by the server navigation and native topbar.
TOPBAR_KEYS = {
    'graphite': ('#292d32', '#1d2024', '#12ffffff', '#65000000', '#94d8c9', '#d3f6ec'),
    'glass': ('#29434f', '#172b35', '#14ffffff', '#75071923', '#94d8c9', '#d3f6ec'),
    'atelier': ('#f6f3ec', '#e8e4dc', '#ddffffff', '#25524939', '#2f6653', '#253f35'),
    'midnight': ('#1c2737', '#0d1522', '#12ffffff', '#65000000', '#b2bfff', '#e2e9ff'),
}


def normalize_design(name):
    name = {'lumen': 'graphite', 'studio': 'atelier'}.get(name, name)
    return name if name in COLORS or name == 'system' else DEFAULT_DESIGN


