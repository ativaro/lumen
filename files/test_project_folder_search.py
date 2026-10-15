import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools_data import Library
from project_folder_search import search,scan


class FolderSearchTest(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.temp)
        self.enterContext(patch.dict(os.environ,LUMEN_TOOLS_DATA=self.temp,LUMEN_DATA=self.temp+'/state'))
        self.folder=self.root/'material';self.folder.mkdir()
        self.library=Library('workbench',self.root)
        self.project=self.library.create('Project',resources=[dict(kind='folder',target=str(self.folder),title='Material')])

    def test_live_link_reads_nested_changes_and_removals(self):
        sub=self.folder/'sub';sub.mkdir();file=sub/'report.txt';file.write_text('The budget is 710 euros.')
        result=search(self.project,'budget')
        self.assertEqual(len(result['items']),1);self.assertIn('710',result['items'][0]['snippet'])
        self.assertEqual(result['items'][0]['path'],str(file));self.assertEqual(result['items'][0]['line'],1)
        file.write_text('The budget is 920 euros.')
        (self.folder/'new.md').write_text('New budget decision.')
        self.assertEqual(len(search(self.project,'budget')['items']),2)
        file.unlink();result=search(self.project,'budget')
        self.assertEqual([r['path'] for r in result['items']],[str(self.folder/'new.md')])
        self.library.update(self.project,resources=[])
        self.assertEqual(search(self.project,'budget')['items'],[])

    def test_hidden_symlinks_and_unlinked_folders_are_not_read(self):
        outside=self.root/'private';outside.mkdir();(outside/'secret.txt').write_text('budget secret')
        (self.folder/'.hidden.txt').write_text('budget hidden')
        (self.folder/'escape').symlink_to(outside,target_is_directory=True)
        (self.folder/'escape.txt').symlink_to(outside/'secret.txt')
        self.assertEqual(search(self.project,'budget')['items'],[])
        self.folder.rename(self.root/'old');self.folder.symlink_to(outside,target_is_directory=True)
        result=search(self.project,'budget');self.assertEqual(result['items'],[]);self.assertTrue(result['folders'][0]['incomplete'])

    def test_missing_archived_changed_and_limit_are_explicit(self):
        self.folder.rmdir();result=search(self.project,'budget');self.assertTrue(result['folders'][0]['error'])
        self.folder.mkdir()
        for i in range(45):(self.folder/f'{i}.txt').write_text('budget match')
        result=search(self.project,'budget');self.assertEqual(len(result['items']),40);self.assertTrue(result['folders'][0]['limit'])
        with patch('project_folder_search.sources',side_effect=[([],{'id':'a'}),([],{'id':'b'})]):
            with self.assertRaisesRegex(ValueError,'changed'):search(self.project,'budget')
        self.library.archive(self.project)
        with self.assertRaises(ValueError):search(self.project,'budget')

    def test_registered_tool_inherits_project_folder_without_executing(self):
        from projects_data import Projects
        from lumen_mcp_tools import invoke,DEFINITIONS
        item=Projects(self.library).add(self.project,'','Initiative','initiative')
        (self.folder/'note.txt').write_text('budget inherited')
        result=invoke('lumen_project_search',dict(id=item,query='budget'))
        self.assertEqual(len(result['items']),1)
        self.assertTrue(DEFINITIONS['lumen_project_search']['annotations']['readOnlyHint'])
        self.assertFalse(DEFINITIONS['lumen_project_search']['action'])

    def test_folder_move_updates_saved_link(self):
        from interop_paths import relocate
        (self.folder/'evidence.txt').write_text('budget moved')
        target=self.root/'moved';self.folder.rename(target)
        relocate(self.folder,target,self.root)
        self.assertEqual(self.library.get(self.project)['resources'][0]['target'],str(target))
        self.assertEqual(search(self.project,'budget')['items'][0]['path'],str(target/'evidence.txt'))

    def test_current_pdf_text_ignores_visual_cache_without_writes(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPdfWriter,QPainter
        app=QApplication.instance() or QApplication([])
        from lumen_ocr import save_cache,stamp,cache_path
        pdf=self.folder/'report.pdf';writer=QPdfWriter(str(pdf));painter=QPainter(writer);painter.drawText(100,300,'budget fresh pdf');painter.end();del writer
        image=self.folder/'image.png';image.write_bytes(b'image fixture')
        for path in (pdf,image):save_cache(path,stamp(path.stat()),ocr='budget cached OCR',caption='budget cached caption')
        before={path:(cache_path(path).read_bytes(),cache_path(path).stat().st_mtime_ns) for path in (pdf,image)}
        result=search(self.project,'budget')
        self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['path'],str(pdf))
        self.assertIn('fresh pdf',result['items'][0]['snippet']);self.assertNotIn('cached',result['items'][0]['snippet'])
        self.assertEqual(result['items'][0]['page'],1)
        self.assertEqual(before,{path:(cache_path(path).read_bytes(),cache_path(path).stat().st_mtime_ns) for path in (pdf,image)})

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
