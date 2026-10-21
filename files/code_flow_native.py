"""The former native Code workflow engine is retired; ordinary tasks stay native."""
from lumen_i18n import tr

MESSAGE='Lumen Code und Automationen werden auf dem verbundenen Lumen Server ausgeführt. Bitte Lumen Code öffnen.'


def unavailable():
    raise ValueError(tr(MESSAGE))


def owns_workflow(db,flow):
    if flow['code_plan'] or flow['trigger']=='schedule':return True
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='code_library'").fetchone():return False
    return bool(db.execute("SELECT 1 FROM code_library WHERE kind='automation' AND json_valid(definition) "
        "AND json_extract(definition,'$.workflow_id')=? LIMIT 1",(flow['id'],)).fetchone())


def check_task(db,task):
    if db.execute("SELECT 1 FROM events WHERE task=? AND kind IN ('code-flow','code-library') LIMIT 1",(task,)).fetchone():
        unavailable()
