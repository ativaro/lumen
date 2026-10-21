"""Retired local MCP tools cannot read or mutate the old project library."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from lumen_mcp_tools import invoke,DEFINITIONS
from test_mcp import mcp
from tools_data import Library

NAMES=('lumen_projects_list','lumen_project_read','lumen_project_search','lumen_project_runs',
       'lumen_project_create','lumen_project_update','lumen_project_start','lumen_project_link','lumen_project_unlink')

class ProjectActionsTest(unittest.TestCase):
    def test_old_tools_cannot_touch_originals_even_with_all_actions_enabled(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,LUMEN_TOOLS_DATA=root,LUMEN_MCP_ACTIONS='1',LUMEN_MCP_PROJECT_ACTIONS='1'):
            library=Library('workbench');key=library.create('Keep original',notes='Private original');before=library.get(key)
            with patch('projects_mcp.invoke',side_effect=AssertionError('retired read')),patch('projects_mcp.mutate',side_effect=AssertionError('retired write')),patch.object(mcp.subprocess,'Popen',side_effect=AssertionError('retired worker')):
                for name in NAMES:
                    with self.subTest(name=name):
                        self.assertNotIn(name,DEFINITIONS)
                        for entry in (invoke,mcp.tool_native):
                            with self.assertRaisesRegex(ValueError,'Server'):entry(name,{'id':key})
            self.assertEqual(library.get(key),before)

    def test_stdio_catalog_never_advertises_retired_tools(self):
        for enabled,project_only in (('0','0'),('1','0'),('0','1')):
            result=subprocess.run([sys.executable,mcp.__file__],input=json.dumps(dict(jsonrpc='2.0',id=1,method='tools/list'))+'\n',env=dict(os.environ,LUMEN_MCP_ACTIONS=enabled,LUMEN_MCP_PROJECT_ACTIONS=project_only),text=True,capture_output=True,check=True)
            names={tool['name'] for tool in json.loads(result.stdout)['result']['tools']}
            self.assertFalse(set(NAMES)&names)
            self.assertIn('lumen_memory_read',names)

    def test_installed_project_skill_uses_discovered_server_contracts(self):
        text=Path(__file__).resolve().parents[1].joinpath('opencode-skill/lumen-projects/SKILL.md').read_text()
        self.assertIn('lumen_server_tools',text)
        self.assertNotIn('LUMEN_MCP_PROJECT_ACTIONS',text)
