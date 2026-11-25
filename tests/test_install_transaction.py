import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerRollbackTests(unittest.TestCase):
    def check_failure(self, failure):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, prefix, commands = (base / name for name in ('source', 'prefix', 'commands'))
            for directory in ('bin', 'native', 'packaging/arch', 'agent-app', 'files'):
                (source / directory).mkdir(parents=True)
            commands.mkdir()
            shutil.copy2(ROOT / 'install.sh', source / 'install.sh')
            shutil.copy2(ROOT / 'packaging/install-transaction.py', source / 'packaging/install-transaction.py')
            shutil.copy2(ROOT / 'packaging/arch/native-build-deps.sh', source / 'packaging/arch')
            (source / 'packaging/third-party.py').symlink_to(ROOT / 'packaging/third-party.py')
            (source / 'packaging/source-identity.py').write_text('print(\'{"revision":"new"}\')\n')
            (source / 'bin/lumen-python').write_text('#!/bin/sh\nexit 0\n')
            (source / 'bin/lumen-python').chmod(0o755)
            for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'uninstall.sh', 'agent-app/main.py'):
                (source / name).write_text('new\n')
            for name in ('capture', 'topbar', 'document', 'service'):
                body = 'exit 31\n' if failure == 'build' and name == 'service' else 'printf new > "$1"\n'
                (source / f'native/build-{name}.sh').write_text('#!/bin/sh\n' + body)
            for name in ('pkg-config', 'cargo', 'rustc', 'pacman'):
                (commands / name).write_text('#!/bin/sh\nexit 0\n')
                (commands / name).chmod(0o755)
            (commands / 'install').write_text('#!/bin/bash\nif [[ "$*" == *agent-app/main.py* ]]; then exit 32; fi\nexec /usr/bin/install "$@"\n')
            (commands / 'install').chmod(0o755)
            before = {'bin/lumen-python': b'old starter', 'files/old.py': b'old module',
                      'THIRD_PARTY_LICENSES.txt': b'old notices', 'install.json': b'{"revision":"old"}', 'qt6-env/keep': b'environment',
                      'models/keep': b'model', 'user-data/keep': b'personal'}
            for name, data in before.items():
                path = prefix / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            env = {'PATH': f'{commands}:/usr/bin:/bin', 'HOME': str(base), 'PREFIX': str(prefix), 'LANG': 'C.UTF-8'}
            result = subprocess.run(['bash', str(source / 'install.sh'), '--no-mcp', '--no-timer'],
                                    env=env, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 31 if failure == 'build' else 32, result.stderr.decode())
            after = {str(path.relative_to(prefix)): path.read_bytes() for path in prefix.rglob('*')
                     if path.is_file() and path.name != '.install.lock'}
            self.assertEqual(after, before)

    def test_build_failure_never_changes_active_code(self):
        self.check_failure('build')

    def test_copy_failure_restores_code_and_revision_preserving_data(self):
        self.check_failure('copy')
