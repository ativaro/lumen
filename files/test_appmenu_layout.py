import json
import os
from pathlib import Path
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


class AppMenuLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def run_layout(self, width=2648, available=True, fit_minimum=False, required=0):
        engine = QJSEngine()
        setup = '''
var knownWidgetTypes = AVAILABLE ? ["org.lumen.appmenu","org.lumen.topbarcontext"] : [];
function screenGeometry(screen) { return {width:WIDTH}; }
var identity=100;
function makeWidget(type) {
    return {type:type,id:++identity,index:0,settings:{},writeConfig:function(k,v){this.settings[k]=v;},
        readConfig:function(k,v){return k in this.settings?this.settings[k]:v;},reloadConfig:function(){}};
}
function makePanel(id,screen,types,length,offset) {
    var entries=types.map(makeWidget),settings={};
    function tracked(w) {
        Object.defineProperty(w,'index',{get:function(){return entries.indexOf(w);},set:function(v){
            entries.splice(entries.indexOf(w),1);entries.splice(Math.min(Math.max(0,v),entries.length-1),0,w);
        }});return w;
    }
    entries.forEach(tracked);
    return {id:id,screen:screen,location:"top",height:56,length:length,offset:offset,alignment:"right",
        minimumLength:length,maximumLength:length,lengthMode:"custom",widgets:function(){return entries;},
        writeConfig:function(k,v){settings[k]=v;},
        addWidget:function(type){var w=makeWidget(type);entries.push(tracked(w));return w;}};
}
var left=makePanel(1,0,["org.kde.plasma.kickoff","org.lumen.system"],WIDTH<1400?224:334,16);
if (FIT_MINIMUM) left.minimumLength=WIDTH-16;
var search=makePanel(2,0,["org.lumen.search"],488,0);
var right=makePanel(3,0,["org.lumen.control"],300,16);
var unrelated=makePanel(4,1,["org.kde.plasma.digitalclock"],300,16);
var all=[left,search,right,unrelated];function panels(){return all;}
function Panel(){var p=makePanel(++identity,0,[],1,0);all.push(p);return p;}
'''.replace('FIT_MINIMUM', json.dumps(fit_minimum)).replace('AVAILABLE', json.dumps(available)).replace('WIDTH', str(width))
        source = Path(os.environ.get('LUMEN_TEST_APPMENU_SOURCE', str(Path(__file__).parents[1] / 'desktop/appmenu.js'))).read_text()
        result = engine.evaluate(setup + source + '''
var first=installLumenAppMenus(panels());left.length+=300;
left.widgets().filter(w=>w.type==="org.lumen.appmenu"&&!w.settings.compactView).forEach(w=>w.settings.requiredWidth=REQUIRED);
var second=installLumenAppMenus(panels());
JSON.stringify({first:first,second:second,search:search,context:all.find(p=>p.widgets().some(w=>w.type==="org.lumen.topbarcontext")),
 left:{max:left.maximumLength,minimum:left.minimumLength,widgets:left.widgets()},other:unrelated.widgets(),count:all.length});
'''.replace('REQUIRED', str(required)))
        self.assertFalse(result.isError(), result.toString())
        return json.loads(result.toString())

    def test_existing_widgets_and_context_panel_are_idempotent(self):
        value = self.run_layout()
        self.assertEqual([w['type'] for w in value['left']['widgets']], ['org.kde.plasma.kickoff','org.lumen.system','org.lumen.appmenu','org.lumen.appmenu'])
        self.assertEqual(value['first'][0]['menus'], value['second'][0]['menus'])
        self.assertEqual(value['context']['id'], value['first'][0]['createdContext'])
        self.assertEqual(value['count'],5)
        self.assertEqual([w['type'] for w in value['other']],['org.kde.plasma.digitalclock'])

    def test_wide_search_is_centered_and_context_does_not_overlap_it(self):
        for width in (2648,3840):
            value=self.run_layout(width=width)
            self.assertEqual(value['search']['alignment'],'center')
            self.assertEqual(value['search']['length'],350)
            search_left=(width-350)/2
            self.assertLessEqual(16+value['left']['max'],search_left-16)
            context_left=width-value['context']['offset']-value['context']['length']
            self.assertGreaterEqual(context_left,search_left+350+16)
            self.assertLessEqual(width-value['context']['offset'],width-332)

    def test_screen_wide_fit_minimum_is_not_reused_as_content_width(self):
        value=self.run_layout(width=3840,fit_minimum=True)
        self.assertLess(value['left']['minimum'],400)
        self.assertLess(value['left']['max'],1920)

    def test_small_display_hides_optional_context_before_overlapping_menus(self):
        value=self.run_layout(width=960,required=260)
        budget=value['left']['widgets'][2]['settings']['widthBudget']
        self.assertGreaterEqual(budget,260)
        self.assertEqual(value['context']['length'],1)
        self.assertLessEqual(16+value['left']['max'],960-value['search']['offset']-value['search']['length']-16)

    def test_search_yields_to_long_real_menus_and_restores(self):
        value=self.run_layout(required=1800)
        self.assertEqual(value['search']['length'],68)
        self.assertGreaterEqual(value['left']['widgets'][2]['settings']['widthBudget'],1800)
        self.assertEqual(self.run_layout()['search']['length'],350)

    def test_missing_native_menu_package_does_not_mutate_panels(self):
        value=self.run_layout(available=False)
        self.assertEqual(value['first'],[])
        self.assertEqual(len(value['left']['widgets']),2)
        self.assertEqual(value['count'],4)


if __name__=='__main__':unittest.main()
