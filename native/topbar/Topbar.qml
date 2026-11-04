import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import org.kde.kirigami as Kirigami
import Lumen.Topbar 1.0

Window {
    id: bar
    objectName: "lumenStandaloneTopbar"
    readonly property int barSize:56
    width:1280
    height:Math.max(barSize,launcher.visible?launcher.y+launcher.height+12:0,systemPopup.visible?systemPopup.y+systemPopup.height+12:0,overflow.visible?overflow.y+overflow.height+12:0,windowMenu.visible?windowMenu.y+windowMenu.height+12:0,trayPopup.visible?trayPopup.y+trayPopup.height+12:0,calendar.visible?calendar.y+calendar.height+12:0,askPopup.visible?askPopup.y+askPopup.height+12:0)
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
    property string clockText:Qt.formatTime(new Date(),"hh:mm")
    function t(source){return stateData.labels?.[source] || source}
    readonly property var uiLocale:Qt.locale(stateData.language==="de"?"de_CH":"en_US")
    function fit(){
        let total=0
        for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(b)total+=b.implicitWidth}
        const extras=networkButton.implicitWidth+volumeButton.implicitWidth+2
        const currentTray=(trayRow.visible?trayRow.implicitWidth+1:0)+(trayMore.visible?trayMore.implicitWidth+1:0)
        const compactCost=compactControls.implicitWidth+1
        const baseSystem=systemRow.implicitWidth-(showStatus?extras:0)-currentTray-(compactControls.visible?compactCost:0)
        const space=width-24-10-14-leftLayout.anchors.leftMargin-leftLayout.anchors.rightMargin-5*leftLayout.spacing-homeRow.implicitWidth-baseSystem
        const allTray=activeTray.length*41+(hasPassiveTray?trayMore.implicitWidth+1:0)
        const minimumTray=trayModel.items.length?41:0
        appLabelWidth=appName.visible?Math.max(40,Math.min(appName.naturalWidth,180,space-total-compactCost-minimumTray)):0
        const withApp=space-appLabelWidth-(!appName.visible?overflowButton.implicitWidth:0)
        showStatus=width>640 && total+extras+allTray<=withApp
        const controlsCost=showStatus?extras:compactCost
        const free=withApp-total-controlsCost
        shownTray=allTray<=free?activeTray.length:Math.max(0,Math.min(activeTray.length,Math.floor((free-trayMore.implicitWidth-1)/41)))
        const trayCost=shownTray*41+(shownTray<activeTray.length || hasPassiveTray?trayMore.implicitWidth+1:0)
        let available=withApp-controlsCost-trayCost
        showContext=total+120<=available
        visibleMenus=menuButtons.count
        if(total>available){let used=overflowButton.implicitWidth;visibleMenus=0;for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(!b || used+b.implicitWidth>available)break;used+=b.implicitWidth;visibleMenus++}}
        Qt.callLater(mask)
    }
    function mask(){
        let regions=[Qt.rect(leftIsland.x,0,leftIsland.width,barSize),Qt.rect(rightIsland.x,0,rightIsland.width,barSize)]
        for(const popup of [launcher,systemPopup,overflow,windowMenu,trayPopup,calendar,askPopup])if(popup.visible)regions.push(Qt.rect(popup.x,popup.y,popup.width,popup.height))
        panelData.inputMask(bar,regions)
    }
    function showLauncher(programs){launcher.programs=programs;launcher.open();panelData.refresh()}
    function updateMenu(){appMenu.setEndpoint(windowState.service,windowState.path)}
    function dismissIfInactive(){if(!bar.active && !appMenu.opened && !trayModel.opened){launcher.close();systemPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close();trayModel.close()}}
    onHeightChanged:Qt.callLater(mask)
    onActiveChanged:if(active)focusLoss.stop();else focusLoss.restart()
    Timer {id:focusLoss;interval:80;onTriggered:bar.dismissIfInactive()}
    Timer {id:restoreFocus;interval:100;onTriggered:if(bar.active && !inlineComposer.editing && !appMenu.opened && !trayModel.opened && ![launcher,systemPopup,overflow,windowMenu,trayPopup,calendar,askPopup].some(p=>p.visible))windowState.action("activate")}
    onWidthChanged:Qt.callLater(fit)
    onVisibleChanged:if(visible)Qt.callLater(fit)
    Timer {interval:1000;running:true;repeat:true;onTriggered:bar.clockText=Qt.formatTime(new Date(),"hh:mm")}
    WindowState {
        id:windowState
        objectName:"activeWindowState"
        screenGeometry:Qt.rect(bar.screen.virtualX,bar.screen.virtualY,bar.screen.width,bar.screen.height)
        holdActiveWindow:appMenu.opened || trayModel.opened || launcher.opened || systemPopup.opened || overflow.opened || windowMenu.opened || trayPopup.opened || calendar.opened
        onServiceChanged:Qt.callLater(bar.updateMenu)
        onPathChanged:Qt.callLater(bar.updateMenu)
        onFullScreenChanged:if(fullScreen){appMenu.close();trayModel.close();launcher.close();systemPopup.close();overflow.close();windowMenu.close();trayPopup.close();calendar.close();askPopup.close()}
    }
    AppMenu {id:appMenu;objectName:"applicationMenus";onEntriesChanged:Qt.callLater(bar.fit)}
    Connections {target:appMenu;function onOpenedChanged(){if(appMenu.opened)restoreFocus.stop();else{overflow.close();restoreFocus.restart()}Qt.callLater(bar.dismissIfInactive)}}
    Connections {target:trayModel;function onChanged(){Qt.callLater(bar.fit)}function onOpenedChanged(){if(trayModel.opened)restoreFocus.stop();else restoreFocus.restart();Qt.callLater(bar.dismissIfInactive)}}
    Connections {target:panelData;function onChanged(){Qt.callLater(bar.fit)}function onShowAppsRequested(name){if(name===bar.screen.name){bar.showLauncher(true)}}}
    Rectangle {
        id:leftIsland;objectName:"leftIsland"
        x:12;y:-18;height:bar.barSize+18
        width:Math.max(0,rightIsland.x-x-10)
        radius:18;color:bar.colors.window;border.color:bar.colors.border
        RowLayout {
            id:leftLayout
            anchors.fill:parent;anchors.topMargin:18;anchors.leftMargin:7;anchors.rightMargin:7;spacing:2
            Row {
                id:homeRow;spacing:2
                BarButton {objectName:"startButton";colors:bar.colors;text:bar.t("Start");glyph:"view-grid";iconOnly:bar.width<1100;onClicked:bar.showLauncher(true)}
                BarButton {id:homeLauncher;objectName:"launcherButton";colors:bar.colors;text:"Lumen";glyph:"qrc:/lumen/icons/lumen-mark.svg";iconOnly:bar.width<560;font.pixelSize:16;font.weight:Font.Medium;onClicked:bar.showLauncher(false)}
                Rectangle {width:1;height:22;color:bar.colors.border;anchors.verticalCenter:parent.verticalCenter}
                BarButton {colors:bar.colors;text:bar.t("Dateien");glyph:"folder";iconOnly:bar.width<720;onClicked:panelData.launch("files")}
            }
            BarButton {id:appName;onNaturalWidthChanged:Qt.callLater(bar.fit);iconOnly:bar.appLabelWidth<=41;colors:bar.colors;text:windowState.appName||bar.t("Desktop");glyph:"application-menu";font.pixelSize:14;onClicked:windowMenu.open();visible:bar.width>=560;Layout.minimumWidth:0;Layout.preferredWidth:bar.appLabelWidth;Layout.maximumWidth:180}
            Row {
                spacing:0
                Repeater {
                    id:menuButtons;model:appMenu.entries
                    BarButton {required property var modelData;required property int index;objectName:"applicationMenu_"+index;colors:bar.colors;text:modelData.label;enabled:modelData.enabled;font.pixelSize:14;visible:index<bar.visibleMenus;onClicked:appMenu.show(index,this);onImplicitWidthChanged:Qt.callLater(bar.fit)}
                    onCountChanged:Qt.callLater(bar.fit)
                }
                BarButton {id:overflowButton;objectName:"menuOverflowButton";colors:bar.colors;text:bar.t("Weitere App-Menüs");glyph:"overflow-menu";iconOnly:true;visible:bar.visibleMenus<menuButtons.count || !appName.visible;onClicked:menuButtons.count?overflow.open():windowMenu.open()}
            }
            Item {Layout.fillWidth:true;Layout.minimumWidth:0}
            Text {visible:bar.showContext && !!windowState.title;text:windowState.title;color:bar.colors.muted;font.pixelSize:12;elide:Text.ElideRight;textFormat:Text.PlainText;Layout.fillWidth:true;Layout.maximumWidth:300;Layout.minimumWidth:0}
            BarButton {colors:bar.colors;text:windowState.appName.includes("Reader")?bar.t("In Lumen besprechen"):bar.t("Seite merken …");glyph:"bookmark-new";iconOnly:true;visible:bar.showContext && bar.contextAvailable;onClicked:panelData.context(windowState.appName,windowState.title,windowState.pid)}
        }
    }
    Rectangle {
        id:rightIsland;x:bar.width-width-12;y:-18;height:bar.barSize+18;width:systemRow.implicitWidth+14
        radius:18;color:bar.colors.window;border.color:bar.colors.border
        Row {
            id:systemRow;anchors.top:parent.top;anchors.topMargin:18+(bar.barSize-implicitHeight)/2;anchors.left:parent.left;anchors.leftMargin:7;spacing:1
            Row {
                id:trayRow;spacing:1;visible:bar.shownTray>0
                Repeater {model:bar.activeTray.length
                    BarButton {required property int index;readonly property var entry:bar.activeTray[index];objectName:"trayItem_"+index;colors:bar.colors;text:entry?entry.title:"";glyph:entry?entry.icon:"";iconOnly:true;visible:index<bar.shownTray;onClicked:trayModel.activate(entry.identity,this)
                        TapHandler {acceptedButtons:Qt.RightButton|Qt.MiddleButton;onTapped:(point,button)=>trayModel.activate(parent.entry.identity,parent,button===Qt.RightButton?3:2)}
                    }
                }
            }
            BarButton {id:trayMore;objectName:"trayMoreButton";colors:bar.colors;text:bar.t("Hintergrund-Apps");glyph:"arrow-down";iconOnly:true;visible:bar.shownTray<bar.activeTray.length || bar.hasPassiveTray;onClicked:trayPopup.open()}
            AskComposer {id:inlineComposer;objectName:"inlineComposer";onEditingChanged:if(editing)restoreFocus.stop();visible:bar.width>=1100;width:Math.min(440,Math.max(260,(bar.width-1000)*0.35+220));colors:bar.colors;translate:bar.t;controller:panelData}
            BarButton {objectName:"askButton";colors:bar.colors;text:bar.t("Lumen fragen oder suchen");glyph:"search";iconOnly:true;visible:bar.width<1100;onClicked:{askPopup.open();popupComposer.focusInput()}}
            BarButton {objectName:"compactDictateButton";colors:bar.colors;text:bar.t("Mit Lumen sprechen");glyph:"microphone-sensitivity-high";iconOnly:true;visible:bar.width<1100;onClicked:panelData.launch("voice")}
            BarButton {colors:bar.colors;text:bar.t("Übertragungen")+(bar.stateData.operations?.transfer?" · "+bar.stateData.operations.transfer.count:"");glyph:"folder-upload";iconOnly:true;visible:!!bar.stateData.operations?.transfer;onClicked:panelData.launch("transfer",bar.stateData.operations.transfer.id)}
            BarButton {colors:bar.colors;text:bar.t("Aufnahme in Audio Studio");glyph:"media-record";iconOnly:true;visible:!!bar.stateData.operations?.audio;onClicked:panelData.launch("app","meetings")}
            BarButton {objectName:"systemErrorButton";colors:bar.colors;text:bar.t(panelData.error);glyph:"dialog-warning";iconOnly:true;visible:!!panelData.error;onClicked:systemPopup.open()}
            BarButton {id:networkButton;colors:bar.colors;text:bar.t("Netzwerk");glyph:"network-wireless";iconOnly:true;visible:bar.showStatus;onClicked:{systemPopup.open();panelData.refresh()}}
            BarButton {id:volumeButton;objectName:"systemControlsButton";colors:bar.colors;text:bar.t("Lautstärke");glyph:bar.stateData.system?.muted?"audio-volume-muted":"audio-volume-high";iconOnly:true;visible:bar.showStatus;onClicked:{systemPopup.open();panelData.refresh()}}
            BarButton {colors:bar.colors;text:bar.t("Mitteilungen")+(bar.stateData.unread>0?" · "+bar.stateData.unread:"");glyph:bar.stateData.unread>0?"notifications-new":"notifications";iconOnly:true;onClicked:panelData.launch("notifications")}
            BarButton {colors:bar.colors;objectName:"clockButton";text:bar.clockText;visible:bar.width>460;font.pixelSize:13;onClicked:calendar.open()}
            BarButton {id:compactControls;objectName:"compactControlsButton";colors:bar.colors;text:bar.t("Systemsteuerung");glyph:"settings-configure";iconOnly:true;visible:!bar.showStatus;onClicked:{systemPopup.open();panelData.refresh()}}
            onImplicitWidthChanged:Qt.callLater(bar.fit)
        }
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
                BarButton {colors:bar.colors;text:bar.t("Programme");checkable:true;checked:launcher.programs;highlighted:launcher.programs;Layout.fillWidth:true;onClicked:launcher.programs=true}
            }
            Loader {id:programLoader;Layout.fillWidth:true;active:launcher.programs;visible:active;onLoaded:item.focusSearch()
                sourceComponent:ProgramList {colors:bar.colors;translate:bar.t;onLaunched:launcher.close()}
            }
            GridLayout {
                visible:!launcher.programs;columns:launcher.width>=440?4:3;columnSpacing:4;rowSpacing:6;Layout.fillWidth:true
                Repeater {
                    model:bar.stateData.apps||[]
                    BarButton {required property var modelData;objectName:"openApp_"+modelData.id;colors:bar.colors;text:modelData.label;Layout.fillWidth:true;Layout.preferredWidth:0;Layout.preferredHeight:Math.max(88,contentItem.implicitHeight+20);Accessible.name:modelData.title;
                        contentItem:Column {spacing:6;Kirigami.Icon {source:"qrc:/lumen/icons/"+(modelData.id==="lumen"?"lumen":"lumen-"+modelData.id)+".svg";width:40;height:40;anchors.horizontalCenter:parent.horizontalCenter}Text {text:modelData.label;color:bar.colors.text;font.pixelSize:12;horizontalAlignment:Text.AlignHCenter;width:parent.width;wrapMode:Text.WordWrap}}
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
    BarPopup {
        id:askPopup;x:bar.width-width-12
        ColumnLayout {width:parent.width;spacing:12
            Label {text:bar.t("Neue Frage an Lumen");color:bar.colors.text;font.pixelSize:19;Layout.fillWidth:true}
            AskComposer {id:popupComposer;objectName:"popupComposer";Layout.fillWidth:true;colors:bar.colors;translate:bar.t;controller:panelData;onSent:askPopup.close()}
            Label {visible:!!panelData.error;text:bar.t(panelData.error);color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            BarButton {colors:bar.colors;text:bar.t("Lumen fragen oder suchen");glyph:"search";Layout.fillWidth:true;onClicked:{askPopup.close();panelData.launch("search")}}
        }
    }
    BarPopup {
        id:systemPopup;x:bar.width-width-12
        ColumnLayout {
            width:parent.width
            spacing:12
            Label {text:bar.uiLocale.toString(new Date(),"dddd, d. MMMM");color:bar.colors.text;font.pixelSize:18;wrapMode:Text.Wrap;Layout.fillWidth:true}
            Label {text:bar.t("Netzwerk")+" · "+(bar.stateData.system?.network||bar.t("Nicht verfügbar"));color:bar.colors.muted;Layout.fillWidth:true}
            RowLayout {Layout.fillWidth:true
                BarButton {objectName:"muteButton";enabled:typeof(bar.stateData.system?.volume)==="number" && !panelData.controlBusy;colors:bar.colors;text:bar.t("Stummschalten");glyph:bar.stateData.system?.muted?"audio-volume-muted":"audio-volume-high";iconOnly:true;onClicked:panelData.control("mute")}
                ControlSlider {id:volume;objectName:"volumeSlider";controller:panelData;action:"volume";modelValue:bar.stateData.system?.volume;Layout.fillWidth:true;Accessible.name:bar.t("Lautstärke")}
                Label {text:volume.available?Math.round(volume.pending?volume.desired:volume.modelValue)+" %"+(volume.pending?" …":""):bar.t("Nicht verfügbar");color:bar.colors.text;Layout.preferredWidth:90;font.pixelSize:12}

            }
            RowLayout {visible:typeof(bar.stateData.system?.brightness)==="number";Layout.fillWidth:true
                Label {text:bar.t("Helligkeit");color:bar.colors.text}
                ControlSlider {controller:panelData;action:"brightness";modelValue:bar.stateData.system?.brightness;Layout.fillWidth:true;Accessible.name:bar.t("Helligkeit")}

            }
            Label {visible:!!panelData.error;text:bar.t(panelData.error);textFormat:Text.PlainText;color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            BarButton {colors:bar.colors;text:bar.t("Netzwerkeinstellungen");glyph:"network-wireless";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("network")}}
            BarButton {colors:bar.colors;text:bar.t("Audioeinstellungen");glyph:"audio-card";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("audio")}}
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
