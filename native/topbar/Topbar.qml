import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import org.kde.kirigami as Kirigami
import Lumen.Topbar 1.0
import org.kde.notificationmanager as Notifications

Window {
    id: bar
    objectName: "lumenStandaloneTopbar"
    readonly property string layout:panelData.layout
    readonly property bool classic:layout==="classic"
    readonly property bool deck:layout==="deck"
    readonly property bool twoRows:classic && width<1320
    readonly property int barSize:classic?(twoRows?118:80):deck?118:layout==="band"?68:60
    readonly property int rowHeight:classic?36:44
    property bool expandedComposer:false
    property alias noteContext:questionState.note
    property string notePendingAction:""
    QtObject {
        id:questionState
        property string draft:""
        property var note:({})
        property string submittedNote:""
        property string submitted:""
        property string pendingAction:""
        property bool pending:false
    }
    width:1280
    height:Math.max(barSize,launcher.visible?launcher.y+launcher.height+12:0,systemPopup.visible?systemPopup.y+systemPopup.height+12:0,networkPopup.visible?networkPopup.y+networkPopup.height+12:0,audioPopup.visible?audioPopup.y+audioPopup.height+12:0,overflow.visible?overflow.y+overflow.height+12:0,windowMenu.visible?windowMenu.y+windowMenu.height+12:0,trayPopup.visible?trayPopup.y+trayPopup.height+12:0,calendar.visible?calendar.y+calendar.height+12:0,askPopup.visible?askPopup.y+askPopup.height+12:0,contextDrawer.visible?contextDrawer.y+contextDrawer.height+12:0,activityPopup.visible?activityPopup.y+activityPopup.height+12:0)
    color:"transparent"
    property bool ready:false
    visible:ready && !windowState.fullScreen
    flags:Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    property var stateData:panelData.snapshot
    readonly property var colors:stateData.palette
    property int visibleMenus:appMenu.entries.length
    property bool showContext:true
    property bool showStatus:true
    property real appLabelWidth:180
    readonly property var activeTray:trayModel.items.filter(item=>item.status!=="Passive")
    readonly property bool hasPassiveTray:trayModel.items.some(item=>item.status==="Passive")
    property int shownTray:0
    readonly property bool contextAvailable: ["Chromium","Google Chrome","Brave","Mozilla Firefox","Microsoft Edge","Vivaldi","Lumen Reader","Reader"].includes(windowState.appName)
    readonly property string currentSymbol:({"Lumen Notes":"wissen","Notes":"wissen","Lumen Projekte":"workbench","Projekte":"workbench","Lumen Inbox":"inbox","Inbox":"inbox","Lumen Files":"files","Dateien":"files"})[windowState.appName]||""
    property string clockText:Qt.formatTime(new Date(),"hh:mm")
    property double now:Date.now()
    readonly property bool quiet:notificationSettings.notificationsInhibitedUntil.getTime()>now
    readonly property var activity:stateData.activity||({})
    readonly property int focusSeconds:activity.focus?.end?Math.max(0,Math.ceil(activity.focus.end-now/1000)):activity.focus?.remaining||0
    readonly property var currentActivity:chooseActivity()
    readonly property string statusSection:currentActivity.section
    readonly property string statusText:currentActivity.text
    function chooseActivity(){
        if(activity.decisionError)return {section:"decision",text:t("Freigaben prüfen"),icon:"dialog-warning"}
        if((activity.decisions||[]).length)return {section:"decision",text:t("Freigabe nötig"),icon:"help-about"}
        if(stateData.operations?.audio)return {section:"operations",text:t("Aufnahme in Audio Studio"),icon:"media-record"}
        if(activity.focus?.state && activity.focus.state!=="off"){
            const remaining=Math.floor(focusSeconds/60).toString().padStart(2,"0")+":"+(focusSeconds%60).toString().padStart(2,"0")
            return {section:"focus",text:focusSeconds?t(activity.focus.state==="paused"?"Fokus pausiert":"Fokus")+" · "+remaining:t("Fokuszeit beendet"),icon:"chronometer"}
        }
        if(stateData.operations?.transfer)return {section:"operations",text:t("Übertragungen"),icon:"folder-upload"}
        const player=panelData.players.find(p=>p.playing)
        if(player)return {section:"media",text:player.title||t("Wiedergabe"),icon:"media-playback-start"}
        if(activity.update?.pending)return {section:"update",text:t("Update bereit"),icon:"system-software-update"}
        if(quiet)return {section:"dnd",text:t("Nicht stören"),icon:"notifications-disabled"}
        return {section:"focus",text:t("Alles im Blick"),icon:"emblem-ok-symbolic"}
    }
    Notifications.Settings {id:notificationSettings;live:true}
    function showActivity(page){activityPopup.page=page;activityPopup.section=statusSection;activityPopup.open()}
    function t(source){return stateData.labels?.[source] || source}
    readonly property var uiLocale:Qt.locale(stateData.language==="de"?"de_CH":"en_US")
    function fit(){
        let total=0
        for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(b)total+=b.implicitWidth}
        // Keep the real menus before optional title/tray space; narrow screens get a second input row.
        if(classic){
            showStatus=width>=900
            expandedComposer=true
            const currentTray=(trayRow.visible?trayRow.implicitWidth+1:0)+(trayMore.visible?trayMore.implicitWidth+1:0)
            const baseSystem=systemRow.implicitWidth-currentTray
            const traySpace=width-24-baseSystem-appRow.x-total-(appName.visible?44:0)-quickRow.implicitWidth-12-(twoRows?0:activityButton.width+324)
            const allTray=activeTray.length*41+(hasPassiveTray?41:0)
            shownTray=allTray<=traySpace?activeTray.length:Math.max(0,Math.min(activeTray.length,Math.floor((traySpace-41)/41)))
            const available=(twoRows?systemRow.x-12:systemRow.x-activityButton.width-300-24)-appRow.x-quickRow.implicitWidth-12
            appLabelWidth=Math.max(40,Math.min(appName.naturalWidth,180,available-total-8))
            const space=available-appLabelWidth-4
            visibleMenus=menuButtons.count
            if(total>space){let used=overflowButton.implicitWidth;visibleMenus=0;for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(!b||used+b.implicitWidth>space)break;used+=b.implicitWidth;visibleMenus++}}
            showContext=false
            Qt.callLater(mask);return
        }
        const statusExtras=networkButton.implicitWidth+volumeButton.implicitWidth+2
        const compactCost=compactControls.implicitWidth+1
        const currentTray=(trayRow.visible?trayRow.implicitWidth+1:0)+(trayMore.visible?trayMore.implicitWidth+1:0)
        const baseSystem=systemRow.implicitWidth-(showStatus?statusExtras:compactCost)-currentTray
        const core=deck?32:homeRow.x+homeRow.width+16
        const available=width-core-baseSystem-24
        showStatus=width>=1100 && (deck || total+statusExtras+100<available)
        const controlsCost=showStatus?statusExtras:compactCost
        const allTray=activeTray.length*41+(hasPassiveTray?trayMore.implicitWidth+1:0)
        const traySpace=deck?width-homeRow.width-baseSystem-controlsCost-60:available-controlsCost-total-110
        shownTray=allTray<=traySpace?activeTray.length:Math.max(0,Math.min(activeTray.length,Math.floor((traySpace-41)/41)))
        expandedComposer=deck?width>=760 && total+340<width:width>=1100 && (classic || available-controlsCost-allTray-total>420)
        const rightEdge=expandedComposer?inlineComposer.x-8:deck?width-16:systemRow.x-12
        const menuSpace=rightEdge-appRow.x-14
        appLabelWidth=Math.max(40,Math.min(appName.naturalWidth,180,menuSpace-total-8))
        let availableMenus=menuSpace-(appName.visible?appLabelWidth+4:0)-quickRow.implicitWidth
        visibleMenus=menuButtons.count
        if(total>availableMenus){let used=overflowButton.implicitWidth;visibleMenus=0;for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(!b || used+b.implicitWidth>availableMenus)break;used+=b.implicitWidth;visibleMenus++}}
        showContext=total+appLabelWidth+quickRow.implicitWidth+160<menuSpace
        Qt.callLater(mask)
    }
    function mask(){
        let regions=classic?[Qt.rect(12,12,width-24,barSize-24)]:[Qt.rect(0,0,width,barSize)]
        let popupOpen=false
        for(const popup of [launcher,systemPopup,networkPopup,audioPopup,overflow,windowMenu,trayPopup,calendar,askPopup,contextDrawer,activityPopup])if(popup.visible){regions.push(Qt.rect(popup.x,popup.y,popup.width,popup.height));popupOpen=true}
        panelData.inputMask(bar,regions,popupOpen)
    }
    onBarSizeChanged:Qt.callLater(mask)
    onLayoutChanged:if(ready){launcher.close();systemPopup.close();networkPopup.close();audioPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();contextDrawer.close();activityPopup.close();Qt.callLater(()=>{fit();if(layout==="context" && inlineComposer.visible && inlineComposer.editing)contextDrawer.open()})}
    function showLauncher(programs){launcher.programs=programs;launcher.open();panelData.refresh()}
    function updateMenu(){appMenu.setEndpoint(windowState.service,windowState.path)}
    function dismissIfInactive(){if(!bar.active && !appMenu.opened && !trayModel.opened){launcher.close();systemPopup.close();networkPopup.close();audioPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();contextDrawer.close();activityPopup.close();trayModel.close()}}
    onHeightChanged:Qt.callLater(mask)
    onActiveChanged:if(active)focusLoss.stop();else focusLoss.restart()
    Timer {id:focusLoss;interval:80;onTriggered:bar.dismissIfInactive()}
    Timer {id:restoreFocus;interval:100;onTriggered:if(bar.active && !inlineComposer.editing && !appMenu.opened && !trayModel.opened && ![launcher,systemPopup,networkPopup,audioPopup,overflow,windowMenu,trayPopup,calendar,askPopup,contextDrawer,activityPopup].some(p=>p.visible))windowState.action("activate")}
    onWidthChanged:Qt.callLater(fit)
    onVisibleChanged:if(visible)Qt.callLater(fit)
    Timer {interval:1000;running:true;repeat:true;onTriggered:{bar.now=Date.now();bar.clockText=Qt.formatTime(new Date(),"hh:mm")}}
    WindowState {
        id:windowState
        objectName:"activeWindowState"
        screenGeometry:Qt.rect(bar.screen.virtualX,bar.screen.virtualY,bar.screen.width,bar.screen.height)
        holdActiveWindow:!!bar.notePendingAction || inlineComposer.editing || appMenu.opened || trayModel.opened || launcher.opened || systemPopup.opened || networkPopup.opened || audioPopup.opened || overflow.opened || windowMenu.opened || trayPopup.opened || calendar.opened || askPopup.opened || contextDrawer.opened || activityPopup.opened
        onServiceChanged:Qt.callLater(bar.updateMenu)
        onPathChanged:Qt.callLater(bar.updateMenu)
        onFullScreenChanged:if(fullScreen){appMenu.close();trayModel.close();launcher.close();systemPopup.close();networkPopup.close();audioPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();contextDrawer.close();activityPopup.close()}
    }
    AppMenu {id:appMenu;objectName:"applicationMenus";onEntriesChanged:Qt.callLater(bar.fit)}
    Connections {target:appMenu;function onOpenedChanged(){if(appMenu.opened)restoreFocus.stop();else{overflow.close();restoreFocus.restart()}Qt.callLater(bar.dismissIfInactive)}}
    Connections {target:trayModel;function onChanged(){Qt.callLater(bar.fit)}function onOpenedChanged(){if(trayModel.opened)restoreFocus.stop();else restoreFocus.restart();Qt.callLater(bar.dismissIfInactive)}}
    Connections {target:panelData;function onChanged(){bar.now=Date.now();Qt.callLater(bar.fit)}function onShowAppsRequested(name){if(name===bar.screen.name){bar.showLauncher(true)}}
        function onNoteAttached(action,note){if(action===bar.notePendingAction){questionState.note=note;bar.notePendingAction=""}}
        function onControlFailed(action){if(action===bar.notePendingAction)bar.notePendingAction=""}}
    Rectangle {
        visible:!bar.classic;width:bar.width;height:bar.barSize;color:bar.colors.window
        Rectangle {anchors.bottom:parent.bottom;width:parent.width;height:1;color:bar.colors.border}
        Rectangle {visible:bar.deck;x:16;y:64;width:parent.width-32;height:1;color:bar.colors.border}
    }
    Rectangle {
        id:leftIsland;objectName:"leftIsland";visible:bar.classic
        x:12;y:12;height:activityPopup.visible?activityPopup.y+activityPopup.height-12:bar.barSize-24;width:bar.width-24
        radius:(bar.colors.radius||10)+7;color:bar.colors.window;border.color:bar.colors.border
    }
    Row {
        id:homeRow;x:bar.classic?24:16;y:(bar.classic?40:bar.deck?34:bar.barSize/2)-height/2
        spacing:bar.classic?2:7
        onWidthChanged:Qt.callLater(bar.fit)
        BarButton {id:homeLauncher;objectName:"launcherButton";key:!bar.classic;colors:bar.colors;text:bar.classic?"Lumen":"Lumen ⌄";glyph:bar.classic?"qrc:/lumen/icons/lumen-mark.svg":"";symbol:bar.classic?"":"mark";iconOnly:bar.classic || bar.width<560;font.weight:Font.Medium;onClicked:bar.showLauncher(false)}
        Rectangle {visible:bar.classic;width:1;height:22;color:bar.colors.border;anchors.verticalCenter:parent.verticalCenter}
        BarButton {key:!bar.classic;colors:bar.colors;text:bar.t("Dateien");glyph:bar.classic?"folder":"";symbol:bar.classic?"":"files";iconOnly:bar.classic || bar.width<720;onClicked:panelData.launch("files")}
        Repeater {model:bar.deck?(bar.stateData.apps||[]).filter(app=>["wissen","workbench","inbox"].includes(app.id)):[]
            BarButton {required property var modelData;objectName:"pin_"+modelData.id;key:true;colors:bar.colors;text:modelData.label;symbol:modelData.id;iconOnly:bar.width<1100;visible:bar.width>=720;onClicked:panelData.launch("app",modelData.id)}
        }
    }
    RowLayout {
        id:appRow;x:bar.deck?16:homeRow.x+homeRow.width+8;y:bar.classic?40-height/2:bar.deck?72:(bar.barSize-height)/2
        width:bar.classic?(bar.twoRows?Math.max(0,systemRow.x-x-12):bar.appLabelWidth+applicationMenuRow.implicitWidth+quickRow.implicitWidth+12):Math.max(0,(bar.expandedComposer?inlineComposer.x-8:bar.deck?bar.width-16:systemRow.x-12)-x);height:bar.rowHeight;spacing:2
        BarButton {id:appName;objectName:"activeAppButton";key:!bar.classic;current:!bar.classic;onNaturalWidthChanged:Qt.callLater(bar.fit);iconOnly:bar.appLabelWidth<=45;colors:bar.colors;text:windowState.appName||bar.t("Desktop");glyph:"application-menu";symbol:bar.classic?"":bar.currentSymbol;onClicked:windowMenu.open();visible:bar.width>=560;Layout.minimumWidth:0;Layout.preferredWidth:bar.appLabelWidth;Layout.maximumWidth:180}
        Row {
            id:applicationMenuRow
            spacing:0
            Repeater {
                id:menuButtons;model:appMenu.entries
                BarButton {required property var modelData;required property int index;objectName:"applicationMenu_"+index;colors:bar.colors;text:modelData.label;enabled:modelData.enabled;visible:index<bar.visibleMenus;onClicked:appMenu.show(index,this);onImplicitWidthChanged:Qt.callLater(bar.fit)}
                onCountChanged:Qt.callLater(bar.fit)
            }
            BarButton {id:overflowButton;objectName:"menuOverflowButton";colors:bar.colors;text:bar.t("Weitere App-Menüs");glyph:"overflow-menu";iconOnly:true;visible:bar.visibleMenus<menuButtons.count || !appName.visible;onClicked:menuButtons.count?overflow.open():windowMenu.open()}
        }
        Row {id:quickRow;spacing:2
            BarButton {objectName:"windowOverviewButton";colors:bar.colors;text:bar.t("Fensterübersicht");glyph:"view-grid";iconOnly:true;onClicked:bar.showActivity("windows")}
            BarButton {objectName:"recentContentButton";colors:bar.colors;text:bar.t("Letzten Inhalt fortsetzen");glyph:"document-open-recent";iconOnly:true;onClicked:bar.showActivity("recent")}
        }
        Item {Layout.fillWidth:true;Layout.minimumWidth:0}
        Text {visible:bar.showContext && !!windowState.title;text:windowState.title;color:bar.colors.muted;elide:Text.ElideRight;textFormat:Text.PlainText;Layout.fillWidth:true;Layout.maximumWidth:300;Layout.minimumWidth:0}
        BarButton {colors:bar.colors;text:windowState.appName.includes("Reader")?bar.t("In Lumen besprechen"):bar.t("Seite merken …");glyph:"bookmark-new";iconOnly:true;visible:bar.showContext && bar.contextAvailable;onClicked:panelData.context(windowState.appName,windowState.title,windowState.pid)}
    }
    AskComposer {
        id:inlineComposer;objectName:"inlineComposer";onEditingChanged:if(editing){restoreFocus.stop();if(bar.layout==="context" && visible)contextDrawer.open()}
        visible:bar.expandedComposer;width:bar.classic?Math.max(0,activityButton.x-(bar.twoRows?24:appRow.x+appRow.width+12)-12):310
        x:bar.classic?(bar.twoRows?24:appRow.x+appRow.width+12):bar.deck?bar.width-310-16:systemRow.x-310-8;y:bar.classic?(bar.twoRows?82:40)-height/2:bar.deck?72:(bar.barSize-height)/2
        colors:bar.colors;translate:bar.t;controller:panelData;keyStyle:!bar.classic
        request:questionState;onInspectAttachment:contextDrawer.open();onSent:{askPopup.close();contextDrawer.close()}
    }
    BarButton {id:activityButton;objectName:"activityButton";visible:bar.classic;colors:bar.colors;monochrome:true;text:bar.statusText;glyph:bar.currentActivity.icon
        width:bar.width<900?160:190;x:bar.twoRows?bar.width-width-24:systemRow.x-width-12;y:(bar.twoRows?82:40)-height/2
        onClicked:bar.showActivity("status")}
    Row {
        id:systemRow;x:bar.width-width-(bar.classic?24:16);y:(bar.classic?40:bar.deck?34:bar.barSize/2)-height/2;spacing:bar.classic?1:5
            BarButton {objectName:"activityCompactButton";visible:!bar.classic;colors:bar.colors;text:bar.statusText;glyph:"view-task";iconOnly:true;onClicked:bar.showActivity("status")}
            Row {
                id:trayRow;spacing:1;visible:bar.shownTray>0
                Repeater {model:bar.activeTray.length
                    BarButton {required property int index;readonly property var entry:bar.activeTray[index];objectName:"trayItem_"+index;colors:bar.colors;text:entry?entry.title:"";glyph:entry?entry.icon:"";iconOnly:true;visible:index<bar.shownTray;onClicked:trayModel.activate(entry.identity,this)
                        TapHandler {acceptedButtons:Qt.RightButton|Qt.MiddleButton;onTapped:(point,button)=>trayModel.activate(parent.entry.identity,parent,button===Qt.RightButton?3:2)}
                    }
                }
            }
            BarButton {id:trayMore;objectName:"trayMoreButton";colors:bar.colors;text:bar.t("Hintergrund-Apps");glyph:"arrow-down";iconOnly:true;visible:bar.shownTray<bar.activeTray.length || bar.hasPassiveTray;onClicked:trayPopup.open()}
            BarButton {key:!bar.classic;objectName:"askButton";colors:bar.colors;text:bar.t("Lumen fragen oder suchen");glyph:"search";iconOnly:true;visible:!bar.expandedComposer;onClicked:{askPopup.open();popupComposer.focusInput()}}
            BarButton {key:!bar.classic;objectName:"compactDictateButton";colors:bar.colors;text:bar.t("Mit Lumen sprechen");glyph:"microphone-sensitivity-high";iconOnly:true;visible:!bar.expandedComposer;onClicked:panelData.launch("voice")}
            BarButton {colors:bar.colors;text:bar.t("Übertragungen")+(bar.stateData.operations?.transfer?" · "+bar.stateData.operations.transfer.count:"");glyph:"folder-upload";iconOnly:true;visible:!bar.classic && !!bar.stateData.operations?.transfer;onClicked:panelData.launch("transfer",bar.stateData.operations.transfer.id)}
            BarButton {colors:bar.colors;text:bar.t("Aufnahme in Audio Studio");glyph:"media-record";iconOnly:true;visible:!bar.classic && !!bar.stateData.operations?.audio;onClicked:panelData.launch("app","meetings")}
            BarButton {key:!bar.classic;objectName:"systemErrorButton";colors:bar.colors;text:bar.t(panelData.error);glyph:"dialog-warning";iconOnly:true;visible:!!panelData.error;onClicked:systemPopup.open()}
            BarButton {id:networkButton;objectName:"networkButton";key:!bar.classic;colors:bar.colors;text:bar.t("Netzwerk");glyph:"network-wireless";iconOnly:true;visible:bar.showStatus;onClicked:{audioPopup.close();systemPopup.close();networkPopup.open()}}
            BarButton {id:volumeButton;key:!bar.classic;objectName:"systemControlsButton";colors:bar.colors;text:bar.t("Audio");glyph:bar.stateData.system?.muted?"audio-volume-muted":"audio-volume-high";iconOnly:true;visible:bar.showStatus;onClicked:{networkPopup.close();systemPopup.close();audioPopup.open();panelData.refresh()}}
            BarButton {key:!bar.classic;colors:bar.colors;text:bar.t("Mitteilungen")+(bar.quiet?" · "+bar.t("Nicht stören"):bar.stateData.unread>0?" · "+bar.stateData.unread:"");glyph:bar.quiet?"notifications-disabled":bar.stateData.unread>0?"notifications-new":"notifications";iconOnly:true;onClicked:panelData.launch("notifications")}
            BarButton {colors:bar.colors;objectName:"clockButton";text:bar.clockText;visible:bar.width>460;onClicked:calendar.open()}
            BarButton {id:compactControls;key:!bar.classic;objectName:"compactControlsButton";colors:bar.colors;text:bar.t("Systemsteuerung");glyph:"settings-configure";iconOnly:true;onClicked:{networkPopup.close();audioPopup.close();systemPopup.open();panelData.refresh()}}
        onImplicitWidthChanged:Qt.callLater(bar.fit)
    }
    component BarPopup:Popup {
        default property alias body:scroller.contentData
        parent:bar.contentItem
        popupType:Popup.Item
        focus:true
        padding:16;closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
        width:Math.min(380,bar.width-24);y:bar.barSize+6
        height:Math.min(implicitHeight,Math.max(100,bar.screen.height-bar.barSize-24))
        contentItem:ScrollView {id:scroller;clip:true;contentWidth:availableWidth;implicitHeight:contentHeight}
        onVisibleChanged:Qt.callLater(bar.mask)
        onOpened:restoreFocus.stop()
        onClosed:{Qt.callLater(bar.mask);restoreFocus.restart()}
        background:Rectangle {color:bar.colors.window;radius:13;border.color:bar.colors.border}
    }
    BarPopup {
        id:launcher;objectName:"appsPopup";x:12
        property bool programs:false
        onOpened:if(programs)Qt.callLater(()=>programLoader.item?.focusSearch())
        ColumnLayout {
            width:parent.width
            spacing:12
            Label {text:bar.t("Start");color:bar.colors.text;font.pixelSize:19;font.weight:Font.Medium;Layout.fillWidth:true}
            RowLayout {Layout.fillWidth:true;spacing:4
                BarButton {colors:bar.colors;text:"Lumen Apps";checkable:true;checked:!launcher.programs;highlighted:!launcher.programs;Layout.fillWidth:true;onClicked:launcher.programs=false}
                BarButton {objectName:"programsTab";colors:bar.colors;text:bar.t("Programme");checkable:true;checked:launcher.programs;highlighted:launcher.programs;Layout.fillWidth:true;onClicked:launcher.programs=true}
            }
            Loader {id:programLoader;Layout.fillWidth:true;active:launcher.programs;visible:active;onLoaded:item.focusSearch()
                sourceComponent:ProgramList {colors:bar.colors;translate:bar.t;onLaunched:launcher.close()}
            }
            GridLayout {
                visible:!launcher.programs;columns:launcher.width>=440?4:3;columnSpacing:4;rowSpacing:6;Layout.fillWidth:true
                Repeater {
                    model:bar.stateData.apps||[]
                    BarButton {required property var modelData;objectName:"openApp_"+modelData.id;colors:bar.colors;text:modelData.label;Layout.fillWidth:true;Layout.preferredWidth:0;Layout.preferredHeight:Math.max(88,contentItem.implicitHeight+20);Accessible.name:modelData.title;
                        contentItem:Column {spacing:6;Kirigami.Icon {source:"qrc:/lumen/icons/"+(modelData.id==="lumen"?"lumen":"lumen-"+modelData.id)+".svg";width:40;height:40;anchors.horizontalCenter:parent.horizontalCenter}Text {text:modelData.label;color:bar.colors.text;horizontalAlignment:Text.AlignHCenter;width:parent.width;wrapMode:Text.WordWrap}}
                        onClicked:{launcher.close();panelData.launch("app",modelData.id)}
                    }
                }
            }
            Label {visible:!!panelData.error;text:bar.t(panelData.error);color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            Rectangle {height:1;color:bar.colors.border;Layout.fillWidth:true}
            BarButton {visible:!launcher.programs;colors:bar.colors;text:bar.t("Alle Aufgaben");glyph:"view-task";Layout.fillWidth:true;onClicked:{launcher.close();panelData.launch("tasks")}}
            BarButton {colors:bar.colors;text:bar.t("Lumen fragen oder suchen");glyph:"search";Layout.fillWidth:true;onClicked:{launcher.close();panelData.launch("search")}}
        }
    }
    component ContextActions:ColumnLayout {
        id:contextActions
        required property string prefix
        spacing:10
        Label {text:bar.t("Mit Lumen weiterarbeiten");color:bar.colors.text;font.pixelSize:17;Layout.fillWidth:true}
        Label {visible:!!windowState.title;text:windowState.appName+" · "+windowState.title;color:bar.colors.muted;elide:Text.ElideRight;Layout.fillWidth:true}
        Label {text:bar.t("Nur ausdrücklich angehängte Quellen werden verwendet.");color:bar.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
        BarButton {objectName:contextActions.prefix+"attachNoteButton";colors:bar.colors;glyph:"accessories-text-editor";text:bar.notePendingAction?bar.t("Notiz wird geprüft …"):bar.t("Geöffnete Notes-Notiz anhängen");Layout.fillWidth:true
            visible:["Notes","Lumen Notes"].includes(windowState.appName);enabled:!bar.notePendingAction
            onClicked:bar.notePendingAction=panelData.attachNote(windowState.pid)
        }
        RowLayout {visible:!!questionState.note.reference;Layout.fillWidth:true
            Label {objectName:contextActions.prefix+"attachedNoteTitle";text:(questionState.note.reference?.title||"")+" · Lumen Notes";color:bar.colors.text;elide:Text.ElideRight;Layout.fillWidth:true}
            BarButton {objectName:contextActions.prefix+"removeNoteButton";colors:bar.colors;glyph:"edit-clear";text:bar.t("Notiz entfernen");iconOnly:true;onClicked:questionState.note=({})}
        }
        Label {visible:!!questionState.note.reference;text:bar.t("Die gespeicherte Notiz wird im Servergespräch verwendet.");color:bar.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
        Flow {Layout.fillWidth:true;spacing:4
            Repeater {model:[bar.t("Zusammenfassen"),bar.t("Checkliste erstellen"),bar.t("Offene Punkte finden")]
                BarButton {required property string modelData;required property int index;objectName:contextActions.prefix+"contextSuggestion_"+index;colors:bar.colors;text:modelData;enabled:!!questionState.note.reference
                    onClicked:{const composer=inlineComposer.visible?inlineComposer:popupComposer;composer.setPrompt(modelData+": "+bar.t("Bitte die angehängte Notes-Notiz verwenden."))}
                }
            }
        }
        Label {visible:!!panelData.error;text:bar.t(panelData.error);color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
    }
    BarPopup {
        id:contextDrawer;objectName:"contextDrawer";focus:false
        width:Math.min(530,bar.width-24);x:bar.width-width-12
        ContextActions {prefix:"dock";width:parent.width}
    }
    BarPopup {
        id:askPopup;x:bar.width-width-12
        ColumnLayout {width:parent.width;spacing:12
            Label {text:bar.t("Neue Frage an Lumen");color:bar.colors.text;font.pixelSize:19;Layout.fillWidth:true}
            AskComposer {id:popupComposer;objectName:"popupComposer";Layout.fillWidth:true;colors:bar.colors;translate:bar.t;controller:panelData;request:questionState;onSent:{askPopup.close();contextDrawer.close()} onInspectAttachment:{}}
            ContextActions {prefix:"popup";visible:bar.layout==="context" || !!questionState.note.reference;Layout.fillWidth:true}
            Label {visible:bar.layout!=="context" && !questionState.note.reference && !!panelData.error;text:bar.t(panelData.error);color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
        }
    }
    ActivityMenu {
        id:activityPopup;objectName:"activityPopup";parent:bar.contentItem
        width:bar.classic?bar.width-24:Math.min(980,bar.width-24);x:(bar.width-width)/2;y:bar.classic?bar.barSize-12:bar.barSize+6;connected:bar.classic
        heightLimit:Math.max(100,bar.screen.height-bar.barSize-24)
        colors:bar.colors;controller:panelData;windows:windowState;notifications:notificationSettings;translate:bar.t;now:bar.now
        onGeometryUpdated:Qt.callLater(bar.mask)
        onOpened:restoreFocus.stop()
        onClosed:restoreFocus.restart()
    }
    SystemMenu {
        id:networkPopup;objectName:"networkPopup";topic:"network"
        parent:bar.contentItem;width:Math.min(740,bar.width-24);x:bar.width-width-12;y:bar.barSize+6
        heightLimit:Math.max(100,bar.screen.height-bar.barSize-24)
        colors:bar.colors;controller:panelData;translate:bar.t
        onGeometryUpdated:Qt.callLater(bar.mask)
        onOpened:restoreFocus.stop()
        onClosed:restoreFocus.restart()
    }
    SystemMenu {
        id:audioPopup;objectName:"audioPopup";topic:"audio"
        parent:bar.contentItem;width:Math.min(740,bar.width-24);x:bar.width-width-12;y:bar.barSize+6
        heightLimit:Math.max(100,bar.screen.height-bar.barSize-24)
        colors:bar.colors;controller:panelData;translate:bar.t
        onGeometryUpdated:Qt.callLater(bar.mask)
        onOpened:restoreFocus.stop()
        onClosed:restoreFocus.restart()
        onLaunchStudio:panelData.launch("app","meetings")
    }
    BarPopup {
        id:systemPopup;objectName:"systemPopup";x:bar.width-width-12
        ColumnLayout {
            width:parent.width
            spacing:12
            Label {text:bar.uiLocale.toString(new Date(),"dddd, d. MMMM");color:bar.colors.text;font.pixelSize:18;wrapMode:Text.Wrap;Layout.fillWidth:true}
            RowLayout {visible:typeof(bar.stateData.system?.brightness)==="number";Layout.fillWidth:true
                Label {text:bar.t("Helligkeit");color:bar.colors.text}
                ControlSlider {controller:panelData;action:"brightness";modelValue:bar.stateData.system?.brightness;Layout.fillWidth:true;Accessible.name:bar.t("Helligkeit")}

            }
            Label {visible:!!panelData.error;text:bar.t(panelData.error);textFormat:Text.PlainText;color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            BarButton {objectName:"networkMenuEntry";colors:bar.colors;text:bar.t("Netzwerk");glyph:"network-wireless";Layout.fillWidth:true;onClicked:{systemPopup.close();audioPopup.close();networkPopup.open()}}
            BarButton {objectName:"audioMenuEntry";colors:bar.colors;text:bar.t("Audio");glyph:"audio-card";Layout.fillWidth:true;onClicked:{systemPopup.close();networkPopup.close();audioPopup.open()}}
            BarButton {colors:bar.colors;text:bar.t("Lumen System");glyph:"qrc:/lumen/icons/lumen-system.svg";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("hardware")}}
            BarButton {colors:bar.colors;text:bar.t("Einstellungen");glyph:"settings-configure";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.launch("settings")}}
            BarButton {colors:bar.colors;text:bar.t("Bildschirm sperren");glyph:"system-lock-screen";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("lock")}}
        }
    }
    BarPopup {
        id:overflow;x:Math.min(bar.width-width-12,Math.max(12,overflowButton.mapToItem(bar.contentItem,0,0).x))
        ColumnLayout {width:parent.width;spacing:2
            Repeater {model:appMenu.entries;BarButton {required property var modelData;required property int index;colors:bar.colors;text:modelData.label;enabled:modelData.enabled;objectName:"overflowMenu_"+index;visible:index>=bar.visibleMenus;Layout.fillWidth:true;onClicked:appMenu.show(index,this)}}
            BarButton {colors:bar.colors;text:bar.t("Fensteraktionen");glyph:"window";Layout.fillWidth:true;onClicked:{overflow.close();windowMenu.open()}}
        }
    }
    BarPopup {
        id:windowMenu;x:Math.min(bar.width-width-12,Math.max(12,appName.mapToItem(bar.contentItem,0,0).x))
        ColumnLayout {width:parent.width;spacing:2
            Label {text:windowState.appName||bar.t("Desktop");color:bar.colors.text;font.weight:Font.Medium;Layout.fillWidth:true}
            Repeater {model:[{label:bar.t("Maximieren / Wiederherstellen"),action:"maximize",icon:"window-maximize"},{label:bar.t("Minimieren"),action:"minimize",icon:"window-minimize"},{label:bar.t("Schließen"),action:"close",icon:"window-close"}]
                BarButton {required property var modelData;colors:bar.colors;text:modelData.label;glyph:modelData.icon;enabled:modelData.action==="close"?windowState.closable:modelData.action==="maximize"?windowState.maximizable:windowState.minimizable;Layout.fillWidth:true;onClicked:{windowState.action(modelData.action);windowMenu.close()}}
            }
        }
    }
    BarPopup {
        id:trayPopup;x:bar.width-width-12
        ColumnLayout {width:parent.width;spacing:4
            Label {text:bar.t("Hintergrund-Apps");color:bar.colors.text;font.pixelSize:18;Layout.fillWidth:true}
            Repeater {model:trayModel.items.length
                BarButton {required property int index;readonly property var entry:trayModel.items[index];objectName:"overflowTray_"+index;colors:bar.colors;text:entry?entry.title:"";glyph:entry?entry.icon:"";Layout.fillWidth:true;onClicked:trayModel.activate(entry.identity,this)
                    onActiveFocusChanged:if(activeFocus)Qt.callLater(()=>{
                        const viewport=trayPopup.contentItem.contentItem,top=mapToItem(viewport,0,0).y
                        const delta=top<8?top-8:top+height>viewport.height-8?top+height-viewport.height+8:0
                        viewport.contentY=Math.max(0,Math.min(Math.max(0,viewport.contentHeight-viewport.height),viewport.contentY+delta))
                    })
                    TapHandler {acceptedButtons:Qt.RightButton|Qt.MiddleButton;onTapped:(point,button)=>trayModel.activate(parent.entry.identity,parent,button===Qt.RightButton?3:2)}
                }
            }
        }
    }
    BarPopup {
        id:calendar;objectName:"calendarPopup";x:bar.width-width-12
        property date monthDate:new Date()
        onOpened:monthDate=new Date()
        ColumnLayout {width:parent.width;spacing:12
            RowLayout {Layout.fillWidth:true
                BarButton {colors:bar.colors;text:bar.t("Vorheriger Monat");glyph:"go-previous";iconOnly:true;onClicked:calendar.monthDate=new Date(calendar.monthDate.getFullYear(),calendar.monthDate.getMonth()-1,1)}
                Label {text:bar.uiLocale.toString(calendar.monthDate,"MMMM yyyy");color:bar.colors.text;font.pixelSize:18;horizontalAlignment:Text.AlignHCenter;Layout.fillWidth:true}
                BarButton {colors:bar.colors;text:bar.t("Nächster Monat");glyph:"go-next";iconOnly:true;onClicked:calendar.monthDate=new Date(calendar.monthDate.getFullYear(),calendar.monthDate.getMonth()+1,1)}
            }
            DayOfWeekRow {locale:bar.uiLocale;Layout.fillWidth:true;palette.text:bar.colors.muted}
            MonthGrid {id:monthGrid;month:calendar.monthDate.getMonth();year:calendar.monthDate.getFullYear();locale:bar.uiLocale;Layout.fillWidth:true;Layout.preferredHeight:230
                delegate:Rectangle {required property var model;color:model.today?bar.colors.accent:"transparent";radius:8;opacity:model.month===monthGrid.month?1:0.35
                    Text {anchors.centerIn:parent;text:parent.model.day;color:parent.model.today?bar.colors.onAccent:bar.colors.text;font.pixelSize:14}
                }
            }
            BarButton {colors:bar.colors;text:bar.t("Inbox öffnen");glyph:"view-calendar";Layout.fillWidth:true;visible:(bar.stateData.apps||[]).some(app=>app.id==="inbox");onClicked:{calendar.close();panelData.launch("app","inbox")}}
        }
    }
    Component.onCompleted:Qt.callLater(fit)
}
