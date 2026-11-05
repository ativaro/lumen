import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Popup {
    id: menu
    required property var colors
    required property var controller
    required property var windows
    required property var notifications
    required property var translate
    required property double now
    property string page:"status"
    property string section:"decision"
    property string selectedPlayer:""
    property real heightLimit:600
    readonly property bool narrow:width<650
    readonly property var activity:controller.snapshot.activity||({})
    readonly property var focusState:activity.focus||({state:"off",remaining:0,end:0})
    readonly property int seconds:focusState.end?Math.max(0,Math.ceil(focusState.end-now/1000)):focusState.remaining||0
    readonly property bool quiet:notifications.notificationsInhibitedUntil.getTime()>now
    readonly property var player:controller.players.find(p=>p.id===selectedPlayer)||controller.players[0]||null
    readonly property string title:page==="windows"?translate("Deine offenen Fenster"):page==="recent"?translate("Dort weitermachen"):translate("Alles im Blick")
    popupType:Popup.Item;focus:true;padding:24
    closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
    height:Math.min(implicitHeight,heightLimit)
    background:Rectangle {color:menu.colors.window;radius:menu.colors.radius||10;border.color:menu.colors.border}
    onOpened:{controller.inspect(page==="recent"?"recent":"activity");controller.refreshMedia()}
    onPageChanged:if(opened)controller.inspect(page==="recent"?"recent":"activity")
    signal geometryUpdated()
    onVisibleChanged:geometryUpdated()
    onHeightChanged:geometryUpdated()
    contentItem:ScrollView {
        id:scroll;clip:true;contentWidth:availableWidth;implicitHeight:body.implicitHeight
        ColumnLayout {
            id:body;width:scroll.availableWidth;spacing:20
            RowLayout {Layout.fillWidth:true
                Label {text:menu.title;color:menu.colors.text;font.pixelSize:20;font.weight:Font.Medium;Layout.fillWidth:true;wrapMode:Text.Wrap}
                BarButton {colors:menu.colors;glyph:"window-close";iconOnly:true;text:menu.translate("Schließen");onClicked:menu.close()}
            }
            GridLayout {visible:menu.page==="windows";Layout.fillWidth:true;columns:menu.narrow?1:3;columnSpacing:16;rowSpacing:12
                Repeater {model:menu.windows.windowModel
                    BarButton {required property var model;required property int index;objectName:"overviewWindow_"+index;colors:menu.colors
                        visible:!!model.IsWindow;Layout.fillWidth:true;Layout.preferredWidth:0;Layout.preferredHeight:100
                        highlighted:!!model.IsActive;text:String(model.display||model.AppName||"");glyph:model.decoration
                        contentItem:Column {spacing:12;width:parent.width
                            Kirigami.Icon {source:model.decoration;width:24;height:24;color:menu.colors.text}
                            Label {text:String(model.AppName||"");color:menu.colors.muted;width:parent.width;elide:Text.ElideRight;textFormat:Text.PlainText}
                            Label {text:String(model.display||"");color:menu.colors.text;width:parent.width;elide:Text.ElideRight;textFormat:Text.PlainText}
                        }
                        onClicked:{menu.windows.activate(index);menu.close()}
                    }
                }
                Label {visible:menu.windows.windowModel.count===0;text:menu.translate("Keine offenen Fenster.");color:menu.colors.muted;Layout.fillWidth:true}
            }
            ColumnLayout {visible:menu.page==="recent";Layout.fillWidth:true;spacing:8
                Label {text:menu.translate("Geöffnete Inhalte");color:menu.colors.muted;Layout.fillWidth:true}
                Repeater {model:menu.page==="recent"?menu.windows.windowModel:null
                    BarButton {required property var model;required property int index;colors:menu.colors;visible:!!model.IsWindow;Layout.fillWidth:true;text:String(model.display||model.AppName||"");glyph:model.decoration;onClicked:{menu.windows.activate(index);menu.close()}}
                }
                Label {text:menu.translate("Zuletzt verwendete Dateien");color:menu.colors.muted;Layout.topMargin:12;Layout.fillWidth:true}
                Repeater {model:menu.controller.details.recent?.items||[]
                    BarButton {required property var modelData;required property int index;objectName:"recentContent_"+index;colors:menu.colors;Layout.fillWidth:true;text:modelData.title;glyph:modelData.icon||"text-x-generic";enabled:!menu.controller.controlBusy
                        onClicked:menu.controller.systemAction("recent","open",modelData.path)}
                }
                Label {visible:!(menu.controller.details.recent?.items||[]).length;text:menu.translate("Noch keine zuletzt verwendeten Dateien.");color:menu.colors.muted;Layout.fillWidth:true;wrapMode:Text.Wrap}
            }
            GridLayout {visible:menu.page==="status";Layout.fillWidth:true;columns:menu.narrow?1:2;columnSpacing:32;rowSpacing:20
                ColumnLayout {Layout.fillWidth:true;Layout.minimumWidth:0;spacing:16
                    ColumnLayout {visible:menu.section==="decision";Layout.fillWidth:true;spacing:12
                        Label {text:menu.translate("Deine Entscheidung ist gefragt");color:menu.colors.text;font.pixelSize:20;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        Repeater {model:menu.activity.decisions||[]
                            BarButton {required property var modelData;required property int index;objectName:"reviewDecision_"+index;colors:menu.colors;Layout.fillWidth:true;text:modelData.title;glyph:"dialog-question";enabled:!menu.controller.controlBusy;onClicked:menu.controller.systemAction("activity","decision",modelData.id)}
                        }
                        Label {text:menu.activity.decisionError||menu.translate((menu.activity.decisions||[]).length?"In Lumen prüfen und dort entscheiden.":"Keine offenen Freigaben.");color:menu.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
                    }
                    ColumnLayout {visible:menu.section==="focus";Layout.fillWidth:true;spacing:12
                        Label {text:menu.translate("In Ruhe weiterarbeiten");color:menu.colors.text;font.pixelSize:20;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        Label {text:menu.focusState.state==="off"?"25:00":Math.floor(menu.seconds/60).toString().padStart(2,"0")+":"+(menu.seconds%60).toString().padStart(2,"0");color:menu.colors.text;font.pixelSize:32;font.weight:Font.Medium}
                        Label {text:menu.translate(menu.focusState.state==="paused"?"Fokuszeit pausiert":menu.focusState.state==="running"&&menu.seconds?"Fokuszeit aktiv":menu.focusState.state==="off"?"Eine konzentrierte Runde für deine aktuelle Arbeit.":"Fokuszeit beendet");color:menu.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        Flow {Layout.fillWidth:true;spacing:8
                            BarButton {objectName:"focusToggleButton";colors:menu.colors;primary:true;enabled:!menu.controller.controlBusy;text:menu.translate(menu.focusState.state==="running"&&menu.seconds?"Pausieren":menu.focusState.state==="paused"?"Fortsetzen":"Fokus starten");glyph:menu.focusState.state==="running"&&menu.seconds?"media-playback-pause":"media-playback-start";onClicked:menu.controller.systemAction("activity","focus:"+(menu.focusState.state==="running"&&menu.seconds?"pause":menu.focusState.state==="paused"?"resume":"start"))}
                            BarButton {objectName:"focusStopButton";visible:menu.focusState.state!=="off";colors:menu.colors;text:menu.translate("Beenden");enabled:!menu.controller.controlBusy;onClicked:menu.controller.systemAction("activity","focus:stop")}
                        }
                    }
                    ColumnLayout {visible:menu.section==="dnd";Layout.fillWidth:true;spacing:12
                        Label {text:menu.translate("Nicht stören");color:menu.colors.text;font.pixelSize:20;Layout.fillWidth:true}
                        Label {text:menu.translate("Popups pausieren für eine Stunde. Mitteilungen bleiben im Verlauf; Freigaben bleiben erreichbar.");color:menu.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        BarButton {objectName:"dndToggleButton";colors:menu.colors;checkable:true;checked:menu.quiet;text:menu.translate(menu.quiet?"Nicht stören beenden":"Nicht stören aktivieren");glyph:"notifications-disabled";onClicked:{menu.notifications.notificationsInhibitedUntil=menu.quiet?new Date(0):new Date(Date.now()+3600000);menu.notifications.save()}}
                    }
                    ColumnLayout {visible:menu.section==="media";Layout.fillWidth:true;spacing:12
                        Label {text:menu.translate("Wiedergabe");color:menu.colors.text;font.pixelSize:20;Layout.fillWidth:true}
                        Label {text:menu.player?.title||menu.translate("Keine aktive Wiedergabe");textFormat:Text.PlainText;color:menu.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        Label {text:menu.player?[menu.player.artist,menu.player.app].filter(Boolean).join(" · "):menu.translate("Player mit MPRIS-Unterstützung erscheinen hier.");textFormat:Text.PlainText;color:menu.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        Flow {visible:!!menu.player;Layout.fillWidth:true;spacing:8
                            BarButton {objectName:"mediaPreviousButton";colors:menu.colors;text:menu.translate("Vorheriger Titel");glyph:"media-skip-backward";enabled:!!menu.player?.control&&!!menu.player.previous;onClicked:menu.controller.mediaAction(menu.player.id,"Previous")}
                            BarButton {objectName:"mediaPlayButton";colors:menu.colors;primary:true;text:menu.translate(menu.player?.playing?"Pausieren":"Abspielen");glyph:menu.player?.playing?"media-playback-pause":"media-playback-start";enabled:!!menu.player?.control&&!!(menu.player.playing?menu.player.pause:menu.player.play);onClicked:menu.controller.mediaAction(menu.player.id,"PlayPause")}
                            BarButton {objectName:"mediaNextButton";colors:menu.colors;text:menu.translate("Nächster Titel");glyph:"media-skip-forward";enabled:!!menu.player?.control&&!!menu.player.next;onClicked:menu.controller.mediaAction(menu.player.id,"Next")}
                        }
                        Repeater {model:menu.controller.players.length>1?menu.controller.players:[]
                            BarButton {required property var modelData;colors:menu.colors;Layout.fillWidth:true;text:modelData.app;highlighted:menu.player?.id===modelData.id;onClicked:menu.selectedPlayer=modelData.id}
                        }
                    }
                    ColumnLayout {visible:menu.section==="update";Layout.fillWidth:true;spacing:12
                        Label {text:menu.translate(menu.activity.update?.pending?"Lumen-Update bereit":"Lumen-Updates");color:menu.colors.text;font.pixelSize:20;Layout.fillWidth:true;wrapMode:Text.Wrap}
                        Label {text:menu.activity.update?.notes||menu.translate("Im Updater prüfen und die gewünschten Komponenten auswählen.");textFormat:Text.PlainText;color:menu.colors.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
                        BarButton {objectName:"openUpdaterButton";colors:menu.colors;text:menu.translate("Im Updater ansehen");glyph:"system-software-update";enabled:!menu.controller.controlBusy;onClicked:menu.controller.systemAction("activity","update")}
                    }
                }
                ColumnLayout {Layout.fillWidth:menu.narrow;Layout.preferredWidth:menu.narrow?-1:210;Layout.alignment:Qt.AlignTop;spacing:4
                    Repeater {model:[{id:"decision",label:"Freigabe",icon:"dialog-question"},{id:"focus",label:"Fokuszeit",icon:"chronometer"},{id:"dnd",label:"Nicht stören",icon:"notifications-disabled"},{id:"media",label:"Wiedergabe",icon:"media-playback-start"},{id:"update",label:"Updates",icon:"system-software-update"}]
                        BarButton {required property var modelData;objectName:"activitySection_"+modelData.id;colors:menu.colors;Layout.fillWidth:true;text:menu.translate(modelData.label);glyph:modelData.icon;highlighted:menu.section===modelData.id;onClicked:menu.section=modelData.id}
                    }
                }
            }
            Label {visible:!!menu.controller.error;text:menu.translate(menu.controller.error);color:menu.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true;textFormat:Text.PlainText}
        }
    }
}
