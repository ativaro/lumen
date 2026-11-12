"""Cross-app neighbors for the native notebook graph and its keyboard list."""
import re
from interop_data import Registry


def app_title(app):
    from interop_ui import app_name
    return app_name(app)


def neighbors(book, note, root=None, area='user'):
    registry = Registry(root)
    source = registry.register(dict(app='wissen', kind='note', id=note['path'], title=note['title'], path=str(book.root/note['path']), locator=dict(root=str(book.root), area=area)))
    rows = registry.related(source); seen = {row['url'] for row in rows}
    for url in re.findall(r'lumen://object/[a-f0-9]{32}(?:\?[^\s\)\]>\"\']+)?', note.get('text', '')+'\n'+note.get('source', ''))[:100]:
        if url in seen: continue
        try: rows.append(dict(registry.resolve(url), url=url, direction='out')); seen.add(url)
        except ValueError: continue
    return [dict(row, app_title=app_title(row['app'])) for row in rows if row['app'] != 'wissen' or row.get('locator', {}).get('root') != str(book.root)][:36]
