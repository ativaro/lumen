"""Project MCP mutations and detached runner, all in a private synthetic library."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from lumen_mcp_tools import invoke, DEFINITIONS
from test_mcp import mcp
from tools_data import Library
from projects_data import Projects


class ProjectActionsTest(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(root)
        self.enterContext(patch.dict(os.environ, LUMEN_TOOLS_DATA=root, LUMEN_MCP_ACTIONS='1', LUMEN_MCP_PROJECT_ACTIONS='0'))

    def call(self, name, **args):
        mcp.validate_schema(args, DEFINITIONS[name]['schema'])
        return invoke(name, args)

    def create(self, kind, parent=None):
        args = dict(kind=kind, title='Test '+kind)
        if parent: args['parent']=parent['id']
        return self.call('lumen_project_create', **args)['item']

    def hierarchy(self, kind='analysis'):
        project=self.create('project'); owner=self.create('initiative',project)
        return project,owner,self.create(kind,owner)

    def test_create_update_conflicts_and_manual_status(self):
        project,owner,task=self.hierarchy('manual')
        result=self.call('lumen_project_update',id=task['id'],expected_updated=task['revision'],
                         changes=dict(title='新しい計画',notes='Notiz',status='done'))
        self.assertEqual(result['item']['title'],'新しい計画')
        self.assertEqual(result['item']['status'],'done')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.call('lumen_project_update',id=task['id'],expected_updated=task['revision'],changes=dict(notes='stale'))
        with self.assertRaises(ValueError): self.create('analysis',project)
        with self.assertRaises(ValueError): self.create('initiative',owner)
        result=self.call('lumen_project_update',id=project['id'],expected_updated=project['revision'],changes=dict(goal='Goal'))
        self.assertEqual(result['goal']['text'],'Goal')
        library=Library('workbench',self.root); library.archive(project['id'])
        with self.assertRaises(ValueError):self.create('initiative',project)
        with self.assertRaises(ValueError):self.create('analysis',owner)

    def test_dependency_cycles_running_and_privilege_boundaries(self):
        project,owner,task=self.hierarchy()
        other=self.create('manual',owner)
        self.call('lumen_project_update',id=task['id'],expected_updated=task['revision'],changes=dict(depends=[other['id']]))
        with self.assertRaises(ValueError):
            self.call('lumen_project_update',id=other['id'],expected_updated=other['revision'],changes=dict(depends=[task['id']]))
        fresh=self.call('lumen_project_read',id=task['id'])['item']
        with self.assertRaises(ValueError):
            self.call('lumen_project_update',id=fresh['id'],expected_updated=fresh['revision'],changes=dict(status='done'))
        for changes in ({'enabled':True},{'resources':[]},{'status':'running'},{'title':''}):
            with self.assertRaises(ValueError):
                self.call('lumen_project_update',id=fresh['id'],expected_updated=fresh['revision'],changes=changes)
        with patch.dict(os.environ,LUMEN_MCP_ACTIONS='0'):
            with self.assertRaisesRegex(ValueError,'disabled'): self.create('project')
        # Real worker rejects unmet dependencies before any engine or file reads.
        with self.assertRaisesRegex(ValueError,'vorausgesetzten'):
            self.call('lumen_project_start',task=fresh['id'],expected_updated=fresh['revision'])
        self.assertEqual(self.call('lumen_project_runs',task=fresh['id'])['items'],[])

    def test_native_update_rechecks_revision_inside_transaction(self):
        project,owner,task=self.hierarchy()
        library=Library('workbench',self.root); projects=Projects(library)
        library.update(project['id'],notes='native edit')
        with self.assertRaises(ValueError):library.update(project['id'],expected_updated=project['revision'],notes='stale')
        projects.update(task['id'],notes='native edit')
        with self.assertRaises(ValueError):projects.update(task['id'],expected_updated=task['revision'],notes='stale')
        fresh=self.call('lumen_project_read',id=task['id'])['item']
        run=projects.begin_run(task['id'],{},expected_updated=fresh['revision'])
        running=self.call('lumen_project_read',id=task['id'])['item']
        with self.assertRaisesRegex(ValueError,'running'):
            projects.update(task['id'],expected_updated=running['revision'],notes='change during run')
        projects.finish_run(run,'cancelled')

    def test_detached_start_returns_real_run_and_failure_is_persisted(self):
        project,owner,task=self.hierarchy()
        library=Library('workbench',self.root)
        # Native attachment: missing source must fail without ever contacting an LLM.
        library.update(project['id'],resources=[dict(title='Missing',kind='file',target=str(self.root/'missing.txt'))])
        result=self.call('lumen_project_start',task=task['id'],expected_updated=task['revision'])
        self.assertEqual(result['task'],task['id']); self.assertEqual(result['status'],'running')
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            run=self.call('lumen_project_runs',task=task['id'],run=result['run'])
            if run['status']!='running':break
            time.sleep(.03)
        self.assertEqual(run['status'],'failed'); self.assertTrue(run['error'])
        with self.assertRaisesRegex(ValueError,'changed'):
            self.call('lumen_project_start',task=task['id'],expected_updated=task['revision'])
        self.assertEqual(len(self.call('lumen_project_runs',task=task['id'])['items']),1)

    def test_project_only_permission_reaches_worker_without_system_writes(self):
        with patch.dict(os.environ,LUMEN_MCP_ACTIONS='0',LUMEN_MCP_PROJECT_ACTIONS='1'):
            result=mcp.tool_native('lumen_project_create',dict(kind='project',title='Worker project'))
            self.assertEqual(result['item']['title'],'Worker project')
            with self.assertRaisesRegex(ValueError,'disabled'):
                mcp.tool_native('lumen_settings_set',{})

    def test_stdio_discovery_is_gated_and_skill_is_installed(self):
        script=Path(mcp.__file__)
        for enabled, project_only in (('0','0'),('1','0'),('0','1')):
            result=subprocess.run([sys.executable,str(script)],input=json.dumps(dict(jsonrpc='2.0',id=1,method='tools/list'))+'\n',
                env=dict(os.environ,LUMEN_MCP_ACTIONS=enabled,LUMEN_MCP_PROJECT_ACTIONS=project_only),text=True,capture_output=True,check=True)
            tools={tool['name']:tool for tool in json.loads(result.stdout)['result']['tools']}
            for name in ('lumen_project_create','lumen_project_update','lumen_project_start'):
                self.assertEqual(name in tools,enabled=='1' or project_only=='1')
                if name in tools:self.assertFalse(tools[name]['annotations']['readOnlyHint'])
            if project_only=='1':self.assertNotIn('lumen_settings_set',tools)
        config=self.root/'config'
        result=subprocess.run([str(script.with_name('lumen-setup'))],env=dict(os.environ,OPENCODE_HOME=str(config)),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        skill = next((config/name/'lumen-projects/SKILL.md' for name in ('skills','skill') if (config/name/'lumen-projects/SKILL.md').is_file()), None)
        self.assertIsNotNone(skill); self.assertIn('lumen_project_start',skill.read_text())


if __name__=='__main__':unittest.main()
