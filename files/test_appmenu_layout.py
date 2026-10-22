import json
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
var knownWidgetTypes = AVAILABLE ? ["org.lumen.appmenu"] : [];
function screenGeometry(screen) { return {width:WIDTH}; }
function makeWidget(type) {
    return {type:type, id:++identity, index:0, settings:{},
        writeConfig:function(key,value){this.settings[key]=value;},readConfig:function(key,value){return key in this.settings?this.settings[key]:value;},reloadConfig:function(){}};
}
var identity=0;
function makePanel(id, screen, types, length, offset) {
    var entries=types.map(makeWidget);
    function tracked(w) {
        Object.defineProperty(w,'index',{get:function(){return entries.indexOf(w);},set:function(value){
            entries.splice(entries.indexOf(w),1);entries.splice(Math.min(Math.max(0,value),entries.length-1),0,w);
        }});return w;
    }
    entries.forEach(tracked);
    return {id:id,screen:screen,location:"top",length:length,offset:offset,
        minimumLength:length,maximumLength:length,lengthMode:"custom",
        widgets:function(){return entries;},
        addWidget:function(type){var w=makeWidget(type);entries.push(tracked(w));return w;}};
}
var left=makePanel(1,0,["org.kde.plasma.kickoff","org.lumen.system"],WIDTH<1400?224:334,16);
if (FIT_MINIMUM) left.minimumLength=WIDTH-16;
var search=makePanel(2,0,["org.lumen.search"],WIDTH<1400?352:488,0);
var unrelated=makePanel(3,1,["org.kde.plasma.digitalclock"],300,16);
function panels(){return [left,search,unrelated];}
'''.replace('FIT_MINIMUM', json.dumps(fit_minimum)).replace('AVAILABLE', json.dumps(available)).replace('WIDTH', str(width))
        result = engine.evaluate(setup + (Path(__file__).parents[1] / 'desktop/appmenu.js').read_text() + '''
var first=installLumenAppMenus(panels());
var budget=left.widgets().filter(w=>w.type==="org.lumen.appmenu").map(w=>w.settings.widthBudget);
left.length+=300;
left.widgets().filter(w=>w.type==="org.lumen.appmenu" && !w.settings.compactView).forEach(w=>w.settings.requiredWidth=REQUIRED);
var second=installLumenAppMenus(panels());
JSON.stringify({first:first,second:second,budget:budget,searchLength:search.length,left:{lengthMode:left.lengthMode,max:left.maximumLength,
    widgets:left.widgets().map(function(w){return {type:w.type,settings:w.settings};})},
    search:search.widgets().map(function(w){return w.type;}),other:unrelated.widgets().map(function(w){return w.type;})});
'''.replace('REQUIRED',str(required)))
        self.assertFalse(result.isError(), result.toString())
        return json.loads(result.toString())

    def test_existing_panels_are_preserved_and_menu_installation_is_idempotent(self):
        result = self.run_layout()
        self.assertEqual([w['type'] for w in result['left']['widgets']], ['org.kde.plasma.kickoff','org.lumen.system','org.lumen.appmenu','org.lumen.appmenu'])
        self.assertEqual(result['left']['widgets'][1]['settings'], {})
        self.assertEqual(result['left']['lengthMode'], 'fit')
        self.assertEqual(result['left']['max'], 2112)
        self.assertEqual(result['search'], ['org.lumen.search'])
        self.assertEqual(result['other'], ['org.kde.plasma.digitalclock'])
        self.assertEqual(result['first'][0]['menus'], result['second'][0]['menus'])
        self.assertEqual(result['budget'], [w['settings']['widthBudget'] for w in result['left']['widgets'][2:]])

    def test_fit_panel_screen_wide_minimum_uses_original_visible_width(self):
        result = self.run_layout(width=3840, fit_minimum=True)
        self.assertEqual(result['left']['max'], 3304)
        self.assertEqual(result['budget'], [2946, 2946])

    def test_small_screen_uses_compact_budget_without_expanding_into_search(self):
        result = self.run_layout(width=960)
        self.assertEqual(result['left']['max'], 560)
        self.assertEqual(result['left']['widgets'][2]['settings']['widthBudget'], 312)

    def test_search_yields_to_long_real_menu_before_overflow(self):
        result = self.run_layout(required=1800)
        self.assertEqual(result['searchLength'],68)
        self.assertGreaterEqual(result['left']['widgets'][2]['settings']['widthBudget'],1800)
        self.assertEqual(self.run_layout(required=0)['searchLength'],488)

    def test_optional_menu_absence_leaves_desktop_unchanged(self):
        result = self.run_layout(available=False)
        self.assertEqual(result['first'], [])
        self.assertEqual(len(result['left']['widgets']), 2)
        self.assertEqual(result['left']['lengthMode'], 'custom')


if __name__ == '__main__':
    unittest.main()
