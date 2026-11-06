"""Concrete local household workflows built on reviewed Lumen transfers."""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re

from lumen_i18n import tr
from interop_data import Registry, validate_payload


def _payload(library, record, title, text, paths=(), items=()):
    source = dict(app=library.root.name, kind='record', id=record['id'], title=record['title'])
    registry = Registry(library.root.parent)
    return validate_payload(dict(title=title, text=text, paths=list(paths), items=list(items), source=source, source_url=registry.register(source)))


def invoice_candidates(text):
    """Extract labeled candidates only; the native review dialog commits them."""
    result = {}
    for field, labels in [('provider', r'Händler|Verkäufer|Anbieter|Hersteller'), ('model', r'Modell|Vertragsnummer'), ('serial', r'Seriennummer|Kundennummer')]:
        found = re.search(r'(?im)^\s*(?:'+labels+r')\s*:\s*(.{1,200})$', text)
        if found: result[field] = found[1].strip()
    found = re.search(r'(?im)^\s*(?:Rechnungsdatum|Kaufdatum|Belegdatum|Datum)\s*:\s*(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b', text)
    if found:
        try:
            result['since'] = (date.fromisoformat(found[1]) if '-' in found[1] else datetime.strptime(found[1], '%d.%m.%Y').date()).isoformat()
        except ValueError: pass
    return result


def _device_details(record):
    labels = [('provider', tr('Hersteller / Anbieter')), ('model', tr('Modell / Vertragsnummer')), ('serial', tr('Seriennummer / Kundennummer')), ('since', tr('Kauf / Beginn'))]
    return '\n'.join(label+': '+str(record[field]) for field, label in labels if record.get(field))


def household_payload(library, key, workflow, text='', paths=()):
    record = library.get(key); details = _device_details(record)
    if workflow == 'cancel':
        title = tr('Kündigung · ')+record['title']
        body = tr('Guten Tag,\n\nhiermit kündige ich den folgenden Vertrag zum nächstmöglichen Zeitpunkt. Bitte bestätigen Sie mir die Kündigung und das Vertragsende schriftlich.\n\n')+record['title']+'\n'+details
    elif workflow == 'support':
        title = tr('Supportanfrage · ')+record['title']
        body = tr('Guten Tag,\n\nich bitte um Unterstützung zu folgendem Gerät oder Vertrag:\n\n')+record['title']+'\n'+details+'\n\n'+(text or record.get('notes', ''))
    elif workflow == 'repair':
        title = tr('Reparatur · ')+record['title']; body = details+'\n\n'+(text or record.get('notes', ''))
    elif workflow == 'handover':
        title = tr('Übergabe · ')+record['title']; body = details+'\n\n'+(text or record.get('notes', ''))
    else: raise ValueError(tr('Unbekannter Haushaltsablauf.'))
    names = {str(library.asset(a['asset'])): a['name'] for a in record.get('attachments', [])}
    items = [dict(kind='attachment', path=str(path), title=names.get(str(path), Path(path).name)) for path in paths]
    return _payload(library, record, title, body.strip(), paths, items)


def _event(title, due, text):
    start = datetime.combine(date.fromisoformat(due), datetime.min.time()).replace(hour=9).astimezone()
    return dict(kind='event', title=title, start=start.isoformat(), end=(start+timedelta(hours=1)).isoformat(), location='', description=text)


def deadline_payload(library, key, field='remind'):
    if field not in ('remind', 'until'): raise ValueError(tr('Unbekannte Haushaltsfrist.'))
    record = library.get(key); due = record.get(field, '')
    if not due: raise ValueError(tr('Diese Frist zuerst im Haushalt eintragen.'))
    title = (tr('Kündigungsfrist · ') if field == 'remind' else tr('Garantie / Vertragsende · '))+record['title']
    marker = '[Lumen-Frist:'+key+':'+field+']'
    text = _device_details(record)+'\n\n'+record.get('notes', '')+'\n\n'+marker
    event = _event(title, due, text); event['link_key'] = 'household:'+key+':'+field
    return _payload(library, record, title, text.strip(), items=[event])


def prepare_event_update(library, values, event):
    """Find a previous deadline in the chosen account, never trust supplied remote URLs."""
    result = dict(values); link = event.get('link_key', '')
    if not link: return result
    match = re.fullmatch(r'household:([a-f0-9]{32}):(remind|until)', link)
    if not match: raise ValueError(tr('Ungültige Fristverknüpfung.'))
    marker = '[Lumen-Frist:'+match[1]+':'+match[2]+']'
    def matches(value): return marker in value.get('description', '').splitlines()
    if not matches(result): raise ValueError(tr('Dem Terminvorschlag fehlt seine Fristverknüpfung.'))
    with library.connect() as db:
        records = [json.loads(row['data']) for row in db.execute('SELECT data FROM calendar_cache WHERE account=?', (values['account'],))]
        found = [record for record in records if matches(record)]
        if len(found) > 1: raise ValueError(tr('Mehrere Termine tragen diese Frist. In Lumen Inbox zuerst den richtigen Termin auswählen.'))
        if found:
            existing = found[0]
            if existing.get('recurring') or existing.get('invited'): raise ValueError(tr('Serien oder Einladungen im ursprünglichen Kalender bearbeiten.'))
            if not all(existing.get(key) for key in ('uid', 'url', 'etag', 'ics')): raise ValueError(tr('Den Kalender zuerst aktualisieren, damit die Frist geschützt geändert werden kann.'))
            result.update({key: existing[key] for key in ('uid', 'url', 'etag', 'ics')}); return result
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='interop_event_proposals'").fetchone()
        pending = []
        if exists:
            for row in db.execute('SELECT * FROM interop_event_proposals'):
                proposal = json.loads(row['data'])
                if proposal.get('account') == values['account'] and matches(proposal): pending.append(row['id'])
        if len(pending) > 1: raise ValueError(tr('Mehrere lokale Vorschläge tragen diese Frist. In Lumen Inbox zuerst prüfen.'))
        if pending: result['proposal_id'] = pending[0]
    return result
