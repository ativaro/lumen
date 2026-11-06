import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools_data import Library


class FolderSearchTest(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.temp)
        self.enterContext(patch.dict(os.environ,LUMEN_TOOLS_DATA=self.temp,LUMEN_DATA=self.temp+'/state'))
        self.folder=self.root/'material';self.folder.mkdir()
        self.library=Library('workbench',self.root)
        self.project=self.library.create('Project',resources=[dict(kind='folder',target=str(self.folder),title='Material')])







    def test_real_mcp_worker_returns_cited_passage(self):
        import json,subprocess,sys
        (self.folder/'evidence.txt').write_text('budget worker evidence')
        worker=Path(__file__).with_name('lumen_mcp_tools.py')
        request=dict(name='lumen_project_search',arguments=dict(id=self.project,query='budget'))
        result=subprocess.run([sys.executable,str(worker)],input=json.dumps(request),text=True,capture_output=True,timeout=40,env=dict(os.environ,LUMEN_MCP_ACTIONS='0'))
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout);self.assertNotIn('error',data)
        self.assertIn('worker evidence',data['data']['items'][0]['snippet'])
        adapter=worker.parents[1]/'bin/lumen_mcp.py'
        requests=[dict(jsonrpc='2.0',id=1,method='tools/list'),dict(jsonrpc='2.0',id=2,method='tools/call',params=request)]
        reply=subprocess.run([sys.executable,str(adapter)],input='\n'.join(json.dumps(r) for r in requests)+'\n',text=True,capture_output=True,timeout=40,env=dict(os.environ,LUMEN_MCP_ACTIONS='0'))
        self.assertEqual(reply.returncode,0,reply.stderr)
        replies={r['id']:r for r in map(json.loads,reply.stdout.splitlines())}
        self.assertIn('lumen_project_search',{t['name'] for t in replies[1]['result']['tools']})
        self.assertIn('worker evidence',replies[2]['result']['structuredContent']['items'][0]['snippet'])

if __name__=='__main__':unittest.main()
