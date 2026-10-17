"""Calendar starts for local routines, in the explicitly displayed Zurich zone."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Zurich')
KINDS = ('manual', 'once', 'daily', 'weekly', 'monthly', 'interval')


def validate(clock):
    keys = {'kind', 'time', 'date', 'days', 'month_day', 'minutes'}
    if not isinstance(clock, dict) or set(clock) != keys or clock['kind'] not in KINDS:
        raise ValueError('Ungültiger Zeitplan.')
    try:
        if len(clock['time']) != 5 or time.fromisoformat(clock['time']).second:
            raise ValueError()
        if date.fromisoformat(clock['date']).isoformat()!=clock['date']:raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Datum und Uhrzeit prüfen.') from None
    if not isinstance(clock['days'], list) or any(type(d) is not int or not 0 <= d <= 6 for d in clock['days']):
        raise ValueError('Ungültige Wochentage.')
    if clock['kind'] == 'weekly' and not clock['days']:
        raise ValueError('Mindestens einen Wochentag wählen.')
    if type(clock['month_day']) is not int or not 1 <= clock['month_day'] <= 31:
        raise ValueError('Tag im Monat: 1 bis 31.')
    if type(clock['minutes']) is not int or not 15 <= clock['minutes'] <= 525600:
        raise ValueError('Intervall: 15 Minuten bis ein Jahr.')
    return clock


def wall(day, at):
    local = datetime.combine(day, time.fromisoformat(at))
    candidates = []
    for fold in (0, 1):
        value = local.replace(tzinfo=ZONE, fold=fold)
        if value.astimezone(timezone.utc).astimezone(ZONE).replace(tzinfo=None) == local:
            candidates.append(value.timestamp())
    return min(candidates) if candidates else None


def starts(clock, now=None, count=3):
    validate(clock)
    now = datetime.now().timestamp() if now is None else now
    kind = clock['kind']
    if kind == 'manual':
        return []
    if kind == 'interval':
        return [now + clock['minutes'] * 60 * (i + 1) for i in range(count)]
    if kind == 'once':
        value = wall(date.fromisoformat(clock['date']), clock['time'])
        return [value] if value is not None and value > now else []
    today = datetime.fromtimestamp(now, ZONE).date()
    result = []
    for offset in range(370):
        day = today + timedelta(days=offset)
        if kind == 'weekly' and day.weekday() not in clock['days']:
            continue
        if kind == 'monthly' and day.day != clock['month_day']:
            continue
        value = wall(day, clock['time'])
        if value is not None and value > now:
            result.append(value)
            if len(result) == count:
                break
    return result


def default():
    return dict(kind='weekly', time='08:00', date=date.today().isoformat(), days=[0], month_day=1, minutes=60)


def describe(clock):
    from lumen_i18n import tr
    validate(clock)
    at = clock['time']
    kind = clock['kind']
    if kind == 'manual': return tr('Manuell starten')
    if kind == 'once': return tr('Einmalig am {0} um {1}', clock['date'], at)
    if kind == 'daily': return tr('Täglich um {0}', at)
    if kind == 'weekly':
        days = [tr(day) for day in ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')]
        return tr('{0} um {1}', ', '.join(days[d] for d in sorted(set(clock['days']))), at)
    if kind == 'monthly': return tr('Monatlich am {0}. um {1}', clock['month_day'], at)
    return tr('Alle {0} Minuten ab Aktivierung', clock['minutes'])
