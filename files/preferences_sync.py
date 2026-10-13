"""Opt-in language/theme replication, with CAS and visible concurrent edits."""
import time
import lumen_connect as connector
from sync_identity import scope


def local():
    from lumen_qt import QSettings
    from lumen_i18n import saved_language, system_language
    from appearance_tokens import normalize_design
    language = saved_language()
    return dict(language=language if language in ('de','en') else system_language(),
                appearance=normalize_design(QSettings('Lumen','Assistant').value('appearance','glass')))


def validate(profile):
    if not isinstance(profile,dict) or set(profile) != {'language','appearance'}: raise ValueError('Invalid preferences')
    if profile['language'] not in ('de','en') or profile['appearance'] not in ('glass','graphite','atelier','midnight','clear','system'): raise ValueError('Invalid preferences')
    return profile


def apply(profile):
    from lumen_qt import QSettings
    validate(profile)
    settings=QSettings('Lumen','Assistant')
    settings.setValue('uiLanguage',profile['language'])
    settings.setValue('appearance',profile['appearance'])
    settings.sync()
    if settings.status() != QSettings.NoError: raise OSError('Preferences could not be saved')


def _configure(store,enabled):
    state=store.setting('sync/preferences',{})
    if not enabled:
        state['enabled']=False;store.set_setting('sync/preferences',state);return
    from sync_settings import prepare_connection
    config=prepare_connection()
    remote=connector.request(config,'/bridge/sync-preferences')
    validate(remote['profile'])
    current=local()
    if not remote['enabled']:
        remote=connector.request(config,'/bridge/sync-preferences',dict(enabled=True,revision=remote['revision'],profile=current))
    # Choosing sync adopts the account profile; preserve the previous local choice.
    state=dict(enabled=True,scope=scope(config,['preferences'],''),base=remote['profile'],previous=current)
    apply(remote['profile'])
    state['last_sync']=time.time();store.set_setting('sync/preferences',state)


def _synchronize(store):
    state=store.setting('sync/preferences',{})
    if not state.get('enabled'):return dict(enabled=False)
    config=connector.read_config()
    if state['scope']!=scope(config,['preferences'],''):raise ValueError('Preferences account changed')
    remote=connector.request(config,'/bridge/sync-preferences')
    validate(remote['profile'])
    if not remote['enabled']:
        state['reason']='server_paused';store.set_setting('sync/preferences',state)
        return dict(enabled=True,paused=True)
    before=local();base=state['base'];merged={};conflicts=[]
    for field in ('language','appearance'):
        left,right=before[field],remote['profile'][field]
        if left!=base[field] and right!=base[field] and left!=right:conflicts.append(field)
        merged[field]=left if left!=base[field] else right
    if conflicts:
        state['conflicts']=conflicts;store.set_setting('sync/preferences',state)
        return dict(conflicts=conflicts)
    if merged!=remote['profile']:
        connector.request(config,'/bridge/sync-preferences',dict(enabled=True,revision=remote['revision'],profile=merged))
    # A user edit made while the request was in flight is retained for the next pass.
    if local()!=before:return dict(enabled=True)
    apply(merged)
    state.update(base=merged,last_sync=time.time(),conflicts=[],reason="ready")
    store.set_setting('sync/preferences',state)
    return dict(enabled=True)


def locked(store, action, *args):
    import fcntl
    with (store.directory/'preferences-sync.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return action(store,*args)


def configure(store, enabled): return locked(store, _configure, enabled)


def synchronize(store): return locked(store, _synchronize)
