"""Legacy replica settings cannot restart local project writers."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import projects_sync
import sync_settings
import lumen_connect
from tools_data import Library

class RetirementTest(unittest.TestCase):
    def test_direct_replica_entrypoints_fail_before_network_or_library_writes(self):
        with tempfile.TemporaryDirectory() as root:
            library=Library('workbench',root);key=library.create('Original',notes='Keep');before=library.get(key)
            state=library.root/'server-sync.json';state.write_text('{"enabled":true,"old":"keep"}');previous=state.read_bytes()
            with patch.object(lumen_connect,'request',side_effect=AssertionError('retired network')):
                for fn,args in ((projects_sync.configure,(library,True)),(projects_sync.synchronize,(library,)),(projects_sync.resolve,(library,'old',True))):
                    with self.assertRaisesRegex(ValueError,'Lumen Server'):fn(*args)
            self.assertEqual(library.get(key),before);self.assertEqual(state.read_bytes(),previous)

    def test_connector_has_no_replica_launcher(self):
        self.assertFalse(hasattr(lumen_connect,'sync_projects'))
        self.assertFalse(hasattr(sync_settings,'project_library'))

    def test_technical_server_project_catalog_remains_paged_and_account_scoped(self):
        cfg={'server':'https://example.invalid','token':'synthetic'}
        with patch.object(lumen_connect,'request',side_effect=[dict(items=[dict(id='one')],next_offset=1),dict(items=[dict(id='two')],next_offset=None)]) as call:
            self.assertEqual(projects_sync.available(cfg),[dict(id='one'),dict(id='two')])
            self.assertEqual(call.call_args.args,(cfg,'/bridge/projects?offset=1'))
