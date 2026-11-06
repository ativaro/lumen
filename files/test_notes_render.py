import unittest
from notes_render import prepare
from lumen_i18n import tr
from wissen_data import parse


class RenderTest(unittest.TestCase):
    def notes(self,values):return {path:parse(path,text.encode()) for path,text in values.items()}
    def test_sections_embeds_and_relative_links(self):
        notes=self.notes({'main.md':'# Main\n![[folder/other#Details]]','folder/other.md':'---\ntags: [secret]\n---\n# Other\n## Details\nSee [[../third#End|next]]\n![local](pic.png)\n## Omit\nNot included','third.md':'# Third\n## End\nHere'})
        output=prepare(notes['main.md']['text'],'main.md',notes)
        self.assertIn('lumen-note:/folder%2Fother.md#Details',output)
        self.assertIn('[next](lumen-note:/third.md#End)',output)
        self.assertIn('(folder/pic.png)',output)
        self.assertNotIn('Not included',output);self.assertNotIn('secret',output)
    def test_cycle_missing_code_and_size_are_bounded(self):
        notes=self.notes({'main.md':'# Main\n![[other]]\n`![[other]]`\n![[missing]]','other.md':'# Other\n![[main]]'})
        output=prepare(notes['main.md']['text'],'main.md',notes)
        self.assertIn(tr('Zyklische Einbettung – Quelle über den Link öffnen.'),output);self.assertIn('`![[other]]`',output);self.assertIn(tr('Eingebettete Notiz nicht gefunden.'),output)
        notes['other.md']['text']='x'*131073
        self.assertIn(tr('Einbettung zu groß – Quelle öffnen.'),prepare('![[other]]','main.md',notes))
        self.assertNotIn('/etc/passwd',prepare('![[../../etc/passwd]]','main.md',notes))
    def test_block_embed_and_obsidian_local_image(self):
        notes=self.notes({'main.md':'# Main','other.md':'# Other\n\nKeep 🌍 ^block\n\nOmit'})
        output=prepare('![[other#^block]]\n![[image.png]]','main.md',notes)
        self.assertIn('Keep 🌍',output);self.assertNotIn('Omit',output);self.assertIn('![image.png](image.png)',output)
