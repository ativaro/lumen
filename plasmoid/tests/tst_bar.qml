import QtQuick
import QtTest
import "../contents/ui" as Lumen

Rectangle {
    id: scene
    width: 480; height: 56; radius: 28; color: "#212b2f"
    Lumen.CompactBar { id: bar; anchors.fill: parent; anchors.margins: 6 }
    SignalSpy { id: toggles; target: bar; signalName: "toggle" }
    SignalSpy { id: launches; target: bar; signalName: "launch" }
    SignalSpy { id: searches; target: bar; signalName: "search" }
    SignalSpy { id: voices; target: bar; signalName: "voice" }
    TestCase {
        name: "LumenCompactBar"; when: windowShown
        function init() { bar.panelWidth = 0; }
        function test_search_icon_keeps_action_and_restores_label() {
            searches.clear(); bar.surface="search"; bar.panelWidth=40; scene.width=68;
            waitForRendering(bar);
            const search=findChild(bar,"searchButton"); const voice=findChild(bar,"voiceButton");
            compare(search.text,""); verify(!voice.visible);
            verify(search.mapToItem(scene,search.width,0).x <= scene.width);
            search.forceActiveFocus();keyClick(Qt.Key_Space);compare(searches.count,1);
            bar.panelWidth=460;scene.width=488;waitForRendering(bar);
            verify(search.text!=="");verify(voice.visible);
        }
        function verifyCentered(button) {
            const icon = button.contentItem.children[0];
            verify(Math.abs(icon.mapToItem(scene, 0, icon.height / 2).y - scene.height / 2) <= 0.5,
                   button.objectName + " icon must share the panel's vertical center");
        }
        function test_microphone_pointer_target_data() {
            return [{tag:"wide", width:480}, {tag:"compact", width:280}, {tag:"narrow", width:220}];
        }
        function test_microphone_pointer_target(data) {
            scene.height=48; scene.width=data.width; bar.surface="search";
            waitForRendering(bar); voices.clear(); searches.clear();
            const search=findChild(bar,"searchButton"); const voice=findChild(bar,"voiceButton");
            verify(search.x+search.width <= voice.x, "Search and microphone hit areas overlap");
            verify(voice.mapToItem(scene,voice.width,0).x <= scene.width, "Microphone leaves panel bounds");
            for (const x of [4,voice.width/2,voice.width-4]) {
                const point=voice.mapToItem(scene,x,voice.height/2);
                mouseMove(scene,point.x,point.y); wait(800);
                const count=voices.count;
                mouseClick(scene,point.x,point.y);
                compare(voices.count,count+1,"Click must reach microphone, including after hover");
                compare(searches.count,0,"Microphone must never activate text search");
            }
        }
        function test_roles_keyboard_and_bounds() {
            toggles.clear(); launches.clear(); searches.clear(); voices.clear();
            scene.height = 48; scene.width = 280; bar.surface = "home"; waitForRendering(bar);
            const home = findChild(bar, "homeButton"); const files = findChild(bar, "filesButton");
            verifyCentered(home); verifyCentered(files);
            verify(home.width > 90); verify(files.mapToItem(scene, files.width, 0).x <= scene.width);
            home.forceActiveFocus(); keyClick(Qt.Key_Space); compare(toggles.count, 1);
            files.forceActiveFocus(); keyClick(Qt.Key_Space); compare(launches.signalArguments[0][0], "files");
            grabImage(scene).save("artifacts/islands/bar-home.png");
            scene.width = 158; waitForRendering(bar);
            verifyCentered(home); verifyCentered(files);
            verify(files.mapToItem(scene, files.width, 0).x <= scene.width, "Compact home must fit a VM island");
            compare(files.text, "");
            files.forceActiveFocus(); keyClick(Qt.Key_Space); compare(launches.count, 2);
            grabImage(scene).save("artifacts/islands/bar-home-compact.png");
            scene.width = 480; bar.surface = "search"; waitForRendering(bar);
            const search = findChild(bar, "searchButton"); search.forceActiveFocus(); keyClick(Qt.Key_Space);
            verifyCentered(search);
            compare(searches.count, 1); verify(search.width > 370);
            const voice = findChild(bar, "voiceButton"); verify(voice.visible); verifyCentered(voice);
            verify(voice.mapToItem(scene, voice.width, 0).x <= scene.width);
            voice.forceActiveFocus(); keyClick(Qt.Key_Space); compare(voices.count, 1);
            compare(searches.count, 1);
            compare(findChild(bar, "askButton"), null); compare(launches.count, 2);
            grabImage(scene).save("artifacts/islands/bar-search.png");
            scene.width = 74; bar.surface = "control"; waitForRendering(bar);
            verify(!voice.visible);
            const center = findChild(bar, "centerButton"); center.forceActiveFocus(); keyClick(Qt.Key_Space);
            verifyCentered(center);
            compare(toggles.count, 2); verify(center.mapToItem(scene, center.width, 0).x <= scene.width);
        }
    }
}
