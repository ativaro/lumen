"""Small folder family shared by the native list, grid and library models."""
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QStandardPaths, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def folder_icons():
    asset = Path(__file__).with_name('folder.svg')
    icons = {'': QIcon(str(asset))}
    # These badges identify the configured XDG locations, never arbitrary names.
    badges = [
        (QStandardPaths.DocumentsLocation, '<path d="M48 44h17l9 9v25H48z M65 44v10h9 M54 62h14 M54 69h10"/>'),
        (QStandardPaths.PicturesLocation, '<rect x="43" y="45" width="34" height="30" rx="2"/><path d="m44 69 9-10 8 8 6-6 9 10"/><circle cx="67" cy="53" r="2"/>'),
        (QStandardPaths.MusicLocation, '<path d="M55 70V48l19-4v22 M55 53l19-4"/><ellipse cx="49" cy="71" rx="6" ry="4"/><ellipse cx="68" cy="67" rx="6" ry="4"/>'),
        (QStandardPaths.MoviesLocation, '<rect x="42" y="46" width="36" height="27" rx="5"/><path d="m56 53 11 7-11 7z" fill="#c8dce7" stroke="none"/>'),
        (QStandardPaths.DownloadLocation, '<path d="M60 44v23 m-9-9 9 9 9-9 M45 73v5h30v-5"/>'),
        (QStandardPaths.DesktopLocation, '<rect x="41" y="44" width="38" height="26" rx="2"/><path d="M60 70v7 M50 78h20"/>'),
    ]
    source = asset.read_text()
    for location, badge in badges:
        path = QStandardPaths.writableLocation(location)
        if not path:
            continue
        svg = source.replace('</svg>', '<g fill="none" stroke="#c8dce7" stroke-opacity=".88" '
                             'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
                             + badge + '</g></svg>')
        # Render once at 3×; paint paths never rasterize assets or access disk.
        pixmap = QPixmap(360, 312); pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, 360, 312))
        painter.end()
        icons[path] = QIcon(pixmap)
    return icons
