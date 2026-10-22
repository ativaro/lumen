import configparser
import gzip
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from appearance import COLORS, DESIGNS
from lumen_desktop_theme import ARTWORK, apply, prepare, prepare_decoration


class DesktopThemeTest(unittest.TestCase):
    def test_bundled_desktop_installs_in_an_empty_profile_and_preserves_existing_art(self):
        import os
        from lumen_desktop_setup import install_resources
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}):
            root = install_resources()
            for _, name in DESIGNS:
                self.assertTrue((root / 'plasma/desktoptheme' / ('org.lumen.' + name) / 'colors').is_file())
                decoration = root / 'aurorae/themes' / ('org.lumen.fine.' + name)
                self.assertTrue((decoration / (decoration.name + 'rc')).is_file())
                self.assertTrue((decoration / 'minimize.svg').is_file())
            self.assertEqual(len(list((root / 'wallpapers').iterdir())), 11)
            wallpaper = root / 'wallpapers/LumenLichtstrom/metadata.json'
            wallpaper.write_text('{"personal-edit": true}')
            install_resources()
            self.assertEqual(wallpaper.read_text(), '{"personal-edit": true}')

    def test_fine_decorations_match_all_palettes_without_overwriting_previous_art(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'LumenGraphite'
            shutil.copytree(ARTWORK / 'aurorae/LumenGraphite', source)
            before = {p.name: p.read_bytes() for p in source.iterdir()}
            for _, name in DESIGNS:
                target = prepare_decoration(name, Path(tmp) / 'themes', source)
                config = configparser.ConfigParser(); config.read(target / (target.name + 'rc'))
                for key, color in (('ActiveTextColor', COLORS[name][3]), ('InactiveTextColor', COLORS[name][6])):
                    self.assertEqual(config['General'][key], ','.join(str(int(color[i:i+2],16)) for i in (1,3,5)))
                self.assertIn(COLORS[name][0], (target / 'decoration.svg').read_text())
                self.assertEqual(config['Layout']['ButtonWidth'], '32')
                self.assertEqual(config['Layout']['ButtonHeight'], '32')
                from PySide6.QtSvg import QSvgRenderer
                for button in ('minimize', 'maximize', 'restore', 'close'):
                    art = (target / (button + '.svg')).read_text()
                    self.assertIn(COLORS[name][3], art)
                    renderer = QSvgRenderer(str(target / (button + '.svg')))
                    self.assertTrue(renderer.isValid())
                    for state in ('active', 'inactive', 'hover', 'pressed', 'hover-inactive',
                                  'pressed-inactive', 'deactivated', 'deactivated-inactive'):
                        self.assertEqual(renderer.boundsOnElement(state + '-center').width(), 32)
                        bounds = renderer.boundsOnElement(state + '-glyph')
                        self.assertLessEqual(bounds.width(), 22.4)
                        self.assertLessEqual(bounds.height(), 19.6)
                        self.assertAlmostEqual(bounds.center().x(), 16, delta=0.1)
                        self.assertAlmostEqual(bounds.center().y(), 16, delta=0.1)
                    self.assertIn('stroke-width="1.6"', art)
                    self.assertNotIn('scale(', art)
                    if button != 'close': self.assertIn(COLORS[name][7], art)
                self.assertEqual(prepare_decoration(name, target.parent, source), target)
            self.assertEqual({p.name: p.read_bytes() for p in source.iterdir()}, before)
            with self.assertRaises(ValueError): prepare_decoration('../escape', Path(tmp) / 'themes', source)
            (target / 'metadata.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'nicht überschrieben'):
                prepare_decoration(name, target.parent, source)

    def test_apply_moves_buttons_right_with_backup_and_guards_undo(self):
        state = {'library': 'org.kde.kwin.aurorae.v2', 'theme': '__aurorae__svg__LumenGraphite', 'ButtonsOnLeft': 'XIA', 'ButtonsOnRight': ''}
        def run(args):
            if args[0] == 'qdbus6': return ''
            key = args[args.index('--key') + 1]
            if args[0] == 'kwriteconfig6': state[key] = args[-1]; return ''
            return 'org.lumen.glass' if key == 'name' else state[key]
        with patch('lumen_desktop_theme.prepare', return_value=Path('org.lumen.glass')), \
             patch('lumen_desktop_theme.prepare_decoration', return_value=Path('org.lumen.fine.glass')), \
             patch('desktop_settings.backup') as backup, patch('desktop_settings.run', side_effect=run) as commands:
            self.assertEqual(apply({'design':'glass'})['decoration'], 'org.lumen.fine.glass')
            self.assertEqual(state['theme'], '__aurorae__svg__org.lumen.fine.glass')
            self.assertEqual(state['ButtonsOnLeft'], '')
            self.assertEqual(state['ButtonsOnRight'], 'IAX')
            self.assertEqual(backup.call_args.args[1]['decoration_before']['ButtonsOnLeft'], 'XIA')
            apply({'design':'glass', 'expected':'org.lumen.glass'})
            self.assertIn((['qdbus6', 'org.kde.KWin', '/KWin', 'org.kde.KWin.reconfigure'],), [c.args for c in commands.call_args_list])
            state['theme'] = 'manually-selected-decoration'
            with self.assertRaisesRegex(ValueError, 'Fensterdekoration wurde inzwischen geändert'):
                apply({'design':'glass', 'expected':'org.lumen.glass'})
            self.assertEqual(state['theme'], 'manually-selected-decoration')

    def test_selected_echo_frame_upgrades_to_fine_and_keeps_theme(self):
        from lumen_desktop_theme import refresh_decoration
        state = {'library': 'org.kde.kwin.aurorae.v2',
                 'theme': '__aurorae__svg__org.lumen.echo.glass',
                 'ButtonsOnLeft': '', 'ButtonsOnRight': 'IAX'}
        before = dict(state)
        def run(args):
            if args[0] == 'qdbus6': return ''
            key = args[args.index('--key') + 1]
            if args[0] == 'kwriteconfig6': state[key] = args[-1]; return ''
            return state[key]
        with patch('desktop_settings.run', side_effect=run), patch('desktop_settings.backup') as backup, \
             patch('lumen_desktop_theme.prepare_decoration', return_value=Path('org.lumen.fine.glass')) as prepare:
            self.assertTrue(refresh_decoration())
            prepare.assert_called_once_with('glass')
            self.assertEqual(state['theme'], '__aurorae__svg__org.lumen.fine.glass')
            self.assertEqual(state['ButtonsOnRight'], before['ButtonsOnRight'])
            self.assertEqual(backup.call_args.args[1]['decoration_before'], before)
            self.assertFalse(refresh_decoration())

    def test_refresh_only_migrates_legacy_lumen_and_rolls_back_on_failure(self):
        from lumen_desktop_theme import refresh_decoration
        state = {'library': 'org.kde.kwin.aurorae.v2',
                 'theme': '__aurorae__svg__org.lumen.graphite',
                 'ButtonsOnLeft': 'XIA', 'ButtonsOnRight': ''}
        before = dict(state)
        fail = False
        def run(args):
            if args[0] == 'qdbus6':
                if fail and state != before: raise RuntimeError('KWin unavailable')
                return ''
            key = args[args.index('--key') + 1]
            if args[0] == 'kwriteconfig6': state[key] = args[-1]; return ''
            return state[key]
        with patch('desktop_settings.run', side_effect=run), patch('desktop_settings.backup'), \
             patch('lumen_desktop_theme.prepare_decoration', return_value=Path('org.lumen.fine.graphite')) as prepare:
            fail = True
            with self.assertRaisesRegex(RuntimeError, 'KWin unavailable'): refresh_decoration()
            self.assertEqual(state, before)
            fail = False
            self.assertTrue(refresh_decoration())
            self.assertEqual(state['ButtonsOnRight'], 'IAX')
            prepare.reset_mock()
            self.assertFalse(refresh_decoration())
            prepare.assert_not_called()
            for theme, library in [('custom', before['library']), (before['theme'], 'org.kde.breeze')]:
                state.update(theme=theme, library=library)
                custom = dict(state)
                self.assertFalse(refresh_decoration())
                self.assertEqual(state, custom)
                prepare.assert_not_called()

    def test_failed_activation_preserves_absent_kde_defaults(self):
        from lumen_desktop_theme import current_decoration, decoration_settings, set_decoration
        state = {}
        def run(args):
            if args[0] == 'qdbus6':
                if state: raise RuntimeError('KWin unavailable')
                return ''
            key = args[args.index('--key') + 1]
            if args[0] == 'kwriteconfig6':
                if '--delete' in args: state.pop(key, None)
                else: state[key] = args[-1]
                return ''
            return state.get(key, args[args.index('--default') + 1])
        with patch('desktop_settings.run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'KWin unavailable'):
                set_decoration(decoration_settings('org.lumen.fine.glass'), current_decoration())
            self.assertEqual(state, {})

    def test_native_variants_match_app_palette_without_changing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'base'; (source / 'widgets').mkdir(parents=True)
            (source / 'metadata.json').write_text(json.dumps({'KPlugin': {'Id': 'base'}}))
            (source / 'colors').write_text('[Colors:Window]\nForegroundNormal=255,255,255\n')
            svg = b'<svg><rect id="north-center" fill="#212b2f" opacity="0.94"/><rect id="north-mask-center" fill="#000000"/><rect fill="#61c8c1"/></svg>'
            (source / 'widgets/panel-background.svgz').write_bytes(gzip.compress(svg))
            destination = Path(tmp) / 'themes'
            for _, name in DESIGNS:
                with self.subTest(name=name):
                    target = prepare(name, destination, source)
                    config = configparser.ConfigParser(); config.read(target / 'colors')
                    def rgb(color): return ','.join(str(int(color[i:i+2],16)) for i in (1,3,5))
                    self.assertEqual(config['Colors:Window']['ForegroundNormal'], rgb(COLORS[name][3]))
                    self.assertEqual(config['Colors:Window']['BackgroundNormal'], rgb(COLORS[name][0]))
                    self.assertEqual(config['Colors:Button']['DecorationFocus'], rgb(COLORS[name][7]))
                    art = gzip.decompress((target / 'widgets/panel-background.svgz').read_bytes()).decode()
                    self.assertIn(COLORS[name][0],art); self.assertIn('fill="#000000"',art)
                    self.assertEqual(prepare(name,destination,source),target)
            self.assertEqual(gzip.decompress((source/'widgets/panel-background.svgz').read_bytes()),svg)
            with self.assertRaises(ValueError): prepare('../escape',destination,source)
            target = destination/'org.lumen.glass'
            (target/'metadata.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'nicht überschrieben'): prepare('glass',destination,source)

    def test_appearance_history_restores_the_desktop_together_with_app(self):
        import os
        from PySide6.QtCore import QSettings
        from lumen_store import Store
        from lumen_history import record, undo_record
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA':tmp+'/state', 'XDG_CONFIG_HOME':tmp+'/config'}):
            # Use the isolated test runner's application config, never the desktop's.
            original_root = str(Path(QSettings('Lumen','Assistant').fileName()).parent.parent)
            QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, tmp + '/config')
            settings=QSettings('Lumen','Assistant')
            self.assertTrue(Path(settings.fileName()).is_relative_to(tmp))
            try:
                settings.setValue('appearance','atelier');settings.sync()
                store=Store()
                identity=record(store,'Theme','preferences',{'appearance':'glass'},{'appearance':'atelier'},settings.fileName())
                with patch('lumen_desktop_theme.apply') as apply:
                    undo_record(store,identity)
                    apply.assert_called_once_with({'design':'glass','expected':'org.lumen.atelier'})
                settings.sync();self.assertEqual(settings.value('appearance'),'glass')
            finally:
                QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, original_root)
