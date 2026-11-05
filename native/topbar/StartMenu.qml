import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import org.kde.kirigami as Kirigami
import org.kde.plasma.private.kicker as Kicker
import org.kde.kitemmodels as Models
import org.kde.plasma.private.sessions 2.0 as Sessions

ColumnLayout {
    id: start
    required property var colors
    required property var controller
    required property var translate
    property bool lumenOnly: false
    property bool library: false
    property bool editing: false
    property bool active: false
    readonly property bool menuOpened:context.opened||power.opened
    property int category: -1
    readonly property bool searching: !!query.text.trim()
    readonly property var lumenApps: (controller.snapshot.apps||[]).filter(app=>app.label.toLocaleLowerCase().includes(query.text.trim().toLocaleLowerCase()))
    signal launched()
    signal moreRecent()
    spacing: 0
    height:implicitHeight
    onActiveChanged:if(!active){context.close();power.close();error.text=""}
    Shortcut {sequence:"Ctrl+K";enabled:start.active;onActivated:query.forceActiveFocus()}

    function reset(lumen) {lumenOnly=lumen;library=lumen;editing=false;category=-1;query.clear();context.close();power.close()}
    function focusSearch() {query.forceActiveFocus()}
    function togglePin(id) {
        if(!id)return
        if(favorites.isFavorite(id))favorites.removeFavorite(id);else favorites.addFavorite(id)
        controller.pinnedApps=favorites.favorites
    }
    function run(model,row,action="",argument=null) {
        if(model && row>=0 && model.trigger(row,action,argument))launched()
        else error.text=translate("Das Programm konnte nicht gestartet werden.")
    }
    function runFiltered(index) {if(index>=0 && index<filtered.count)run(filtered.sourceModel,filtered.mapToSource(filtered.index(index,0)).row)}
    function contextFor(button,model,row,data) {
        context.source=model;context.row=row;context.favoriteId=data.favoriteId||"";context.title=data.display||""
        context.actions=(data.actionList||[]).filter(action=>action.actionId==="_kicker_jumpListAction" && action.text)
        const point=button.mapToItem(start,0,button.height)
        context.x=Math.max(0,Math.min(start.width-context.width,point.x))
        context.anchorY=point.y
        context.open()
    }
    Kicker.SimpleFavoritesModel {id:favorites;objectName:"startFavorites";favorites:start.controller.pinnedApps}
    Kicker.RootModel {
        id:catalogue;objectName:"programCatalogue";flat:true;sorted:true;showAllApps:true;showAllAppsCategorized:false
        showRecentApps:false;showRecentDocs:false;showRecentFolders:false;showPowerSession:false;showFavoritesPlaceholder:false
        favoritesModel:favorites
    }
    Kicker.RootModel {
        id:categories;flat:true;sorted:true;showAllApps:false;showAllAppsCategorized:false
        showRecentApps:false;showRecentDocs:false;showRecentFolders:false;showPowerSession:false;showFavoritesPlaceholder:false
        favoritesModel:favorites
    }
    Models.KSortFilterProxyModel {
        id:filtered
        sourceModel:start.category>=0&&!start.searching?categories.modelForRow(start.category):catalogue.count?catalogue.modelForRow(0):null
        filterString:query.text.trim();filterCaseSensitivity:Qt.CaseInsensitive
    }
    Sessions.SessionManagement {id:session}
    Connections {target:start.controller;function onControlFinished(action,value){if(action.startsWith("recent:open:"))start.launched()}}
    ColumnLayout {id:launchBody;Layout.fillWidth:true;Layout.margins:24;spacing:20
    RowLayout {Layout.fillWidth:true;spacing:12
        Label {text:start.translate(start.lumenOnly?"Lumen Apps":start.library?"Alle Apps":"Dein Start");color:start.colors.text;font.pixelSize:26;font.weight:Font.Medium;Layout.fillWidth:true;wrapMode:Text.Wrap}
        BarButton {objectName:"startLibraryButton";colors:start.colors;text:start.translate(start.library?"Zurück":"Alle Apps");glyph:start.library?"go-previous":"go-next";LayoutMirroring.enabled:!start.library;LayoutMirroring.childrenInherit:true;Layout.alignment:Qt.AlignTop
            onClicked:{start.lumenOnly=false;start.library=!start.library;query.clear();start.editing=false;start.category=-1}}
    }
    TextField {
        id:query;objectName:"programSearch";Layout.fillWidth:true;implicitHeight:50
        placeholderText:start.translate("Welche App brauchst du?");Accessible.name:placeholderText;selectByMouse:true
        leftPadding:40;rightPadding:width>=440?68:16
        palette.text:start.colors.text;palette.placeholderText:start.colors.muted
        background:Rectangle {color:start.colors.base;radius:12;border.color:query.activeFocus?start.colors.accent:start.colors.border}
        Kirigami.Icon {source:"search";isMask:true;color:start.colors.muted;width:18;height:18;x:14;anchors.verticalCenter:parent.verticalCenter}
        Label {visible:query.width>=440;text:"Strg K";font.pixelSize:12;color:start.colors.muted;anchors.right:parent.right;anchors.rightMargin:14;anchors.verticalCenter:parent.verticalCenter}
        onTextChanged:{grid.currentIndex=0;error.text="";context.close();power.close()}
        onAccepted:if(start.lumenOnly){if(start.lumenApps.length){start.controller.launch("app",start.lumenApps[0].id);start.launched()}}else if(start.searching)start.runFiltered(grid.currentIndex)
        Keys.onDownPressed:if(grid.visible&&grid.count){grid.currentIndex=0;grid.forceActiveFocus()}
        Keys.onEscapePressed:event=>{if(text){clear();event.accepted=true}else event.accepted=false}
    }
    ColumnLayout {visible:!start.library&&!start.searching;Layout.fillWidth:true;spacing:12
        RowLayout {Layout.fillWidth:true
            Label {text:start.translate("Angeheftet");color:start.colors.text;Layout.fillWidth:true}
            BarButton {objectName:"startEditButton";colors:start.colors;text:start.translate(start.editing?"Fertig":"Anpassen");glyph:start.editing?"dialog-ok-apply":"configure";checkable:true;checked:start.editing;onClicked:start.editing=!start.editing}
        }
        GridLayout {Layout.fillWidth:true;columns:launchBody.width>=560?6:3;columnSpacing:4;rowSpacing:8
            Repeater {model:favorites
                BarButton {id:pin;required property var model;required property int index;objectName:"startPin_"+index;colors:start.colors
                    Layout.fillWidth:true;Layout.preferredWidth:0;Layout.preferredHeight:96
                    text:model.display;Accessible.name:model.display+(start.editing?" · "+start.translate("Entfernen"):"")
                    contentItem:Column {spacing:8
                        Rectangle {width:44;height:44;radius:12;color:start.colors.base;border.color:start.colors.border;anchors.horizontalCenter:parent.horizontalCenter
                            Kirigami.Icon {anchors.centerIn:parent;width:26;height:26;source:pin.model.decoration}
                            Kirigami.Icon {visible:start.editing;anchors.right:parent.right;anchors.top:parent.top;width:16;height:16;source:"list-remove";isMask:true;color:start.colors.accent}
                        }
                        Label {text:pin.text;textFormat:Text.PlainText;color:start.colors.text;width:parent.width;horizontalAlignment:Text.AlignHCenter;wrapMode:Text.Wrap;font.pixelSize:12}
                    }
                    onClicked:if(start.editing)start.togglePin(model.favoriteId);else start.run(favorites,index)
                    TapHandler {acceptedButtons:Qt.RightButton;onTapped:start.contextFor(pin,favorites,pin.index,pin.model)}
                    Keys.onPressed:event=>{if(event.key===Qt.Key_Menu || event.key===Qt.Key_F10&&event.modifiers&Qt.ShiftModifier){start.contextFor(pin,favorites,index,model);event.accepted=true}}
                }
            }
        }
        Label {visible:!favorites.count;text:start.translate("Noch keine Apps angeheftet. Wähle sie unter „Alle Apps“ aus.");color:start.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
        Rectangle {Layout.fillWidth:true;Layout.topMargin:8;height:1;color:start.colors.border}
        RowLayout {Layout.fillWidth:true;Layout.topMargin:4
            Label {text:start.translate("Gleich weiter");color:start.colors.text;Layout.fillWidth:true}
            BarButton {visible:(start.controller.details.recent?.items||[]).length>2;colors:start.colors;text:start.translate("Mehr");onClicked:start.moreRecent()}
        }
        Repeater {model:(start.controller.details.recent?.items||[]).slice(0,2)
            BarButton {required property var modelData;required property int index;objectName:"startRecent_"+index;colors:start.colors;Layout.fillWidth:true;Layout.preferredHeight:62
                text:modelData.title;enabled:!start.controller.controlBusy
                contentItem:RowLayout {spacing:12
                    Kirigami.Icon {source:modelData.icon||"text-x-generic";Layout.preferredWidth:28;Layout.preferredHeight:28}
                    ColumnLayout {Layout.fillWidth:true;spacing:2
                        Label {text:modelData.title;textFormat:Text.PlainText;color:start.colors.text;elide:Text.ElideRight;Layout.fillWidth:true}
                        Label {text:start.translate(modelData.kind==="conversation"?"Gespräch":"Datei")+(modelData.updated?" · "+Qt.formatDateTime(new Date(modelData.updated*1000),"dd.MM. hh:mm"):"");color:start.colors.muted;font.pixelSize:12}
                    }
                    Kirigami.Icon {source:"go-next";isMask:true;color:start.colors.muted;Layout.preferredWidth:18;Layout.preferredHeight:18}
                }
                onClicked:start.controller.systemAction("recent","open",modelData.target)
            }
        }
        Label {visible:!(start.controller.details.recent?.items||[]).length;text:start.translate("Noch keine zuletzt verwendeten Inhalte.");color:start.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
    }
    ColumnLayout {visible:start.library||start.searching;Layout.fillWidth:true;spacing:12
        Flow {visible:!start.searching&&!start.lumenOnly;Layout.fillWidth:true;spacing:4
            BarButton {objectName:"startCategoryAll";colors:start.colors;text:start.translate("Alle");highlighted:start.category<0;onClicked:start.category=-1}
            BarButton {objectName:"startCategoryLumen";colors:start.colors;text:"Lumen";onClicked:{start.lumenOnly=true;start.category=-1}}
            Repeater {model:categories
                BarButton {required property var model;required property int index;objectName:"startCategory_"+index;colors:start.colors;text:model.display;highlighted:start.category===index;onClicked:start.category=index}
            }
        }
        Label {visible:start.searching;text:start.translate("Passende Apps")+" · "+(start.lumenOnly?start.lumenApps.length:filtered.count);color:start.colors.muted;Layout.fillWidth:true}
        GridView {
            id:grid;objectName:"programList";visible:!start.lumenOnly;Layout.fillWidth:true;Layout.preferredHeight:Math.min(330,contentHeight);clip:true
            readonly property int columns:width>=540?3:width>=380?2:1
            cellWidth:width/columns;cellHeight:80;model:filtered
            currentIndex:0;keyNavigationEnabled:true;reuseItems:true
            ScrollBar.vertical:ScrollBar {}
            Keys.onReturnPressed:start.runFiltered(currentIndex)
            Keys.onEscapePressed:event=>{if(start.lumenOnly){start.lumenOnly=false;event.accepted=true}else if(start.library&&!start.searching){start.library=false;event.accepted=true}else event.accepted=false}
            onCurrentIndexChanged:positionViewAtIndex(currentIndex,GridView.Contain)
            delegate:Item {id:app;required property var model;required property int index;property var entry:model
                width:grid.cellWidth;height:grid.cellHeight
                readonly property bool pinned:{start.controller.pinnedApps;return favorites.isFavorite(String(app.entry.favoriteId||""))}
                BarButton {id:appButton;objectName:"program_"+app.index;colors:start.colors
                    anchors.fill:parent;anchors.margins:4;rightPadding:38
                    highlighted:app.GridView.isCurrentItem&&grid.activeFocus
                    text:String(app.entry.display||"")
                    contentItem:RowLayout {spacing:10
                        Kirigami.Icon {source:app.entry.decoration;Layout.preferredWidth:28;Layout.preferredHeight:28}
                        Label {text:appButton.text;textFormat:Text.PlainText;color:start.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
                    }
                    background:Rectangle {color:appButton.hovered?start.colors.alternate:start.colors.base;border.color:appButton.visualFocus||appButton.hovered?start.colors.accent:start.colors.border;border.width:appButton.visualFocus?2:1;radius:11}
                    onClicked:start.runFiltered(app.index)
                    TapHandler {acceptedButtons:Qt.RightButton;onTapped:start.contextFor(appButton,filtered.sourceModel,filtered.mapToSource(filtered.index(app.index,0)).row,app.entry)}
                    Keys.onPressed:event=>{if(event.key===Qt.Key_Menu||event.key===Qt.Key_F10&&event.modifiers&Qt.ShiftModifier){start.contextFor(appButton,filtered.sourceModel,filtered.mapToSource(filtered.index(app.index,0)).row,app.entry);event.accepted=true}}
                }
                BarButton {objectName:"startPinToggle_"+app.index;visible:!!app.entry.favoriteId;colors:start.colors;text:start.translate(app.pinned?"Nicht mehr anheften":"Anheften");glyph:app.pinned?"window-unpin":"window-pin";iconOnly:true;highlighted:app.pinned
                    anchors.right:app.right;anchors.rightMargin:6;anchors.verticalCenter:app.verticalCenter;width:32
                    onClicked:start.togglePin(app.entry.favoriteId)
                }
            }
        }
        GridLayout {visible:start.lumenOnly;Layout.fillWidth:true;columns:launchBody.width>=520?4:3;columnSpacing:4;rowSpacing:8
            Repeater {model:start.lumenApps
                BarButton {required property var modelData;objectName:"openApp_"+modelData.id;colors:start.colors;Layout.fillWidth:true;Layout.preferredWidth:0;Layout.preferredHeight:96;text:modelData.label
                    contentItem:Column {spacing:8
                        Kirigami.Icon {source:"qrc:/lumen/icons/"+(modelData.id==="lumen"?"lumen":"lumen-"+modelData.id)+".svg";width:40;height:40;anchors.horizontalCenter:parent.horizontalCenter}
                        Label {text:modelData.label;textFormat:Text.PlainText;color:start.colors.text;width:parent.width;horizontalAlignment:Text.AlignHCenter;wrapMode:Text.Wrap}
                    }
                    onClicked:{start.controller.launch("app",modelData.id);start.launched()}
                }
            }
        }
        Label {visible:start.lumenOnly?!start.lumenApps.length:!grid.count;text:start.translate("Keine Programme gefunden.");color:start.colors.muted;Layout.fillWidth:true;wrapMode:Text.Wrap}
        BarButton {visible:start.lumenOnly;colors:start.colors;text:start.translate("Alle Aufgaben");glyph:"view-task";Layout.fillWidth:true;onClicked:{start.controller.launch("tasks");start.launched()}}
    }
    Label {id:error;visible:!!text;color:start.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
    Label {visible:!!start.controller.error;text:start.translate(start.controller.error);color:start.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true;textFormat:Text.PlainText}
    }
    Frame {Layout.fillWidth:true;Layout.leftMargin:1;Layout.rightMargin:1;Layout.bottomMargin:1;padding:12;leftPadding:16;rightPadding:16
      background:Rectangle {color:start.colors.base;bottomLeftRadius:(start.colors.radius||10)+3;bottomRightRadius:(start.colors.radius||10)+3
          Rectangle {height:1;width:parent.width;color:start.colors.border}}
      contentItem:RowLayout {spacing:4
        BarButton {objectName:"startProfileButton";colors:start.colors;text:start.controller.userName;glyph:"user-identity";Layout.fillWidth:true;onClicked:{start.controller.launch("settings");start.launched()}}
        BarButton {objectName:"startSettingsButton";colors:start.colors;text:start.translate("Einstellungen");glyph:"settings-configure";iconOnly:true;onClicked:{start.controller.launch("settings");start.launched()}}
        BarButton {objectName:"startLockButton";colors:start.colors;text:start.translate("Bildschirm sperren");glyph:"system-lock-screen";iconOnly:true;enabled:session.canLock;onClicked:{session.lock();start.launched()}}
        BarButton {id:powerButton;objectName:"startPowerButton";colors:start.colors;text:start.translate("Sitzung und Energie");glyph:"system-shutdown";iconOnly:true;onClicked:power.open()}
      }
    }
    component StartAction:MenuItem {
        id:action
        implicitHeight:Math.max(36,contentItem.implicitHeight+12)
        leftPadding:10;rightPadding:10
        contentItem:RowLayout {spacing:10
            Kirigami.Icon {visible:!!action.icon.name;source:action.icon.name;isMask:true;color:action.enabled?start.colors.text:start.colors.muted;Layout.preferredWidth:18;Layout.preferredHeight:18}
            Label {text:action.text;textFormat:Text.PlainText;color:action.enabled?start.colors.text:start.colors.muted;font:action.font;elide:Text.ElideRight;Layout.fillWidth:true}
        }
        background:Rectangle {color:action.highlighted?start.colors.alternate:start.colors.base;radius:7
            border.color:action.highlighted?start.colors.accent:"transparent"}
    }
    Menu {id:power;objectName:"startPowerMenu";parent:start;x:Math.max(0,start.width-width);y:Math.max(0,start.height-height-60);width:Math.min(230,start.width);padding:6;popupType:Popup.Window
        background:Rectangle {color:start.colors.base;border.color:start.colors.border;radius:12}
        StartAction {text:start.translate("Ruhezustand");icon.name:"system-suspend";enabled:session.canSuspend;onTriggered:{session.suspend();start.launched()}}
        StartAction {text:start.translate("Neu starten");icon.name:"system-reboot";enabled:session.canReboot;onTriggered:{session.requestReboot(Sessions.SessionManagement.ForcePrompt);start.launched()}}
        StartAction {text:start.translate("Abmelden");icon.name:"system-log-out";enabled:session.canLogout;onTriggered:{session.requestLogout(Sessions.SessionManagement.ForcePrompt);start.launched()}}
        StartAction {text:start.translate("Ausschalten");icon.name:"system-shutdown";enabled:session.canShutdown;onTriggered:{session.requestShutdown(Sessions.SessionManagement.ForcePrompt);start.launched()}}
    }
    Menu {id:context;objectName:"startAppContext";parent:start;width:Math.min(260,start.width);padding:6;popupType:Popup.Window
        property var source:null;property int row:-1;property string favoriteId:"";property var actions:[]
        property real anchorY:0
        height:Math.min(implicitHeight,start.height)
        function place(){y=Math.max(0,Math.min(start.height-height,anchorY))}
        onOpened:Qt.callLater(place)
        onHeightChanged:if(visible)Qt.callLater(place)
        Connections {target:context.source;ignoreUnknownSignals:true
            function onModelReset(){context.close()}
            function onRowsRemoved(){context.close()}
            function onRowsMoved(){context.close()}
        }
        background:Rectangle {color:start.colors.base;border.color:start.colors.border;radius:12}
        StartAction {text:context.title;enabled:false}
        StartAction {text:start.translate("Öffnen");icon.name:"go-next";onTriggered:start.run(context.source,context.row)}
        Instantiator {model:context.actions
            delegate:StartAction {required property var modelData;required property int index;objectName:"startNativeAction_"+index;text:modelData.text;icon.name:modelData.icon||"application-x-executable";onTriggered:start.run(context.source,context.row,modelData.actionId,modelData.actionArgument)}
            onObjectAdded:(index,object)=>context.insertItem(index+2,object)
            onObjectRemoved:(index,object)=>context.removeItem(object)
        }
        StartAction {objectName:"startContextPin";visible:!!context.favoriteId;text:start.translate(favorites.isFavorite(context.favoriteId)?"Nicht mehr anheften":"Anheften");icon.name:"window-pin";onTriggered:start.togglePin(context.favoriteId)}
    }
}
