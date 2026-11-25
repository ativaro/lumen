"""The former native Code workflow engine is retired; ordinary tasks stay native."""
from lumen_i18n import tr

MESSAGE='Lumen Code und Automationen werden auf dem verbundenen Lumen Server ausgeführt. Bitte Lumen Code öffnen.'


def unavailable():
    raise ValueError(tr(MESSAGE))


def check_task(db,task):
    if db.execute("SELECT 1 FROM events WHERE task=? AND kind IN ('code-flow','code-library') LIMIT 1",(task,)).fetchone():
        unavailable()
