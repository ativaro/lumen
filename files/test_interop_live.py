import tempfile
from pathlib import Path
import unittest
from tools_data import Library
from tools_ui import Job
from interop_data import Registry
from interop_targets import apply

class LiveTest(unittest.TestCase):
    def test_household_folder_link_does_not_copy_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'docs';folder.mkdir();(folder/'receipt.txt').write_text('receipt')
            source=dict(app='files',kind='file',id=str(folder),path=str(folder),title='Docs')
            payload=dict(title='Docs',paths=[str(folder)],source=source,source_url=Registry(tmp).register(source))
            result=apply('household.add',payload,dict(token='folder',mode='link'),Job(lambda _:None),tmp)
            library=Library('household',tmp);record=library.get(result['id'])
            self.assertEqual(record['linked_paths'][0]['path'],str(folder));self.assertEqual(record['attachments'],[])
if __name__=='__main__':unittest.main()
