"""Token-free navigation metadata, never an app session or an access grant.

New Server objects use explicit version 2 refs; existing Drive refs stay unchanged.
Consumers must obtain a current authorized app session before using a route.
"""
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import drive_references as drive
from lumen_i18n import tr

ROUTES = {'note':'note', 'projects':'project', 'code':'entry', 'media':'record','inbox':'mail','photos':'photo'}


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError(tr('Ungültige Server-Kennung.')) from None
    return value


def _binding(value):
    if not isinstance(value, dict) or set(value) != {'server', 'account'}:
        raise ValueError(tr('Ungültige Server-Herkunft.'))
    server = value['server']
    if (not isinstance(server, str) or len(server) > 4096
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c in '\\%' for c in server)):
        raise ValueError(tr('Ungültige Server-Herkunft.'))
    try:
        url = urlsplit(server)
        valid = (url.scheme == 'https' and url.geturl() == server and url.hostname
                 and not url.netloc.endswith(':') and url.username is None
                 and url.password is None and not url.path and not url.query
                 and not url.fragment and (url.port is None or 0 < url.port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(tr('Ungültige Server-Herkunft.'))
    return dict(server=server, account=_uuid(value['account']))


def validate_ref(ref):
    if isinstance(ref, dict) and ref.get('app') == 'files':
        result = drive.validate(ref)
        result['locator'] = _binding(result['locator'])
        return result
    if (not isinstance(ref, dict) or set(ref) - {'version','app','id','title','locator','item_id'}
            or not {'version','app','id','title','locator'} <= set(ref)
            or type(ref['version']) is not int or ref['version'] != 2
            or not isinstance(ref['app'], str) or ref['app'] not in ROUTES):
        raise ValueError(tr('Ungültiger Serververweis.'))
    if not isinstance(ref['title'], str) or not ref['title'] or len(ref['title']) > 4096 or '\0' in ref['title']:
        raise ValueError(tr('Ungültiger Server-Name.'))
    if 'item_id' in ref:
        if ref['app'] not in ('projects','inbox'):raise ValueError(tr('Ungültiger Serververweis.'))
        _uuid(ref['item_id'])
    return dict(ref, id=_uuid(ref['id']), locator=_binding(ref['locator']))


def identity(ref):
    ref = validate_ref(ref)
    result = (ref['locator']['server'], ref['locator']['account'], ref['app'],
              ref.get('kind'), ref['id'])
    return result + (ref['item_id'],) if 'item_id' in ref else result


def _target(ref, binding, query, source, return_to):
    binding = _binding(binding)
    ref = validate_ref(ref)
    source = validate_ref(ref if source is None else source)
    return_to = validate_ref(source if return_to is None else return_to)
    if any(item['locator'] != binding for item in (ref, source, return_to)):
        raise ValueError(tr('Dieser Verweis gehört zu einem anderen Server oder Konto.'))
    return dict(action='open', reference=ref, route='/?' + urlencode(query),
                source=source, return_to=return_to)


def navigation(ref, binding, *, source=None, return_to=None):
    """Describe an existing object; binding comes from the caller's current session.

    The host owns presentation mode and authorization. No URL is opened here.
    """
    ref = validate_ref(ref)
    if ref['app'] == 'files':
        raise ValueError(tr('Drive-Verweise zuerst online auflösen.'))
    query = {'app':ref['app'], ROUTES[ref['app']]:ref['id']}
    if 'item_id' in ref:
        if ref['app']=='inbox':query={'app':'inbox','calendar':ref['id'],'event':ref['item_id']}
        else:query['project_task'] = ref['item_id']
    return _target(ref, binding, query, source, return_to)


def clicked_reference(value, binding):
    """A same-server object link is navigation metadata, never renderer authority."""
    from server_app_session import APPS, APP_NAMES
    try:
        if (not isinstance(value,str) or len(value)>8192
                or any(ord(c)<32 or ord(c)==127 or c=='\\' for c in value)):
            return None
        url=urlsplit(value)
        if (url.scheme+'://'+url.netloc != binding.origin or url.path!='/'
                or url.fragment not in ('','main-content')):
            return None
        query=parse_qs(url.query,keep_blank_values=True,strict_parsing=True)
        app=query.get('app',[])
        if len(app)!=1:return None
        app='note' if app[0]=='notes' else app[0]
        if app=='files' and set(query)=={'app','family'} and len(query['family'])==1:
            return validate_ref(dict(app='files',kind='drive_file',id=query['family'][0],title='Lumen Drive',
                locator=dict(server=binding.origin,account=binding.account)))
        kind=next((key for key,item in APPS.items() if item[0]==app),None)
        if app not in ROUTES or kind not in APP_NAMES:return None
        calendar=app=='inbox' and 'calendar' in query
        key='calendar' if calendar else ROUTES[app]
        allowed={'app',key,'presentation'} | ({'project_task'} if app=='projects' else {'event'} if calendar else set())
        if (set(query)-allowed or len(query.get(key,[]))!=1
                or query.get('presentation',['desktop'])!=['desktop']):
            return None
        ref=dict(version=2,app=app,id=query[key][0],title=APP_NAMES[kind][0],
                 locator=dict(server=binding.origin,account=binding.account))
        if calendar:
            if len(query.get('event',[]))!=1:return None
            ref['item_id']=query['event'][0]
        if 'project_task' in query:
            if len(query['project_task'])!=1:return None
            ref['item_id']=query['project_task'][0]
        return validate_ref(ref)
    except (ValueError,TypeError,AttributeError):
        return None


def drive_navigation(ref, job=None):
    """Resolve the existing Drive family online, retaining it as source/return path.

    Files/Reader app sessions are not provided by this adapter. A consumer must
    fail closed until its host supports the corresponding authorized session.
    """
    ref = validate_ref(ref)
    if ref['app'] != 'files' or ref['kind'] != 'drive_file':
        raise ValueError(tr('Für diesen Eintrag gibt es keinen Server-Dateilink.'))
    config, rows = drive.resolve([ref], job)
    row = rows[0]
    if (row.get('family') != ref['id'] or row.get('trashed') is not False
            or any(type(row.get(key)) is not int or row[key] < 1 for key in ('version','revision'))):
        raise ValueError(tr('Die aufgelöste Drive-Version passt nicht zum Verweis.'))
    resolved = dict(id=_uuid(row.get('id')), version=row['version'], revision=row['revision'])
    # Navigation takes a version ID; persistent Drive identity remains the family.
    result = _target(ref, dict(server=config['server'], account=ref['locator']['account']),
                     {'app':'files', 'file':resolved['id']}, None, None)
    return dict(result, resolved=resolved)
