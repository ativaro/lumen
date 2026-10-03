"""Bounded themed file symbols without desktop content sniffing on the GUI thread."""
from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import QFileInfo, QMimeDatabase
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileIconProvider, QStyle


class FileIcons(QFileIconProvider):
    def __init__(self):
        super().__init__()
        self.mime=QMimeDatabase()
        self.cache=OrderedDict()
        self.theme=None
        self.fallback={kind:QIcon(str(Path(__file__).with_name(asset)))
                       for kind,asset in ((self.IconType.File,'file.svg'),(self.IconType.Folder,'folder.svg'))}
        style=QApplication.style()
        self.links={False:style.standardIcon(QStyle.SP_FileLinkIcon),
                    True:style.standardIcon(QStyle.SP_DirLinkIcon)}

    def icon(self,value):
        if not isinstance(value,QFileInfo):return super().icon(value)
        directory=value.isDir()
        if value.isSymLink():return self.links[directory]
        if directory:return self.named('folder','',True)
        # Only a filename is needed for a listing icon. Opening file contents here
        # stalls QFileSystemModel's GUI updates for large mixed directories.
        mime=self.mime.mimeTypeForFile(value.fileName(),QMimeDatabase.MatchExtension)
        return self.named(mime.iconName(),mime.genericIconName(),False)

    def named(self,name,generic,directory):
        theme=(QIcon.themeName(),tuple(QIcon.themeSearchPaths()))
        if theme!=self.theme:self.cache.clear();self.theme=theme
        key=(name,generic,directory)
        if key not in self.cache:
            fallback=self.fallback[self.IconType.Folder if directory else self.IconType.File]
            icon=QIcon.fromTheme(generic,fallback) if generic else fallback
            if name:icon=QIcon.fromTheme(name,icon)
            # Resolve missing symbols once per type, including the fallback.
            if icon.isNull():icon=fallback
            self.cache[key]=icon
            if len(self.cache)>256:self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        return self.cache[key]
