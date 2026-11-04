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
    height:Math.max(barSize,launcher.visible?launcher.y+launcher.height+12:0,systemPopup.visible?systemPopup.y+systemPopup.height+12:0,overflow.visible?overflow.y+overflow.height+12:0,windowMenu.visible?windowMenu.y+windowMenu.height+12:0)
    color:"transparent"
    property bool ready:false
    visible:ready && !windowState.fullScreen
    flags:Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    property var stateData:panelData.snapshot
    readonly property var colors:stateData.palette
    property int visibleMenus:appMenu.entries.length
    property bool showContext:true
    property bool showStatus:true
    readonly property bool contextAvailable: ["Chromium","Google Chrome","Brave","Mozilla Firefox","Microsoft Edge","Vivaldi","Lumen Reader","Reader"].includes(windowState.appName)
    property string clockText:Qt.formatTime(new Date(),"hh:mm")
    function fit(){
        let total=0
        for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(b)total+=b.implicitWidth}
        const extras=networkButton.implicitWidth+volumeButton.implicitWidth+2
        const baseSystem=systemRow.implicitWidth-(showStatus?extras:0)
        let available=width-24-16-homeRow.implicitWidth-appName.implicitWidth-baseSystem-extras
        showStatus=total<=available
        if(!showStatus)available+=extras
        showContext=total+120<=available
        visibleMenus=menuButtons.count
        if(total>available){let used=overflowButton.implicitWidth;visibleMenus=0;for(let i=0;i<menuButtons.count;i++){const b=menuButtons.itemAt(i);if(!b || used+b.implicitWidth>available)break;used+=b.implicitWidth;visibleMenus++}}
        Qt.callLater(mask)
    }
    function mask(){
        let regions=[Qt.rect(leftIsland.x,0,leftIsland.width,barSize),Qt.rect(rightIsland.x,0,rightIsland.width,barSize)]
        for(const popup of [launcher,systemPopup,overflow,windowMenu])if(popup.visible)regions.push(Qt.rect(popup.x,popup.y,popup.width,popup.height))
        panelData.inputMask(bar,regions)
    }
    onHeightChanged:Qt.callLater(mask)
    onActiveChanged:if(!active){launcher.close();systemPopup.close();overflow.close();windowMenu.close()}
    onWidthChanged:Qt.callLater(fit)
    onVisibleChanged:if(visible)Qt.callLater(fit)
    Timer {interval:1000;running:true;repeat:true;onTriggered:bar.clockText=Qt.formatTime(new Date(),"hh:mm")}
    WindowState {
        id:windowState
        objectName:"activeWindowState"
        screenGeometry:Qt.rect(bar.screen.virtualX,bar.screen.virtualY,bar.screen.width,bar.screen.height)
        holdActiveWindow:appMenu.opened || launcher.opened || systemPopup.opened || overflow.opened || windowMenu.opened
        onServiceChanged:appMenu.setEndpoint(service,path)
        onPathChanged:appMenu.setEndpoint(service,path)
    }
    AppMenu {id:appMenu;objectName:"applicationMenus";onEntriesChanged:Qt.callLater(bar.fit)}
    Connections {target:panelData;function onChanged(){Qt.callLater(bar.fit)}function onShowAppsRequested(name){if(name===bar.screen.name){launcher.open();panelData.refresh()}}}
    Rectangle {
        id:leftIsland
        x:12;y:-18;height:bar.barSize+18
        width:Math.max(0,rightIsland.x-x-10)
        radius:18;color:bar.colors.window;border.color:bar.colors.border
        RowLayout {
            anchors.fill:parent;anchors.topMargin:18;anchors.leftMargin:7;anchors.rightMargin:7;spacing:2
            Row {
                id:homeRow;spacing:2
                BarButton {id:homeLauncher;objectName:"launcherButton";colors:bar.colors;text:"Lumen";glyph:"lumen";font.pixelSize:16;font.weight:Font.Medium;onClicked:{launcher.open();panelData.refresh()}}
                Rectangle {width:1;height:22;color:bar.colors.border;anchors.verticalCenter:parent.verticalCenter}
                BarButton {colors:bar.colors;text:qsTr("Dateien");glyph:"folder";iconOnly:bar.width<720;onClicked:panelData.launch("files")}
            }
            BarButton {id:appName;colors:bar.colors;text:windowState.appName||qsTr("Desktop");glyph:"application-menu";font.pixelSize:14;onClicked:windowMenu.open();Layout.maximumWidth:bar.width<600?44:180;iconOnly:bar.width<600}
            Row {
                spacing:0
                Repeater {
                    id:menuButtons;model:appMenu.entries
                    BarButton {required property var modelData;required property int index;objectName:"applicationMenu_"+index;colors:bar.colors;text:modelData.label;enabled:modelData.enabled;font.pixelSize:14;visible:index<bar.visibleMenus;onClicked:appMenu.show(index,this);onImplicitWidthChanged:Qt.callLater(bar.fit)}
                    onCountChanged:Qt.callLater(bar.fit)
                }
                BarButton {id:overflowButton;colors:bar.colors;text:qsTr("Weitere App-Menüs");glyph:"overflow-menu";iconOnly:true;visible:bar.visibleMenus<menuButtons.count;onClicked:overflow.open()}
            }
            Item {Layout.fillWidth:true;Layout.minimumWidth:0}
            Text {visible:bar.showContext && !!windowState.title;text:windowState.title;color:bar.colors.muted;font.pixelSize:12;elide:Text.ElideRight;textFormat:Text.PlainText;Layout.fillWidth:true;Layout.maximumWidth:300;Layout.minimumWidth:0}
            BarButton {colors:bar.colors;text:windowState.appName.includes("Reader")?qsTr("In Lumen besprechen"):qsTr("Seite merken …");glyph:"bookmark-new";iconOnly:true;visible:bar.showContext && bar.contextAvailable;onClicked:panelData.context(windowState.appName,windowState.title,windowState.pid)}
        }
    }
    Rectangle {
        id:rightIsland;x:bar.width-width-12;y:-18;height:bar.barSize+18;width:systemRow.implicitWidth+14
        radius:18;color:bar.colors.window;border.color:bar.colors.border
        Row {
            id:systemRow;anchors.top:parent.top;anchors.topMargin:18;anchors.left:parent.left;anchors.leftMargin:7;spacing:1
            BarButton {colors:bar.colors;text:qsTr("Lumen fragen oder suchen");glyph:"search";iconOnly:true;onClicked:panelData.launch("search")}
            BarButton {colors:bar.colors;text:qsTr("Übertragungen")+(bar.stateData.operations?.transfer?" · "+bar.stateData.operations.transfer.count:"");glyph:"folder-upload";iconOnly:true;visible:!!bar.stateData.operations?.transfer;onClicked:panelData.launch("transfer",bar.stateData.operations.transfer.id)}
            BarButton {colors:bar.colors;text:qsTr("Aufnahme in Audio Studio");glyph:"media-record";iconOnly:true;visible:!!bar.stateData.operations?.audio;onClicked:panelData.launch("app","meetings")}
            BarButton {id:networkButton;colors:bar.colors;text:qsTr("Netzwerk");glyph:"network-wireless";iconOnly:true;visible:bar.showStatus;onClicked:{systemPopup.open();panelData.refresh()}}
            BarButton {id:volumeButton;colors:bar.colors;text:qsTr("Lautstärke");glyph:bar.stateData.system?.muted?"audio-volume-muted":"audio-volume-high";iconOnly:true;visible:bar.showStatus;onClicked:{systemPopup.open();panelData.refresh()}}
            BarButton {colors:bar.colors;text:qsTr("Mitteilungen")+(bar.stateData.unread>0?" · "+bar.stateData.unread:"");glyph:bar.stateData.unread>0?"notifications-new":"notifications";iconOnly:true;onClicked:panelData.launch("notifications")}
            BarButton {colors:bar.colors;text:bar.clockText;visible:bar.width>460;font.pixelSize:13;onClicked:{systemPopup.open();panelData.refresh()}}
            BarButton {colors:bar.colors;text:qsTr("Systemsteuerung");glyph:"settings-configure";iconOnly:true;visible:bar.width<=460;onClicked:{systemPopup.open();panelData.refresh()}}
            onImplicitWidthChanged:Qt.callLater(bar.fit)
        }
    }
    component BarPopup:Popup {
        parent:bar.contentItem
        popupType:Popup.Item
        focus:true
        padding:16;closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
        width:Math.min(380,bar.width-24);y:bar.barSize+6
        onVisibleChanged:Qt.callLater(bar.mask)
        onClosed:{Qt.callLater(bar.mask);if(bar.active)windowState.action("activate")}
        background:Rectangle {color:bar.colors.window;radius:13;border.color:bar.colors.border}
    }
    BarPopup {
        id:launcher;objectName:"appsPopup";x:12
        contentItem:ColumnLayout {
            spacing:12
            Label {text:qsTr("Deine Lumen Apps");color:bar.colors.text;font.pixelSize:19;font.weight:Font.Medium;Layout.fillWidth:true}
            GridLayout {
                columns:launcher.width>=350?4:3;columnSpacing:4;rowSpacing:6;Layout.fillWidth:true
                Repeater {
                    model:bar.stateData.apps||[]
                    BarButton {required property var modelData;objectName:"openApp_"+modelData.id;colors:bar.colors;text:modelData.label;Layout.fillWidth:true;Layout.preferredWidth:0;Layout.preferredHeight:82;Accessible.name:modelData.title;
                        contentItem:Column {spacing:6;Kirigami.Icon {source:modelData.id==="lumen"?"lumen":"lumen-"+modelData.id;width:38;height:38;anchors.horizontalCenter:parent.horizontalCenter}Text {text:modelData.label;color:bar.colors.text;font.pixelSize:12;horizontalAlignment:Text.AlignHCenter;width:parent.width;elide:Text.ElideRight}}
                        onClicked:{launcher.close();panelData.launch("app",modelData.id)}
                    }
                }
            }
            Label {visible:!!panelData.error;text:panelData.error;color:bar.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            Rectangle {height:1;color:bar.colors.border;Layout.fillWidth:true}
            BarButton {colors:bar.colors;text:qsTr("Alle Aufgaben");glyph:"view-task";Layout.fillWidth:true;onClicked:{launcher.close();panelData.launch("tasks")}}
            BarButton {colors:bar.colors;text:qsTr("Alle Programme");glyph:"view-app-grid";Layout.fillWidth:true;onClicked:{launcher.close();panelData.control("search")}}
        }
    }
    BarPopup {
        id:systemPopup;x:bar.width-width-12
        contentItem:ColumnLayout {
            spacing:12
            Label {text:Qt.formatDate(new Date(),"dddd, d. MMMM");color:bar.colors.text;font.pixelSize:18;wrapMode:Text.Wrap;Layout.fillWidth:true}
            Label {text:qsTr("Netzwerk")+" · "+(bar.stateData.system?.network||qsTr("Nicht verfügbar"));color:bar.colors.muted;Layout.fillWidth:true}
            RowLayout {Layout.fillWidth:true
                BarButton {colors:bar.colors;text:qsTr("Stummschalten");glyph:bar.stateData.system?.muted?"audio-volume-muted":"audio-volume-high";iconOnly:true;onClicked:panelData.control("mute")}
                Slider {id:volume;Layout.fillWidth:true;from:0;to:100;value:bar.stateData.system?.volume||0;enabled:bar.stateData.system?.volume!==null;Accessible.name:qsTr("Lautstärke");onMoved:volumeCommit.restart()}
                Label {text:Math.round(volume.value)+" %";color:bar.colors.text}
                Timer {id:volumeCommit;interval:180;onTriggered:if(!volume.pressed)panelData.control("volume",Math.round(volume.value));else restart()}
            }
            RowLayout {visible:bar.stateData.system?.brightness!==null;Layout.fillWidth:true
                Label {text:qsTr("Helligkeit");color:bar.colors.text}
                Slider {id:brightness;Layout.fillWidth:true;from:0;to:100;value:bar.stateData.system?.brightness||0;Accessible.name:qsTr("Helligkeit");onMoved:brightnessCommit.restart()}
                Timer {id:brightnessCommit;interval:180;onTriggered:if(!brightness.pressed)panelData.control("brightness",Math.round(brightness.value));else restart()}
            }
            BarButton {colors:bar.colors;text:qsTr("Netzwerkeinstellungen");glyph:"network-wireless";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("network")}}
            BarButton {colors:bar.colors;text:qsTr("Audioeinstellungen");glyph:"audio-card";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("audio")}}
            BarButton {colors:bar.colors;text:qsTr("Lumen System");glyph:"lumen-system";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("hardware")}}
            BarButton {colors:bar.colors;text:qsTr("Einstellungen");glyph:"settings-configure";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.launch("settings")}}
            BarButton {colors:bar.colors;text:qsTr("Bildschirm sperren");glyph:"system-lock-screen";Layout.fillWidth:true;onClicked:{systemPopup.close();panelData.control("lock")}}
        }
    }
    BarPopup {
        id:overflow;x:Math.min(bar.width-width-12,Math.max(12,overflowButton.mapToItem(bar.contentItem,0,0).x))
        contentItem:ColumnLayout {spacing:2
            Repeater {model:appMenu.entries;BarButton {required property var modelData;required property int index;colors:bar.colors;text:modelData.label;enabled:modelData.enabled;visible:index>=bar.visibleMenus;Layout.fillWidth:true;onClicked:appMenu.show(index,this)}}
        }
    }
    BarPopup {
        id:windowMenu;x:Math.min(bar.width-width-12,Math.max(12,appName.mapToItem(bar.contentItem,0,0).x))
        contentItem:ColumnLayout {spacing:2
            Label {text:windowState.appName||qsTr("Desktop");color:bar.colors.text;font.weight:Font.Medium;Layout.fillWidth:true}
            Repeater {model:[{label:qsTr("Maximieren / Wiederherstellen"),action:"maximize",icon:"window-maximize"},{label:qsTr("Minimieren"),action:"minimize",icon:"window-minimize"},{label:qsTr("Schließen"),action:"close",icon:"window-close"}]
                BarButton {required property var modelData;colors:bar.colors;text:modelData.label;glyph:modelData.icon;enabled:!!windowState.activeWindow;Layout.fillWidth:true;onClicked:{windowState.action(modelData.action);windowMenu.close()}}
            }
        }
    }
    Component.onCompleted:Qt.callLater(fit)
}
