import QtQuick
import QtQuick.Window
import QtTest
import org.kde.kirigami as Kirigami
import "../contents/ui" as Lumen

Rectangle {
    id: scene; width: 560; height: 740; color: Kirigami.Theme.backgroundColor
    Lumen.NotificationCenter {
        id: center; anchors.fill: parent
        items: [{id:"1", system:true, source:"Browser", title:"Download abgeschlossen", body:"Reiseplanung.pdf ist bereit.", updated:Date.now()/1000, read:false, archived:false, snoozed:0, attention:false, actions:[{key:"open",label:"Datei öffnen"}]},
            {id:"2", system:false, source:"Lumen Projekte", title:"Wochenbericht ist bereit", body:"Die Ausführung ist abgeschlossen. Öffne das Ergebnis in deinem Projekt.", updated:Date.now()/1000, read:false, archived:false, snoozed:0, attention:false, actions:[{key:"open",label:"Ergebnis öffnen"}]}]
    }
    SignalSpy { id: action; target: center; signalName: "action" }
    SignalSpy { id: dnd; target: center; signalName: "toggleDnd" }
    Lumen.NotificationHost { id: host; pending: "test-snapshot"; visible: false }
    Lumen.NotificationHost { id: secondHost; pending: "test-snapshot"; visible: false }
    Lumen.NotificationToast { id: toast }
    SignalSpy { id: toastAction; target: toast; signalName: "action" }
    Window {
        id: panel; x: 100; y: 20; width: 480; height: 72
        Item { id: panelAnchor; property int rightFloatingPadding: 8; property int bottomFloatingPadding: 8 }
    }
    TestCase {
        name: "LumenNotification"; when: windowShown
        function init() {center.selectedKey="";center.filter="all";findChild(center,"notificationSearch").text="";}
        function test_discussion_handoff_uses_only_the_selected_card() {
            action.clear();center.choose(center.items[0]);waitForRendering(center);
            const button=findChild(center,"notificationDiscuss");
            verify(button!==null);button.clicked();
            compare(action.count,1);
            compare(action.signalArguments[0][0],"1");
            compare(action.signalArguments[0][1],true);
            compare(action.signalArguments[0][2],"discuss");
        }
        function test_toast_follows_panel_right_edge_and_bottom() {
            toast.anchorItem=panelAnchor;
            toast.present({id:"position",title:"Test",body:"",source:"Test",actions:[]});
            tryCompare(toast,"x",panel.x+panel.width-panelAnchor.rightFloatingPadding-toast.width);
            compare(toast.y,panel.y+panel.height-panelAnchor.bottomFloatingPadding+8);
            panel.width=420;panel.y=40;
            tryCompare(toast,"x",panel.x+panel.width-panelAnchor.rightFloatingPadding-toast.width);
            compare(toast.y,panel.y+panel.height-panelAnchor.bottomFloatingPadding+8);
            toast.dismiss();toast.anchorItem=null;
        }
        function test_private_summary_is_only_used_while_unlocked() {
            const row={id:"system",localIdentity:"local-1",system:true,title:"Generic",body:""};
            host.localItems=[{id:"local-1",source:"Test",updated:Date.now()/1000,read:false,archived:false,resolved:false,snoozed:0,title:"Private summary",body:"Synthetic",actions:[]}];
            host.locked=true;compare(host.displayNotice(row).title,"Generic");
            host.locked=false;host.gaming=false;
            if(!host.inhibited)compare(host.displayNotice(row).title,"Private summary");
            host.localItems=[];host.locked=true;
        }
        function test_one_presenter_and_gaming() {
            verify(host.primary!==secondHost.primary);
            const before=host.inhibited;
            host.gaming=true;verify(host.inhibited);
            host.gaming=false;compare(host.inhibited,before);
        }
        function test_toast_layout_and_dismissal() {
            toast.present({id:"example",title:"Dein Bericht ist bereit",body:"Der Wochenbericht wurde fertiggestellt.",source:"Lumen Projekte",actions:[{key:"open",label:"Ergebnis öffnen"}]});
            tryCompare(toast,"visible",true);
            verify((toast.flags & Qt.WindowDoesNotAcceptFocus)!==0);
            waitForRendering(toast.mainItem);grabImage(toast.mainItem).save("/tmp/lumen-toast.png");
            mouseClick(findChild(toast.mainItem,"notificationToastAction"));
            compare(toastAction.count,1);compare(toastAction.signalArguments[0][0],"example");compare(toastAction.signalArguments[0][1],"open");
            tryCompare(toast,"visible",false);
        }
        function test_selection_and_readable_responsive_detail() {
            center.choose(center.items[1]);
            compare(center.selected.title,"Wochenbericht ist bereit");
            verify(findChild(center,"notificationBack").visible);
            mouseClick(findChild(center,"notificationBack"));
            compare(center.selectedKey,"");
            scene.width=1040;waitForRendering(center);verify(center.wide);
            center.choose(center.items[0]);compare(center.selected.id,"1");
            const old=center.selectedKey;
            center.items=center.items.slice();compare(center.selectedKey,old);
            scene.width=560;
        }
        function test_click_during_refresh_is_queued() {
            host.act("a".repeat(64),false,"read");
            host.act("a".repeat(64),false,"archive");
            compare(host.queuedActions.length,2);
            compare(host.queuedActions[0].operation,"read");
            compare(host.queuedActions[1].operation,"archive");
            host.queuedActions=[];
        }
        function test_search_keyboard_and_layout() {
            const search=findChild(center,"notificationSearch");
            compare(findChild(center,"notificationList").count,2);
            search.text="Browser"; tryCompare(findChild(center,"notificationList"),"count",1);
            search.text=""; tryCompare(findChild(center,"notificationList"),"count",2);
            const button=findChild(center,"notificationDnd");button.forceActiveFocus();keyClick(Qt.Key_Space);compare(dnd.count,1);
            waitForRendering(center);grabImage(scene).save("/tmp/lumen-notifications.png");
            scene.width=480;waitForRendering(center);verify(search.width<480);
            const grouping=findChild(center,"notificationGroup");grouping.forceActiveFocus();keyClick(Qt.Key_Space);verify(center.grouped);
            center.filter="later";tryCompare(findChild(center,"notificationList"),"count",0);
            center.uiLanguage="en";compare(search.placeholderText,"Search notifications …");
        }
    }
}
