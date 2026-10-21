import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings,QSize
from PySide6.QtWidgets import QPushButton,QLabel
from test_settings_navigation import SettingsFixture
from test_server_app_window import PrivateHostFixture


class DesktopServerSettingsTest(SettingsFixture):
    def test_server_panels_keep_real_local_window_option_without_fake_selection_or_model_controls(self):
        d=self.dialog
        for key in ('wissen','workbench','code','meetings','vault','inbox'):
            self.assertEqual(set(d.app_controls[key]),{'restoreGeometry'})
            page=d.stack.widget(d.app_pages[key])
            captions=[b.text() for b in page.findChildren(QPushButton)]
            self.assertIn('Gerätefreigaben auf dem Server öffnen',captions)
            self.assertNotIn('Sprache, Modell und Arbeitsweise',captions)
            self.assertNotIn('Spracheingabe und Einrichtung',captions)
        self.assertIn('restoreSelection',d.app_controls['reader'])
        self.assertNotIn('radio',d.app_controls)

    def test_vault_and_backups_have_distinct_titles_and_real_launch_routes(self):
        d=self.dialog;page=d.stack.widget(d.app_pages['vault'])
        self.assertEqual(d.page_info[d.app_pages['vault']]['title'],'Lumen Vault')
        with patch('lumen_apps.QProcess.startDetached',return_value=(True,42)) as launch:
            next(b for b in page.findChildren(QPushButton) if b.text()=='App öffnen').click()
            self.assertTrue(launch.call_args.args[0].endswith('lumen-vault'))
            next(b for b in page.findChildren(QPushButton) if b.text()=='Lokale Sicherungspläne öffnen').click()
            self.assertTrue(launch.call_args.args[0].endswith('lumen-system'))
            self.assertEqual(launch.call_args.args[1],['--page','backups'])

    def test_settings_geometry_survives_close_and_files_only_can_close(self):
        from settings_dialog import SettingsDialog
        d=self.dialog;d.resize(1160,810);d.reject()
        later=SettingsDialog(assistant_settings=self.settings,files_settings=self.files,load_system=False)
        self.assertEqual((later.size().width(),later.size().height()),(1160,810));later.close();later.deleteLater()
        files=SettingsDialog(assistant_settings=self.settings,files_settings=self.files,files_only=True)
        files.show();files.resize(900,780);files.reject()
        self.assertFalse(files.isVisible());self.assertTrue(self.settings.contains('windows/settings/files'));files.deleteLater()


class ServerHostGeometryTest(PrivateHostFixture):
    def test_each_app_uses_its_approved_default_bounded_to_the_screen(self):
        preferences=QSettings('Lumen','Assistant')
        for app,size in {'code':(1531,1291),'audio':(1400,1399),
                         'projects':(1866,1159),'notes':(1658,1015)}.items():
            with self.subTest(app=app):
                preferences.remove('windows/server/'+app+'/geometry');preferences.sync()
                window=self.import_window(drive=False,pilot=True,app=app)
                available=window.screen().availableGeometry().adjusted(24,24,-24,-24)
                self.assertEqual(window.size(),QSize(*size).boundedTo(available.size()))

    def test_normal_server_window_uses_large_default_and_remembers_size(self):
        preferences=QSettings('Lumen','Assistant')
        preferences.remove('windows/server/code/geometry')
        preferences.setValue('apps/code/restoreGeometry',True);preferences.sync()
        window=self.import_window(drive=False,pilot=True,app='code')
        available=window.screen().availableGeometry().adjusted(24,24,-24,-24)
        self.assertEqual(window.size(),QSize(1531,1291).boundedTo(available.size()))
        window.resize(1280,820);window.close();self.wait(lambda:window._disposed)
        reopened=self.import_window(drive=False,pilot=True,app='code')
        self.assertEqual((reopened.width(),reopened.height()),(1280,820))
