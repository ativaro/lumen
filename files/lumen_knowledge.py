"""Explicit-root local knowledge search, reusing Lumen's bounded text/PDF reader."""
from lumen_i18n import tr
import os
from pathlib import Path
import time

from content_search import folder_fd, read_content, query_groups

EXCLUDED = {'node_modules', 'vendor', '__pycache__', 'credentials', 'secrets', 'id_rsa', 'id_ed25519', 'passwords', 'password', 'tokens', 'apikey', 'api_key', 'private_key', 'secret'}
SUFFIXES = {'.txt', '.md', '.rst', '.pdf', '.csv', '.py', '.js', '.ts', '.html', '.odt.txt', '.log'}


def index_root(store, directory, cancelled=lambda: False, pause=lambda: None):
    root = Path(directory).expanduser().resolve(strict=True)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    queue = [Path('.')]; documents = []; count = size = errors = 0
    try:
        while queue and count < 10000 and size < 32 * 1024 * 1024:
            pause()
            if cancelled(): raise InterruptedError(tr('Indexierung abgebrochen; bisheriger Index bleibt erhalten.'))
            relative = queue.pop(); parent = folder_fd(root_fd, relative)
            try:
                with os.scandir(parent) as entries:
                    for entry in entries:
                        if cancelled(): raise InterruptedError(tr('Indexierung abgebrochen.'))
                        count += 1
                        if count % 20 == 0: pause()
                        if count > 10000 or size >= 32 * 1024 * 1024: break
                        if entry.name.startswith('.') or (entry.name.lower() in EXCLUDED or Path(entry.name.lower()).stem in EXCLUDED) or entry.is_symlink(): continue
                        if entry.is_dir(follow_symlinks=False): queue.append(relative / entry.name); continue
                        path = root / relative / entry.name
                        if path.suffix.lower() not in SUFFIXES or not entry.is_file(follow_symlinks=False): continue
                        try:
                            before = entry.stat(follow_symlinks=False)
                            text, partial = read_content(path, parent)
                            if not text: continue
                            size += len(text.encode('utf-8'))
                            stamp = f'{before.st_mtime_ns}:{before.st_size}'
                            for page, content in enumerate(text.split('\f'), 1):
                                if content.strip(): documents.append((str(root), str(path), page, stamp, content))
                        except (OSError, ValueError): errors += 1
            finally: os.close(parent)
        with store.connect() as db:
            db.execute('DELETE FROM documents WHERE root=?', (str(root),))
            db.executemany('INSERT INTO documents VALUES (?,?,?,?,?)', documents)
            db.execute('INSERT OR REPLACE INTO roots VALUES (?,?)', (str(root), time.time()))
        return {'documents': len({d[1] for d in documents}), 'pages': len(documents), 'errors': errors,
                'limited': bool(queue) or count >= 10000 or size >= 32 * 1024 * 1024}
    finally: os.close(root_fd)


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
