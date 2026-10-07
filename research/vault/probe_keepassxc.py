#!/usr/bin/env python3
"""Synthetic-only engine qualification. Never accepts an existing vault or secret.

Run directly; outputs only format/KDF facts, never exported XML. This is not the
production broker. The test database and all secrets are generated in isolation.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET

PASSWORD = b'SYNTHETIC-ENGINE-PROBE-NOT-A-REAL-SECRET'


def run(*args, password=PASSWORD, fds=()):
    return subprocess.run(['/usr/bin/keepassxc-cli', *args],
                          input=password + b'\n' + password + b'\n',
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          pass_fds=fds, timeout=30, check=False)


def header(path):
    blob = path.read_bytes()
    minor, major = struct.unpack_from('<HH', blob, 8)
    result = {'format': f'{major}.{minor}', 'kdf': 'AES-KDF' if major == 3 else 'unknown'}
    pos = 12
    while pos < min(len(blob), 65536):
        tag = blob[pos]; width = 4 if major >= 4 else 2
        length = int.from_bytes(blob[pos+1:pos+1+width], 'little')
        data = blob[pos+1+width:pos+1+width+length]; pos += 1+width+length
        if tag == 11:
            # Public header variant dictionary; never decrypts anything.
            k = 2
            while k < len(data) and data[k]:
                kind = data[k]; k += 1
                n = int.from_bytes(data[k:k+4], 'little'); k += 4
                key = data[k:k+n]; k += n
                n = int.from_bytes(data[k:k+4], 'little'); k += 4
                value = data[k:k+n]; k += n
                if key == b'$UUID':
                    result['kdf'] = {'c9d9f39a628a4460bf740d08c18a4fea': 'AES-KDF',
                                     '9e298b1956db4773b23dfc3ec6f0a1e6': 'Argon2id',
                                     'ef636ddf8c29444b91f7a9a403e30a0c': 'Argon2d'}.get(value.hex(), value.hex())
        if tag == 0: break
    return result


def probe():
    version = subprocess.run(['/usr/bin/keepassxc-cli', '--version'], capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='lumen-vault-synthetic-') as directory:
        os.chmod(directory, 0o700)
        original, imported = (Path(directory)/name for name in ('original.kdbx', 'imported.kdbx'))
        created = run('db-create', '-q', '-p', '-t', '1000', str(original))
        assert created.returncode == 0, 'Synthetic create failed'
        exported = run('export', '-q', str(original))
        assert exported.returncode == 0 and ET.fromstring(exported.stdout).tag == 'KeePassFile'
        # No plaintext file: the XML stays in an anonymous inherited memory fd.
        fd = os.memfd_create('lumen-synthetic-xml', os.MFD_CLOEXEC)
        try:
            os.write(fd, exported.stdout); os.lseek(fd, 0, os.SEEK_SET)
            result = run('import', '-q', '-p', '-t', '1000', f'/proc/self/fd/{fd}', str(imported), fds=(fd,))
        finally: os.close(fd)
        assert result.returncode == 0, 'Synthetic import failed'
        assert run('export', '-q', str(imported)).returncode == 0
        assert run('export', '-q', str(imported), password=b'WRONG-SYNTHETIC-KEY').returncode != 0
        corrupt = Path(directory)/'corrupt.kdbx'
        data = bytearray(imported.read_bytes()); data[-30] ^= 0x80; corrupt.write_bytes(data)
        assert run('export', '-q', str(corrupt)).returncode != 0
        truncated = Path(directory)/'truncated.kdbx'; truncated.write_bytes(data[:80])
        assert run('export', '-q', str(truncated)).returncode != 0
        return {'engine': 'KeePassXC CLI', 'version': version, 'create': header(original),
                'xml_import': header(imported), 'memory_fd_import': 'passed',
                'wrong_password': 'rejected', 'corrupted_file': 'rejected', 'truncated_file': 'rejected',
                'production_qualified': False,
                'reason': 'CLI cannot select Argon2id; XML import recreates database encryption settings. Full native CRUD and broker review remain open.'}


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
