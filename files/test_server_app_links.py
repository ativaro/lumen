import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import drive_references as drive
import server_app_links as links


class ServerAppLinksTest(unittest.TestCase):
    def setUp(self):
        self.binding = dict(server='https://staging.invalid', account=str(uuid4()))
        self.ref = dict(version=2, app='projects', id=str(uuid4()), title='Haus',
                        locator=dict(self.binding))
        self.drive = dict(app='files', kind='drive_file', id=str(uuid4()),
                          title='Original.pdf', locator=dict(self.binding))
        self.row = dict(id=str(uuid4()), family=self.drive['id'], version=3,
                        revision=8, name='Renamed.pdf', trashed=False)
        self.config = dict(server=self.binding['server'], token='device-secret')

    def test_versioned_refs_keep_existing_ids_and_distinguish_every_boundary(self):
        for app in ('note', 'projects', 'code'):
            ref = dict(self.ref, app=app)
            self.assertEqual(links.validate_ref(ref), ref)
            self.assertEqual(links.identity(ref), links.identity(dict(ref, title='Renamed')))
            for changed in (dict(ref, id=str(uuid4())), dict(ref, app='code' if app != 'code' else 'note'),
                            dict(ref, locator=dict(self.binding, account=str(uuid4()))),
                            dict(ref, locator=dict(self.binding, server='https://other.invalid'))):
                self.assertNotEqual(links.identity(ref), links.identity(changed))

    def test_project_task_reference_keeps_its_project_and_exact_task(self):
        ref = dict(self.ref, item_id=str(uuid4()))
        target = links.navigation(ref, self.binding)
        self.assertEqual(parse_qs(urlsplit(target['route']).query),
                         {'app':['projects'], 'project':[ref['id']], 'project_task':[ref['item_id']]})
        self.assertNotEqual(links.identity(ref), links.identity(self.ref))
        self.assertEqual(links.validate_ref(ref), ref)
        from interop_data import Registry
        with tempfile.TemporaryDirectory() as root:
            registry=Registry(root)
            first=registry.register(ref)
            other=dict(ref,item_id=str(uuid4()))
            second=registry.register(other)
            self.assertNotEqual(first,second)
            self.assertEqual(registry.resolve(first),ref)
            self.assertEqual(registry.resolve(second),other)
        for wrong in (dict(ref, app='note'), dict(ref, item_id='../task'), dict(ref, item_id=None)):
            with self.subTest(ref=wrong), self.assertRaises(ValueError):
                links.validate_ref(wrong)

    def test_clicked_server_links_use_only_the_current_account_and_known_objects(self):
        from server_app_session import Binding
        source = Binding(self.binding['server'], self.binding['account'], str(uuid4()), 'code')
        for app, key, expected in (('notes','note','note'), ('projects','project','projects'),
                                   ('code','entry','code'), ('media','record','media'),('inbox','mail','inbox')):
            with self.subTest(app=app):
                url=source.origin+'/?app='+app+'&'+key+'='+self.ref['id']
                ref=links.clicked_reference(url,source)
                self.assertEqual(ref['app'],expected)
                self.assertEqual(ref['id'],self.ref['id'])
                self.assertEqual(ref['locator'],self.binding)
        task=str(uuid4())
        url=source.origin+'/?app=projects&project='+self.ref['id']+'&project_task='+task
        self.assertEqual(links.clicked_reference(url,source)['item_id'],task)
        for wrong in (url.replace(source.origin,'https://other.invalid'), url+'&token=secret',
                      url+'&app=projects', url+'&project_task='+task, url+'#secret',
                      url.replace(task,'../task'), url.replace('project_task=','device='),
                      source.origin+'/?app=vault', source.origin+'/?app=note&note='+task+'&presentation=web',
                      'file:///etc/passwd', 'javascript:alert(1)', '//other.invalid/?app=note',
                      source.origin+'/?app=notes&note='+task+'&project_task='+task):
            with self.subTest(url=wrong):
                self.assertIsNone(links.clicked_reference(wrong,source))
        self.assertEqual(links.validate_ref(self.drive), self.drive)
        self.assertNotEqual(links.identity(self.drive), links.identity(dict(self.drive, kind='drive_folder')))

    def test_inbox_mail_and_calendar_event_references_are_exact_and_account_bound(self):
        from server_app_session import Binding
        binding=Binding(self.binding['server'],self.binding['account'],str(uuid4()),'inbox')
        for item in (None,str(uuid4())):
            ref=dict(self.ref,app='inbox')
            if item:ref['item_id']=item
            url=binding.reference_url(ref)
            self.assertTrue(binding.navigation(url))
            self.assertEqual(links.clicked_reference(url,binding),dict(ref,title='Lumen Inbox'))
            self.assertIn(('calendar=' if item else 'mail=')+ref['id'],url)
            for wrong in (url+'&mail='+ref['id'],url+'&event=bad',url+'&project_task='+ref['id']):
                self.assertFalse(binding.navigation(wrong))
                self.assertIsNone(links.clicked_reference(wrong,binding))

    def test_legacy_refs_are_not_silently_reinterpreted(self):
        for ref in (dict(app='wissen', kind='note', id='note.md', title='Note', locator={'root':'/tmp/notes'}),
                    dict(app='workbench', kind='record', id=self.ref['id'], title='Project'),
                    {k:v for k,v in self.ref.items() if k != 'version'},
                    dict(self.ref, app='files'), dict(self.ref, version=1), dict(self.ref, version=True)):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                links.validate_ref(ref)

    def test_registered_server_objects_launch_the_existing_owning_receiver(self):
        from pathlib import Path
        from interop_data import Registry
        from interop_open import open_url
        with tempfile.TemporaryDirectory() as root:
            registry=Registry(root)
            for app,target in (('note','wissen'),('projects','workbench'),('code','code'),('media','meetings'),('inbox','inbox')):
                with self.subTest(app=app):
                    ref=dict(self.ref,app=app)
                    url=registry.register(ref)
                    with patch('interop_open.subprocess.Popen') as started:open_url(url,root)
                    command=started.call_args.args[0]
                    self.assertEqual(Path(command[1]).name,'tools_app.py')
                    self.assertEqual(command[2:],[target,'--ref',url])
                    self.assertEqual(registry.resolve(url),ref)
                    self.assertNotIn(self.config['token'],' '.join(command))

    def test_only_exact_token_free_schema_is_accepted(self):
        for ref in (None, [], dict(self.ref, token='secret'), dict(self.ref, path='/tmp/file'),
                    dict(self.ref, locator=dict(self.binding, token='secret')),
                    dict(self.ref, id='../file'), dict(self.ref, id=str(uuid4()).upper()),
                    dict(self.ref, title=''), dict(self.ref, title='a\0b'),
                    dict(self.ref, locator=dict(self.binding, account='../user')),
                    dict(self.ref, app=[])):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                links.validate_ref(ref)

    def test_origin_has_no_path_credentials_or_browser_ambiguous_authority(self):
        invalid = ('http://staging.invalid', 'https://user:secret@staging.invalid',
                   'https://@staging.invalid', 'https://staging.invalid/',
                   'https://staging.invalid?token=secret', 'https://staging.invalid#file',
                   'https://staging.invalid?', 'https://staging.invalid#',
                   'https://staging.invalid:',
                   'https://staging.invalid:bad', 'https://staging.invalid:0',
                   'https://staging.invalid:65536', 'https://staging.invalid\\evil',
                   'https://staging.invalid\n', 'https://stag ing.invalid')
        for origin in invalid:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                links.validate_ref(dict(self.ref, locator=dict(self.binding, server=origin)))
        valid = dict(self.ref, locator=dict(self.binding, server='https://[::1]:8443'))
        self.assertEqual(links.validate_ref(valid), valid)

    def test_navigation_uses_canonical_routes_with_no_identity_or_secret_in_query(self):
        for app, parameter in (('note','note'), ('projects','project'), ('code','entry')):
            ref = dict(self.ref, app=app)
            target = links.navigation(ref, self.binding)
            self.assertEqual(parse_qs(urlsplit(target['route']).query), {'app':[app], parameter:[ref['id']]})
            self.assertEqual(urlsplit(target['route']).path, '/')
            self.assertFalse(urlsplit(target['route']).netloc)
            self.assertEqual(target['action'], 'open')
            self.assertEqual(target['reference'], ref)
            self.assertEqual(target['source'], ref)
            self.assertEqual(target['return_to'], ref)
            for secret in (self.binding['server'], self.binding['account'], self.config['token']):
                self.assertNotIn(secret, target['route'])

    def test_current_binding_and_all_provenance_must_match(self):
        for binding in (dict(self.binding, account=str(uuid4())),
                        dict(self.binding, server='https://other.invalid'),
                        dict(self.binding, token='secret')):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                links.navigation(self.ref, binding)
        source = dict(self.drive)
        target = links.navigation(self.ref, self.binding, source=source, return_to=source)
        self.assertEqual(target['source'], source)
        self.assertEqual(target['return_to'], source)
        for field in ('source', 'return_to'):
            foreign = dict(source, locator=dict(self.binding, account=str(uuid4())))
            with self.assertRaises(ValueError):
                links.navigation(self.ref, self.binding, **{field:foreign})
        target['reference']['locator']['account'] = str(uuid4())
        target['source']['locator']['account'] = str(uuid4())
        self.assertEqual(self.ref['locator'], self.binding)
        self.assertEqual(source['locator'], self.binding)
        self.assertEqual(target['return_to'], source)

    def test_drive_uses_authorized_current_version_but_keeps_stable_family(self):
        cache = dict(files={self.drive['id']:self.row}, folders={})
        with patch.object(drive.lumen_connect, 'read_config', return_value=self.config), \
             patch.object(drive.lumen_connect, 'request', return_value={'id':self.binding['account']}), \
             patch.object(drive.sync, 'inventory', return_value=cache), \
             patch('drive_transport.download', side_effect=AssertionError('Opening must not download')):
            target = links.drive_navigation(self.drive)
            self.assertEqual(target['reference'], self.drive)
            self.assertEqual(target['resolved'], {k:self.row[k] for k in ('id','version','revision')})
            self.assertEqual(parse_qs(urlsplit(target['route']).query), {'app':['files'],'file':[self.row['id']]})
            self.assertNotEqual(self.row['id'], self.drive['id'])
            previous = links.identity(target['reference'])
            self.row.update(id=str(uuid4()), version=4, revision=9)
            next_target = links.drive_navigation(self.drive)
            self.assertEqual(links.identity(next_target['reference']), previous)
            self.assertNotEqual(next_target['route'], target['route'])
            self.assertNotIn(self.config['token'], json.dumps(next_target))

    def test_drive_reuses_live_origin_account_revocation_and_switch_checks(self):
        cache = dict(files={self.drive['id']:self.row}, folders={})
        with patch.object(drive.lumen_connect, 'read_config', return_value=self.config) as config, \
             patch.object(drive.lumen_connect, 'request', return_value={'id':self.binding['account']}) as request, \
             patch.object(drive.sync, 'inventory', return_value=cache) as inventory:
            config.return_value = dict(self.config, server='https://other.invalid')
            with self.assertRaises(ValueError): links.drive_navigation(self.drive)
            request.assert_not_called()
            config.return_value = self.config
            request.return_value = {'id':str(uuid4())}
            with self.assertRaises(ValueError): links.drive_navigation(self.drive)
            inventory.assert_not_called()
            request.return_value = {'id':self.binding['account']}
            inventory.return_value = dict(files={}, folders={})
            with self.assertRaises(ValueError): links.drive_navigation(self.drive)
            inventory.return_value = cache
            self.row['trashed'] = True
            with self.assertRaises(ValueError): links.drive_navigation(self.drive)
            self.row['trashed'] = False
            config.side_effect = [self.config, dict(self.config, token='new-token')]
            with self.assertRaises(ValueError): links.drive_navigation(self.drive)

    def test_unresolved_drive_and_folder_navigation_fail_before_any_network(self):
        with patch.object(drive, 'resolve') as resolve:
            with self.assertRaises(ValueError): links.navigation(self.drive, self.binding)
            with self.assertRaises(ValueError): links.drive_navigation(dict(self.drive, kind='drive_folder'))
            resolve.assert_not_called()

    def test_mismatched_resolved_family_or_invalid_version_cannot_become_a_route(self):
        invalid = (dict(self.row, family=str(uuid4())), dict(self.row, id='../file'),
                   dict(self.row, version=0), dict(self.row, revision=True))
        for row in invalid:
            with self.subTest(row=row), patch.object(drive, 'resolve', return_value=(self.config,[row])), self.assertRaises(ValueError):
                links.drive_navigation(self.drive)


if __name__ == '__main__':
    unittest.main()
