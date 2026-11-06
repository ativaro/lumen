#!/usr/bin/python3
"""Synthetic source and packaging checks; never installs into the host profile."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_identity', REPO/'packaging/source-identity.py')
identity = importlib.util.module_from_spec(spec); spec.loader.exec_module(identity)


class PackagingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lumen-package-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)/'source'; self.repo.mkdir()
        self.env = patch.dict(os.environ, {}, clear=True); self.env.start(); self.addCleanup(self.env.stop)
        os.environ['PATH'] = '/usr/bin:/bin'
        os.environ['HOME'] = self.temp.name

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def initialize(self):
        for name in ('packaging/source-identity.py', 'packaging/arch/PKGBUILD', 'packaging/arch/build-package.sh', '.gitignore'):
            target = self.repo/name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO/name, target)
        self.git('init', '-b', 'main')
        self.git('remote', 'add', 'origin', 'https://forge.example.invalid/ativaro/lumen.git')
        self.git('add', '.')
        self.git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-m', 'fixture')

    def test_source_identity_survives_archive_and_omits_credentials(self):
        self.initialize()
        self.git('remote', 'set-url', 'origin', 'https://synthetic:credential@forge.example.invalid/ativaro/lumen.git?token=private#private')
        result = identity.identity(self.repo)
        self.assertEqual(result['source_url'], 'https://forge.example.invalid/ativaro/lumen.git')
        self.assertEqual(result['revision'], self.git('rev-parse', 'HEAD'))
        extracted = Path(self.temp.name)/'extracted'; extracted.mkdir()
        (extracted/'source.json').write_text(json.dumps(result))
        self.assertEqual(identity.identity(extracted), result)
        os.environ['LUMEN_SOURCE_URL'] = 'https://forgejo.example/owner/lumen.git'
        self.assertEqual(identity.identity(extracted)['source_url'], os.environ['LUMEN_SOURCE_URL'])

    def test_missing_or_unsafe_source_fails_before_install(self):
        with self.assertRaises(ValueError): identity.identity(self.repo)
        for remote in ('http://example.invalid/repo.git', 'https://example.invalid/repo', 'https://example.invalid:bad/repo.git'):
            (self.repo/'source.json').write_text(json.dumps(dict(revision='a'*40, source_url=remote, source_date_epoch=1)))
            with self.assertRaises(ValueError): identity.identity(self.repo)

    def test_wrong_revision_cannot_label_another_commit(self):
        self.initialize()
        os.environ['LUMEN_SOURCE_REVISION'] = 'a'*40
        with self.assertRaisesRegex(ValueError, 'Quellrevision stimmt nicht'): identity.identity(self.repo)

    def test_archive_is_repeatable_checksums_and_refuses_dirty_source(self):
        self.initialize()
        command = ['bash', str(self.repo/'packaging/arch/build-package.sh'), '--source-only']
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        archive = self.repo/'packaging/arch/lumen-1.2.0.tar.gz'; first = archive.read_bytes()
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(first, archive.read_bytes())
        subprocess.run(['sha256sum', '-c', archive.name+'.sha256'], cwd=archive.parent, check=True, stdout=subprocess.DEVNULL)
        with tarfile.open(archive) as bundle:
            data = json.load(bundle.extractfile('lumen-1.2.0/source.json'))
        self.assertEqual(data['revision'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(data['source_url'], 'https://forge.example.invalid/ativaro/lumen.git')
        (self.repo/'uncommitted.py').write_text('new source')
        failed = subprocess.run(command, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(first, archive.read_bytes())


if __name__ == '__main__': unittest.main()
