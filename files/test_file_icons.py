"""File listing symbols must not ask the desktop to inspect each file's contents."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QFileInfo, QMimeDatabase, QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileIconProvider


class FileIconsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def test_filename_matching_never_uses_native_per_file_lookup_and_caches_symbols(self):
        from file_icons import FileIcons
        provider=FileIcons()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a.txt';b=root/'b.txt';a.write_bytes(b'%PDF-1.7');b.write_text('Different content')
            native=QFileIconProvider.icon;calls=[]
            def checked(owner,value):
                self.assertNotIsInstance(value,QFileInfo,'Native per-file lookup may sniff contents and load custom icons')
                return native(owner,value)
            original=provider.mime.mimeTypeForFile
            def mime(name,mode):calls.append((name,mode));return original(name,mode)
            with patch.object(QFileIconProvider,'icon',checked),patch.object(provider.mime,'mimeTypeForFile',side_effect=mime):
                first=provider.icon(QFileInfo(str(a)));second=provider.icon(QFileInfo(str(b)))
                self.assertFalse(first.isNull());self.assertEqual(first.cacheKey(),second.cacheKey())
                self.assertTrue(all(mode==QMimeDatabase.MatchExtension and '/' not in name for name,mode in calls))
                self.assertFalse(provider.icon(QFileInfo(str(root/'missing.unknown'))).isNull())

    def test_symlinks_keep_a_distinct_marker_and_theme_cache_is_bounded(self):
        from file_icons import FileIcons
        provider=FileIcons()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'folder';folder.mkdir();link=root/'link';link.symlink_to(folder)
            self.assertNotEqual(provider.icon(QFileInfo(str(folder))).cacheKey(),provider.icon(QFileInfo(str(link))).cacheKey())
            for index in range(300):provider.named('missing-test-icon-'+str(index),'',False)
            self.assertLessEqual(len(provider.cache),256)
            previous=QIcon.themeName()
            try:
                QIcon.setThemeName('lumen-test-unavailable-theme')
                self.assertFalse(provider.icon(QFileInfo(str(root/'document.txt'))).isNull())
                self.assertLess(len(provider.cache),5)
            finally:QIcon.setThemeName(previous)

    def test_file_model_and_search_share_provider_after_releasing_network(self):
        from file_icons import FileIcons
        from app import Window
        from file_spaces import Catalog
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            root=Path(tmp);window=Window(tmp,QSettings(tmp+'/files.ini',QSettings.IniFormat),Catalog(Store(root/'state')))
            try:
                self.assertIsInstance(window.icon_provider,FileIcons)
                self.assertIs(window.fs.iconProvider(),window.icon_provider)
                window.network.mounts['/nonexistent-test-mount']='smb://example.invalid/share'
                with patch.object(window.network,'release') as release:window.release_unused_network()
                release.assert_called_once()
                self.assertIs(window.fs.iconProvider(),window.icon_provider)
            finally:window.close();window.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()
