"""Run the local bootstrap with disposable modules and package-manager doubles."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class BootstrapTest(unittest.TestCase):
    def run_bootstrap(self, provide_modules):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        root = Path(temp)
        source, tools, modules = (root / name for name in ('source', 'bin', 'modules'))
        for folder in (source, tools, modules): folder.mkdir()
        repo = Path(__file__).resolve().parents[1]
        shutil.copyfile(repo / 'bootstrap.sh', source / 'bootstrap.sh')
        (source / 'packaging/arch').mkdir(parents=True)
        shutil.copy(repo / 'packaging/arch/native-build-deps.sh', source / 'packaging/arch')
        # The previous bootstrap dependencies exist; only the Notes' Markdown module is absent.
        qt = modules / 'PySide6'; qt.mkdir(); (qt / '__init__.py').touch()
        for name in ('QtWidgets', 'QtSvg', 'QtQuick', 'QtQuickWidgets', 'QtDBus'):
            (qt / (name + '.py')).touch()
        for name in ('gi', 'PIL', 'dbus'): (modules / (name + '.py')).touch()
        def command(name, text):
            path = tools / name; path.write_text('#!/bin/bash\nset -eu\n' + text); path.chmod(0o755)
        command('id', 'printf "1000\\n"\n')
        command('qdbus6', 'exit 0\n')
        command('pacman', '''printf 'pacman %s\\n' "$*" >> "$TEST_TRACE"
if [ "$1" = -T ]; then
    for package in "$@"; do
        case "$package" in python-markdown-it-py) exit 127;; esac
    done
    exit 0
fi
exit 99
''')
        command('sudo', '''printf 'sudo %s\\n' "$*" >> "$TEST_TRACE"
[ "$1" = pacman ] && [ "$2" = -S ]
for module in $TEST_PROVIDE_MODULES; do
    printf '' > "$PYTHONPATH/$module.py"
done
''')
        command('python-check', 'exec "$TEST_PYTHON" -S "$@"\n')
        (source / 'install.sh').write_text('''#!/bin/bash
set -eu
printf 'install\\n' >> "$TEST_TRACE"
mkdir -p "$PREFIX/bin"
printf '#!/bin/bash\\nprintf "wizard\\\\n" >> "$TEST_TRACE"\\n' > "$PREFIX/bin/lumen-setup-wizard"
chmod +x "$PREFIX/bin/lumen-setup-wizard"
''')
        env = dict(os.environ, PATH=str(tools) + os.pathsep + '/usr/bin',
                   PREFIX=str(root / 'installed'), PYTHONPATH=str(modules),
                   LUMEN_PYTHON=str(tools / 'python-check'), TEST_PYTHON=sys.executable,
                   TEST_TRACE=str(root / 'trace'), TEST_PROVIDE_MODULES=provide_modules,
                   XDG_CURRENT_DESKTOP='KDE', DBUS_SESSION_BUS_ADDRESS='synthetic', DISPLAY=':synthetic')
        result = subprocess.run(['bash', str(source / 'bootstrap.sh'), '--local'],
                                env=env, capture_output=True, text=True, timeout=10)
        return result, (root / 'trace').read_text()

    def test_missing_notes_modules_install_before_real_import_check(self):
        result, trace = self.run_bootstrap('markdown_it')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = trace.splitlines()
        self.assertIn('python-markdown-it-py', commands[0])
        self.assertTrue(commands[1].startswith('sudo pacman -S --needed --noconfirm -- '))
        self.assertIn('python-markdown-it-py', commands[1])
        for package in ('gcc', 'pkgconf', 'make', 'cmake', 'qt6-base', 'qt6-declarative',
                        'layer-shell-qt', 'libdbusmenu-glib'):
            self.assertIn(package, commands[0].split())
            self.assertIn(package, commands[1].split())
        self.assertEqual(commands[2:], ['install', 'wizard'])

    def test_unavailable_modules_stop_before_installer_and_wizard(self):
        for available in ('',):
            with self.subTest(available=available):
                result, trace = self.run_bootstrap(available)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ModuleNotFoundError', result.stderr)
                self.assertNotIn('\ninstall\n', '\n' + trace)
                self.assertNotIn('\nwizard\n', '\n' + trace)


if __name__ == '__main__': unittest.main()
