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
    property bool conversationOpen:false
    property bool conversationLoaded:false
    property string conversationQuery:""
    property bool detachingConversation:false
    property bool yieldingConversation:false
    property bool draggingConversation:false
    property bool conversationMoveReady:false
    readonly property int conversationHeight:Math.max(260,Math.min(620,bar.screen.height-bar.barSize-24))
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
        property string error:""
    }
    width:1280
    height:Math.max(conversationOpen?barSize+conversationHeight:barSize,quickMenu.visible?quickMenu.y+quickMenu.height+12:0,launcher.visible?launcher.y+launcher.height+12:0,systemPopup.visible?systemPopup.y+systemPopup.height+12:0,networkPopup.visible?networkPopup.y+networkPopup.height+12:0,audioPopup.visible?audioPopup.y+audioPopup.height+12:0,overflow.visible?overflow.y+overflow.height+12:0,windowMenu.visible?windowMenu.y+windowMenu.height+12:0,trayPopup.visible?trayPopup.y+trayPopup.height+12:0,calendar.visible?calendar.y+calendar.height+12:0,askPopup.visible?askPopup.y+askPopup.height+12:0,contextDrawer.visible?contextDrawer.y+contextDrawer.height+12:0,activityPopup.visible?activityPopup.y+activityPopup.height+12:0)
    color:"transparent"
    property string quickTopic:"notifications"
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
        return {section:"focus",text:t("Auf einen Blick"),icon:"emblem-ok-symbolic"}
    }
    Notifications.Settings {id:notificationSettings;live:true}
    function showActivity(page){quickMenu.close();if(conversationOpen)closeConversation();activityPopup.page=page;activityPopup.section=statusSection;activityPopup.open()}
    function t(source){return stateData.labels?.[source] || source}
    function openConversation(){
        focusLoss.stop();restoreFocus.stop();quickMenu.close();launcher.close();askPopup.close();contextDrawer.close();activityPopup.close()
        conversationPane.parent=bar.contentItem
        conversationOpen=true;panelData.conversation.call("width",[Math.min(712,bar.width-72)])
        if(questionState.draft)panelData.conversation.call("draft",[questionState.draft,questionState.note])
        mask();bar.requestActivate();conversationWindow.hide();focusLoss.stop()
        Qt.callLater(conversationPane.focusInput)
    }
    function closeConversation(){conversationOpen=false;conversationWindow.hide();panelData.conversation.call("hidden");Qt.callLater(mask);restoreFocus.restart()}
    function toggleConversation(){conversationOpen?closeConversation():openConversation()}
    function conversationSent(){askPopup.close();contextDrawer.close();if(!conversationWindow.visible)openConversation();conversationPane.following=true;Qt.callLater(conversationPane.latest)}
    function detachConversation(dragging){
        conversationOpen=false;conversationPane.parent=conversationWindow.contentItem
        conversationWindow.width=Math.min(900,bar.screen.width-48);conversationWindow.height=Math.min(760,bar.screen.height-80)
        conversationWindow.x=bar.screen.virtualX+(bar.width-conversationWindow.width)/2;conversationWindow.y=bar.screen.virtualY+bar.barSize+24
        conversationMoveReady=false;draggingConversation=dragging;detachingConversation=true;mask();bar.update()
    }
    onFrameSwapped:if(detachingConversation){
        detachingConversation=false;conversationWindow.activateWhenMapped=true;conversationWindow.focusPending=true;conversationWindow.show()
    }
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
        let regions=classic?[Qt.rect(12,12,width-24,barSize-24+(conversationOpen?conversationHeight:0))]:[Qt.rect(0,0,width,barSize+(conversationOpen?conversationHeight:0))]
        let popupOpen=false
        for(const popup of [quickMenu,launcher,systemPopup,networkPopup,audioPopup,overflow,windowMenu,trayPopup,calendar,askPopup,contextDrawer,activityPopup])if(popup.visible){regions.push(Qt.rect(popup.x,popup.y,popup.width,popup.height));popupOpen=true}
        yieldingConversation=detachingConversation||(conversationWindow.visible&&!popupOpen&&!conversationOpen)
        panelData.inputMask(bar,regions,popupOpen||conversationOpen)
    }
    onBarSizeChanged:Qt.callLater(mask)
    onLayoutChanged:if(ready){quickMenu.close();launcher.close();systemPopup.close();networkPopup.close();audioPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();contextDrawer.close();activityPopup.close();Qt.callLater(()=>{fit();if(layout==="context" && inlineComposer.visible && inlineComposer.editing)contextDrawer.open()})}
    function showLauncher(lumenApps){
        if(launcher.opened && startMenu.lumenOnly===lumenApps){launcher.close();return}
        if(conversationOpen)closeConversation()
        for(const popup of [quickMenu,systemPopup,networkPopup,audioPopup,activityPopup,contextDrawer,askPopup])popup.close()
        focusLoss.stop();restoreFocus.stop()
        startMenu.reset(lumenApps)
        if(launcher.opened){launcher.scrollToTop();startMenu.focusSearch()}
        else launcher.open()
        panelData.refresh();panelData.inspect("recent")
    }
    function quick(topic){
        const same=quickMenu.visible && quickTopic===topic
        if(same){quickMenu.close();return}
        if(conversationOpen)closeConversation()
        for(const popup of [launcher,systemPopup,networkPopup,audioPopup,activityPopup,contextDrawer,askPopup])popup.close()
        focusLoss.stop();restoreFocus.stop()
        quickTopic=topic
        if(topic==="audio" || topic==="network")panelData.inspect(topic)
        quickMenu.open()
    }
    function drillQuick(key){
        const topic=quickTopic
        quickMenu.close()
        if(topic==="notifications"){
            if(key)panelData.noticeCommand("open",key)
            else panelData.launch("notifications")
        }else if(topic==="settings"){
            if(key==="preferences")panelData.launch("settings")
            else if(key==="network" || key==="audio")openDeviceMenu(key)
            else {panelData.refresh();systemPopup.open()}
        }else openDeviceMenu(topic,Number(key)||0)
    }
    function openDeviceMenu(topic,section=0){
        systemPopup.close()
        const full=topic==="network"?networkPopup:audioPopup
        full.section=section;full.open()
    }
    function updateMenu(){appMenu.setEndpoint(windowState.service,windowState.path)}
    function dismissIfInactive(){if(!bar.active && !appMenu.opened && !trayModel.opened && !startMenu.menuOpened && !conversationPane.dialogVisible){quickMenu.close();launcher.close();systemPopup.close();networkPopup.close();audioPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();contextDrawer.close();activityPopup.close();trayModel.close();if(conversationOpen)closeConversation()}}
    onHeightChanged:Qt.callLater(mask)
    onConversationOpenChanged:Qt.callLater(mask)
    onActiveChanged:if(active)focusLoss.stop();else focusLoss.restart()
    Timer {id:focusLoss;interval:80;onTriggered:bar.dismissIfInactive()}
    // A delayed activation can steal focus from a subsequently reopened popup.
    Timer {id:restoreFocus;interval:0;onTriggered:if(bar.active && !bar.conversationOpen && !bar.detachingConversation && !inlineComposer.editing && !appMenu.opened && !trayModel.opened && ![quickMenu,launcher,systemPopup,networkPopup,audioPopup,overflow,windowMenu,trayPopup,calendar,askPopup,contextDrawer,activityPopup].some(p=>p.visible))windowState.action("activate")}
    onWidthChanged:Qt.callLater(fit)
    onVisibleChanged:if(visible)Qt.callLater(fit)
    Timer {interval:1000;running:true;repeat:true;onTriggered:{bar.now=Date.now();bar.clockText=Qt.formatTime(new Date(),"hh:mm")}}
    WindowState {
        id:windowState
        objectName:"activeWindowState"
        screenGeometry:Qt.rect(bar.screen.virtualX,bar.screen.virtualY,bar.screen.width,bar.screen.height)
        holdActiveWindow:bar.conversationOpen || bar.detachingConversation || !!bar.notePendingAction || inlineComposer.editing || appMenu.opened || trayModel.opened || quickMenu.opened || launcher.opened || systemPopup.opened || networkPopup.opened || audioPopup.opened || overflow.opened || windowMenu.opened || trayPopup.opened || calendar.opened || askPopup.opened || contextDrawer.opened || activityPopup.opened
        onServiceChanged:Qt.callLater(bar.updateMenu)
        onPathChanged:Qt.callLater(bar.updateMenu)
        onFullScreenChanged:if(fullScreen){appMenu.close();trayModel.close();quickMenu.close();launcher.close();systemPopup.close();networkPopup.close();audioPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();contextDrawer.close();activityPopup.close()}
    }
    AppMenu {id:appMenu;objectName:"applicationMenus";onEntriesChanged:Qt.callLater(bar.fit)}
    Connections {target:appMenu;function onOpenedChanged(){if(appMenu.opened)restoreFocus.stop();else{overflow.close();restoreFocus.restart()}Qt.callLater(bar.dismissIfInactive)}}
    Connections {target:trayModel;function onChanged(){Qt.callLater(bar.fit)}function onOpenedChanged(){if(trayModel.opened)restoreFocus.stop();else restoreFocus.restart();Qt.callLater(bar.dismissIfInactive)}}
    Connections {target:panelData;function onChanged(){bar.now=Date.now();Qt.callLater(bar.fit)}function onShowAppsRequested(name){if(name===bar.screen.name){bar.showLauncher(false)}}
        function onNoteAttached(action,note){if(action===bar.notePendingAction){questionState.note=note;bar.notePendingAction=""}}
        function onControlFailed(action){if(action===bar.notePendingAction)bar.notePendingAction=""}}
    Rectangle {
        visible:!bar.classic;width:bar.width;height:bar.barSize+(bar.conversationOpen?bar.conversationHeight:0);color:bar.colors.window
        Rectangle {anchors.bottom:parent.bottom;width:parent.width;height:1;color:bar.colors.border}
        Rectangle {visible:bar.deck;x:16;y:64;width:parent.width-32;height:1;color:bar.colors.border}
    }
    Rectangle {
        id:leftIsland;objectName:"leftIsland";visible:bar.classic
        x:12;y:12;height:bar.conversationOpen?bar.barSize-24+bar.conversationHeight:activityPopup.visible?activityPopup.y+activityPopup.height-12:bar.barSize-24;width:bar.width-24
        radius:(bar.colors.radius||10)+7;bottomLeftRadius:launcher.visible?0:radius;bottomRightRadius:quickMenu.visible?0:radius;color:bar.colors.window;border.color:bar.colors.border
    }
    Row {
        id:homeRow;x:bar.classic?24:16;y:(bar.classic?40:bar.deck?34:bar.barSize/2)-height/2
        spacing:bar.classic?2:7
        onWidthChanged:Qt.callLater(bar.fit)
        BarButton {objectName:"programsButton";key:!bar.classic;colors:bar.colors;text:bar.t("Startmenü");glyph:"applications-all-symbolic";monochrome:true;iconOnly:true;current:launcher.visible && !startMenu.lumenOnly;onClicked:bar.showLauncher(false)}
        BarButton {id:homeLauncher;objectName:"launcherButton";key:!bar.classic;colors:bar.colors;text:bar.classic?"Lumen":"Lumen ⌄";glyph:bar.classic?"qrc:/lumen/icons/lumen-mark.svg":"";symbol:bar.classic?"":"mark";iconOnly:bar.classic || bar.width<560;font.weight:Font.Medium;current:launcher.visible && startMenu.lumenOnly;onClicked:bar.showLauncher(true)}
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
        onInputRequested:if(conversationWindow.visible)bar.openConversation()
        visible:bar.expandedComposer;width:bar.classic?Math.max(0,activityButton.x-(bar.twoRows?24:appRow.x+appRow.width+12)-60):266
        x:bar.classic?(bar.twoRows?24:appRow.x+appRow.width+12):bar.deck?bar.width-310-16:systemRow.x-310-8;y:bar.classic?(bar.twoRows?82:40)-height/2:bar.deck?72:(bar.barSize-height)/2
        colors:bar.colors;translate:bar.t;controller:panelData;keyStyle:!bar.classic
        request:questionState;onInspectAttachment:contextDrawer.open();onSent:bar.conversationSent();onVoiceRequested:bar.openConversation()
    }
    BarButton {objectName:"conversationToggle";visible:inlineComposer.visible;colors:bar.colors;glyph:bar.conversationOpen?"arrow-up":"arrow-down";text:bar.t(bar.conversationOpen?"Gespräch einklappen":"Gespräch aufklappen");iconOnly:true;x:inlineComposer.x+inlineComposer.width+4;y:inlineComposer.y;onClicked:bar.toggleConversation()}
    ConversationState {id:conversationState;model:panelData.conversation;translate:bar.t;colors:bar.colors}
    Connections {target:panelData.conversation;function onChanged(){
        const incoming=conversationState.data.query||""
        if(incoming!==bar.conversationQuery){
            bar.conversationQuery=incoming
            if(!questionState.pending&&incoming&&conversationState.data.voiceActive)questionState.draft=incoming
        }
        if(!bar.conversationLoaded&&Object.keys(conversationState.data).length){
            bar.conversationLoaded=true
            if(!questionState.pending&&!questionState.draft&&conversationState.data.query)questionState.draft=conversationState.data.query
            if(!questionState.pending&&!questionState.note.reference&&conversationState.data.note?.reference)questionState.note=conversationState.data.note
        }
    }}
    Connections {target:questionState;function onPendingChanged(){if(questionState.pending&&!conversationWindow.visible)bar.openConversation()}}
    Connections {target:questionState;function onDraftChanged(){draftSync.restart()}function onNoteChanged(){draftSync.restart()}}
    Timer {id:draftSync;interval:250;onTriggered:if(!questionState.pending)panelData.conversation.call("draft",[questionState.draft,questionState.note])}
    ConversationPane {
        id:conversationPane;objectName:"topbarConversation";visible:bar.conversationOpen||conversationWindow.visible
        x:detached?0:12;y:detached?0:bar.barSize-12
        width:detached?conversationWindow.width:bar.width-24;height:detached?conversationWindow.height:bar.conversationHeight
        controller:conversationState;request:questionState;host:panelData;colors:bar.colors;translate:bar.t
        detached:parent===conversationWindow.contentItem
        onDetachRequested:dragging=>bar.detachConversation(dragging)
        onCollapseRequested:bar.closeConversation()
        onReattachRequested:bar.openConversation()
    }
    Window {
        id:conversationWindow;objectName:"detachedConversation";visible:false;transientParent:null
        property bool activateWhenMapped:false
        property bool focusPending:false
        onVisibleChanged:{if(!visible)focusPending=false;Qt.callLater(bar.mask)}
        function beginDrag(){if(active&&!activateWhenMapped&&bar.draggingConversation){bar.draggingConversation=false;Qt.callLater(()=>{bar.conversationMoveReady=conversationWindow.startSystemMove()})}}
        onActiveChanged:if(active){focusPending=false;beginDrag()}
        screen:bar.screen
        title:"Lumen";flags:Qt.Window|Qt.FramelessWindowHint;width:900;height:700;minimumWidth:440;minimumHeight:400;color:"transparent"
        Rectangle {anchors.fill:parent;z:-1;color:bar.colors.window;radius:bar.colors.radius||12;border.color:bar.colors.border}
        Repeater {
            model:[Qt.LeftEdge,Qt.RightEdge,Qt.TopEdge,Qt.BottomEdge,Qt.TopEdge|Qt.LeftEdge,Qt.TopEdge|Qt.RightEdge,Qt.BottomEdge|Qt.LeftEdge,Qt.BottomEdge|Qt.RightEdge]
            MouseArea {
                required property int modelData
                readonly property bool horizontal:!!(modelData&(Qt.LeftEdge|Qt.RightEdge))
                readonly property bool vertical:!!(modelData&(Qt.TopEdge|Qt.BottomEdge))
                z:2;enabled:conversationWindow.visibility!==Window.Maximized
                x:modelData&Qt.RightEdge?conversationWindow.width-8:0;y:modelData&Qt.BottomEdge?conversationWindow.height-8:0
                width:horizontal?8:conversationWindow.width;height:vertical?8:conversationWindow.height
                cursorShape:horizontal&&vertical?(modelData===(Qt.TopEdge|Qt.LeftEdge)||modelData===(Qt.BottomEdge|Qt.RightEdge)?Qt.SizeFDiagCursor:Qt.SizeBDiagCursor):horizontal?Qt.SizeHorCursor:Qt.SizeVerCursor
                onPressed:conversationWindow.startSystemResize(modelData)
            }
        }
        onFrameSwapped:if(activateWhenMapped){
            activateWhenMapped=false
            Qt.callLater(()=>{conversationWindow.requestActivate();windowState.activateProcess(panelData.processId);conversationPane.focusInput();conversationWindow.beginDrag()})
        }
        Timer {interval:1000;running:conversationWindow.focusPending;onTriggered:conversationWindow.focusPending=false}
        onClosing:event=>{event.accepted=false;bar.closeConversation()}
    }
    Connections {target:windowState.windows;function onObjectAdded(){if(conversationWindow.focusPending)Qt.callLater(()=>windowState.activateProcess(panelData.processId))}}
    Shortcut {sequence:"Escape";enabled:bar.conversationOpen||conversationWindow.active;onActivated:bar.closeConversation()}
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
            BarButton {key:!bar.classic;objectName:"compactDictateButton";colors:bar.colors;text:bar.t("Mit Lumen sprechen");glyph:"microphone-sensitivity-high";iconOnly:true;visible:!bar.expandedComposer;onClicked:{bar.openConversation();panelData.conversation.call("voice")}}
            BarButton {colors:bar.colors;text:bar.t("Übertragungen")+(bar.stateData.operations?.transfer?" · "+bar.stateData.operations.transfer.count:"");glyph:"folder-upload";iconOnly:true;visible:!bar.classic && !!bar.stateData.operations?.transfer;onClicked:panelData.launch("transfer",bar.stateData.operations.transfer.id)}
            BarButton {colors:bar.colors;text:bar.t("Aufnahme in Audio Studio");glyph:"media-record";iconOnly:true;visible:!bar.classic && !!bar.stateData.operations?.audio;onClicked:panelData.launch("app","meetings")}
            BarButton {key:!bar.classic;objectName:"systemErrorButton";colors:bar.colors;text:bar.t(panelData.error);glyph:"dialog-warning";iconOnly:true;visible:!!panelData.error;onClicked:systemPopup.open()}
            BarButton {id:networkButton;objectName:"networkButton";key:!bar.classic;colors:bar.colors;text:bar.t("Netzwerk");glyph:"network-wireless";iconOnly:true;visible:bar.showStatus;current:quickMenu.visible && bar.quickTopic==="network";onClicked:bar.quick("network")}
            BarButton {id:volumeButton;key:!bar.classic;objectName:"systemControlsButton";colors:bar.colors;text:bar.t("Audio");glyph:bar.stateData.system?.muted?"audio-volume-muted":"audio-volume-high";iconOnly:true;visible:bar.showStatus;current:quickMenu.visible && bar.quickTopic==="audio";onClicked:bar.quick("audio")}
            BarButton {objectName:"notificationsButton";key:!bar.classic;colors:bar.colors;text:bar.t("Mitteilungen")+(bar.quiet?" · "+bar.t("Nicht stören"):bar.stateData.unread>0?" · "+bar.stateData.unread:"");glyph:bar.quiet?"notifications-disabled":bar.stateData.unread>0?"notifications-new":"notifications";iconOnly:true;current:quickMenu.visible && bar.quickTopic==="notifications";onClicked:bar.quick("notifications")
                Rectangle {anchors.right:parent.right;anchors.top:parent.top;anchors.rightMargin:4;anchors.topMargin:4;width:7;height:7;radius:4;color:bar.colors.accent
                    visible:!bar.quiet && (quickMenu.visible && bar.quickTopic==="notifications" && panelData.noticePreview.items?panelData.noticePreview.unread:bar.stateData.unread)>0}
            }
            BarButton {colors:bar.colors;objectName:"clockButton";text:bar.clockText;visible:bar.width>460;onClicked:calendar.open()}
            BarButton {id:compactControls;key:!bar.classic;objectName:"compactControlsButton";colors:bar.colors;text:bar.t("Systemsteuerung");glyph:"settings-configure";iconOnly:true;current:quickMenu.visible && bar.quickTopic==="settings";onClicked:bar.quick("settings")}
        onImplicitWidthChanged:Qt.callLater(bar.fit)
    }
    component BarPopup:Popup {
        id:barPopup
        property bool followFocus:false
        default property alias body:scroller.contentData
        parent:bar.contentItem
        popupType:Popup.Item
        focus:true
        padding:16;closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
        width:Math.min(380,bar.width-24);y:bar.barSize+6
        height:Math.min(implicitHeight,Math.max(100,bar.screen.height-bar.barSize-24))
        contentItem:ScrollView {id:scroller;clip:true;contentWidth:availableWidth;implicitHeight:contentHeight}
        function scrollToTop(){if(scroller.contentItem)scroller.contentItem.contentY=0}
        function revealFocus(){
            const focused=bar.activeFocusItem,viewport=scroller.contentItem
            if(!followFocus || !visible || !focused || !viewport)return
            let ancestor=focused.parent
            while(ancestor && ancestor!==viewport)ancestor=ancestor.parent
            if(!ancestor)return
            const top=focused.mapToItem(viewport,0,0).y
            const delta=top<8?top-8:top+focused.height>viewport.height-8?top+focused.height-viewport.height+8:0
            viewport.contentY=Math.max(0,Math.min(Math.max(0,viewport.contentHeight-viewport.height),viewport.contentY+delta))
        }
        Connections {target:bar;function onActiveFocusItemChanged(){if(barPopup.followFocus)Qt.callLater(barPopup.revealFocus)}}
        onVisibleChanged:Qt.callLater(bar.mask)
        onOpened:restoreFocus.stop()
        onClosed:{Qt.callLater(bar.mask);restoreFocus.restart()}
        background:Rectangle {color:bar.colors.window;radius:13;border.color:bar.colors.border}
    }
    component DockedPopup:BarPopup {
        followFocus:true
        y:bar.barSize-(bar.classic?13:1)
        background:Rectangle {
            color:bar.colors.window;radius:bar.colors.radius||10;topLeftRadius:0;topRightRadius:0;border.color:bar.colors.border
            Rectangle {x:1;y:0;width:parent.width-2;height:2;color:parent.color}
        }
    }
    DockedPopup {
        id:quickMenu;objectName:"quickMenu";padding:12
        width:Math.min(390,Math.max(1,bar.width-36));x:bar.width-width-12
        QuickMenu {width:parent.width;topic:bar.quickTopic;colors:bar.colors;controller:panelData;translate:bar.t;quiet:bar.quiet
            onDrill:key=>bar.drillQuick(key)
            onDismiss:quickMenu.close()
            onToggleQuiet:{notificationSettings.notificationsInhibitedUntil=bar.quiet?new Date(0):new Date(Date.now()+3600000);notificationSettings.save();bar.now=Date.now()}
        }
        readonly property bool watchingNotices:visible && bar.quickTopic==="notifications"
        onWatchingNoticesChanged:panelData.watchNotices(bar,watchingNotices)
        Timer {interval:5000;repeat:true;running:quickMenu.watchingNotices && !panelData.noticePreview.items;onTriggered:panelData.noticeCommand("preview")}
    }
    DockedPopup {
        id:launcher;objectName:"appsPopup";x:12;padding:0
        onOpened:{restoreFocus.stop();scrollToTop();Qt.callLater(startMenu.focusSearch)}
        width:Math.min(650,bar.width-24)
        StartMenu {id:startMenu;objectName:"startMenu";width:parent.width;colors:bar.colors;controller:panelData;translate:bar.t;active:launcher.opened
            onMenuOpenedChanged:if(!menuOpened)focusLoss.restart()
            onLaunched:launcher.close()
            onMoreRecent:{launcher.close();bar.showActivity("recent")}
            onSettingsRequested:bar.quick("settings")
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
            AskComposer {id:popupComposer;objectName:"popupComposer";Layout.fillWidth:true;colors:bar.colors;translate:bar.t;controller:panelData;request:questionState;onSent:bar.conversationSent();onVoiceRequested:bar.openConversation();onInspectAttachment:{}}
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
            BarButton {objectName:"networkMenuEntry";colors:bar.colors;text:bar.t("Netzwerk");glyph:"network-wireless";Layout.fillWidth:true;onClicked:bar.openDeviceMenu("network")}
            BarButton {objectName:"audioMenuEntry";colors:bar.colors;text:bar.t("Audio");glyph:"audio-card";Layout.fillWidth:true;onClicked:bar.openDeviceMenu("audio")}
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
        id:trayPopup;objectName:"trayPopup";x:bar.width-width-12
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
