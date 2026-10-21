"""Local Inbox data and attachment checks retained for explicit backup/interop only.

Network mail delivery, calendar clients and credentials belong to Lumen Server.
"""
from pathlib import Path
from lumen_i18n import tr
from tools_data import Library

MAX_MAIL = 20*1024**2


def store(root=None):
    library=Library('inbox',root)
    with library.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS messages (
            account TEXT, folder TEXT, validity TEXT, uid TEXT, thread TEXT, subject TEXT,
            sender TEXT, sent TEXT, body TEXT, raw BLOB, unread INTEGER,
            PRIMARY KEY(account,folder,validity,uid));
            CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, account TEXT, data TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT, due TEXT, source TEXT, done INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS interop_task_details(task TEXT PRIMARY KEY,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calendar_cache(account TEXT, uid TEXT, data TEXT, PRIMARY KEY(account,uid));''')
    return library



def draft_attachments(library,attachments):
    if not isinstance(attachments,list) or len(attachments)>100:raise ValueError(tr('Ungültige Entwurfsanhänge.'))
    result=[];total=0
    for item in attachments:
        if not isinstance(item,dict) or not isinstance(item.get('asset'),str) or not isinstance(item.get('name'),str):raise ValueError(tr('Ungültiger Entwurfsanhang.'))
        path=library.asset(item['asset'])
        if path.is_symlink() or not path.is_file():raise ValueError(tr('Ein Entwurfsanhang fehlt.'))
        total+=path.stat().st_size
        if total>12*1024**2:raise ValueError(tr('Anhänge zusammen größer als 12 MiB.'))
        name=Path(item['name'].replace('\\','/')).name
        if not name or any(c in name for c in '\r\n\0'):raise ValueError(tr('Ungültiger Anhangname.'))
        result.append(dict(asset=item['asset'],name=name))
    return result
