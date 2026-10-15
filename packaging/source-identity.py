#!/usr/bin/python3
"""Keep installer and archive provenance independent of a local Git checkout."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit


def identity(repo):
    repo = Path(repo).resolve()
    saved = json.loads((repo/'source.json').read_text()) if (repo/'source.json').is_file() else {}
    def git(*args):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else ''
    own_git = git('rev-parse', '--show-toplevel') == str(repo)
    head = git('rev-parse', 'HEAD') if own_git else saved.get('revision', '')
    revision = os.environ.get('LUMEN_SOURCE_REVISION') or head
    if head and revision != head:
        raise ValueError('Quellrevision stimmt nicht mit dem Quellstand überein.')
    remote = os.environ.get('LUMEN_SOURCE_URL') or (git('remote', 'get-url', 'origin') if own_git else saved.get('source_url', ''))
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Quellrevision fehlt oder ist ungültig.')
    url = urlsplit(remote)
    if url.scheme != 'https' or not url.hostname or not url.path.strip('/'):
        raise ValueError('Quelladresse muss eine HTTPS-Repository-URL sein.')
    # Authentication stays in Git's credential store, never in install metadata.
    source_url = urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], url.path.rstrip('/'), '', ''))
    url.port
    if not url.path.rstrip('/').endswith('.git') or any(c.isspace() for c in remote):
        raise ValueError('Quelladresse muss eine HTTPS-Repository-URL mit .git sein.')
    epoch = os.environ.get('SOURCE_DATE_EPOCH') or (git('show', '-s', '--format=%ct', 'HEAD') if own_git else saved.get('source_date_epoch'))
    if not str(epoch).isdigit(): raise ValueError('Reproduzierbares Quelldatum fehlt.')
    return dict(revision=revision, source_url=source_url, source_date_epoch=int(epoch))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    parser.add_argument('--kind', choices=('user', 'system', 'source'), default='source')
    args = parser.parse_args()
    try:
        print(json.dumps(dict(identity(args.repo), kind=args.kind), sort_keys=True))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')
