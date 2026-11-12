"""Explicit-root local knowledge search, reusing Lumen's bounded text, PDF and Office reader."""
from lumen_i18n import tr
from pathlib import Path
import time

from content_search import OFFICE, query_groups

EXCLUDED = {'node_modules', 'vendor', '__pycache__', 'credentials', 'secrets', 'id_rsa', 'id_ed25519', 'passwords', 'password', 'tokens', 'apikey', 'api_key', 'private_key', 'secret'}
SUFFIXES = {'.txt', '.md', '.rst', '.pdf', '.csv', '.py', '.js', '.ts', '.html', '.odt.txt', '.log'} | OFFICE


def index_root(store, directory, cancelled=lambda: False, pause=lambda: None):
    """The document core walks and reads the folder; the index keeps one row per page."""
    import json, subprocess
    from lumen_office import PDFError, program
    root = Path(directory).expanduser().resolve(strict=True)
    try: command = [program(), 'index']
    except PDFError as error: raise ValueError(str(error)) from error
    request = dict(root=str(root), excluded=sorted(EXCLUDED), suffixes=sorted(SUFFIXES), max_entries=10000, max_bytes=32 * 1024 * 1024,
                   messages={text: tr(text) for text in ('Office-Datei zu groß.', 'Office-Datei nicht lesbar.', 'PDF nicht lesbar.', 'Datei während der Suche verändert.')})
    documents = []; done = None
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        process.stdin.write(json.dumps(request).encode()); process.stdin.close()
        for line in process.stdout:
            pause()
            if cancelled(): raise InterruptedError(tr('Indexierung abgebrochen; bisheriger Index bleibt erhalten.'))
            event = json.loads(line)
            if event['type'] == 'error': raise OSError(event['message'])
            if event['type'] == 'done': done = event; break
            for page, content in enumerate(event['text'].split('\f'), 1):
                if content.strip(): documents.append((str(root), event['path'], page, event['stamp'], content))
    finally:
        if process.poll() is None: process.kill()
        process.wait(); process.stdout.close()
    if done is None: raise OSError(tr('Indexierung abgebrochen.'))
    with store.connect() as db:
        db.execute('DELETE FROM documents WHERE root=?', (str(root),))
        db.executemany('INSERT INTO documents VALUES (?,?,?,?,?)', documents)
        db.execute('INSERT OR REPLACE INTO roots VALUES (?,?)', (str(root), time.time()))
    return {'documents': len({d[1] for d in documents}), 'pages': len(documents), 'errors': done['errors'], 'limited': done['limited']}


def search(store, query, limit=30):
    groups = query_groups(query)
    if not groups: return []
    expression = ' AND '.join('(' + ' OR '.join('"' + word.replace('"', '""') + '"*' for word in group) + ')' for group in groups)
    rows = store.rows("SELECT root,path,page,stamp,snippet(documents,4,'','',' … ',40) AS snippet FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT ?", (expression, min(100, max(1, limit))))
    result = []
    for row in rows:
        path = Path(row['path']); root = Path(row['root'])
        try:
            info = path.stat()
            if (path.resolve() != path or not path.is_relative_to(root) or not path.is_file()
                    or f'{info.st_mtime_ns}:{info.st_size}' != row['stamp']): continue
            result.append(row)
        except OSError: pass
    return result
