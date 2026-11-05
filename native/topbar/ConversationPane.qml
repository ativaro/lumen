pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "search" as Search

Item {
    id:pane
    required property var controller
    required property var request
    required property var host
    required property var colors
    required property var translate
    property bool detached:false
    property bool dialogVisible:false
    property bool following:true
    signal detachRequested(bool dragging)
    signal collapseRequested()
    signal reattachRequested()
    function focusInput(){composer.forceActiveFocus()}
    function submit(){if(!request.draft.trim()||request.pending||controller.busy)return;following=true;request.error="";request.submitted=request.draft;request.submittedNote=JSON.stringify(request.note);request.pending=true;request.pendingAction=host.ask(request.submitted,request.note)}
    function latest(){if(conversation.contentItem){following=true;conversation.contentItem.cancelFlick();conversation.contentItem.contentY=Math.max(0,conversation.contentHeight-conversation.availableHeight)}}
    function followLatest(){if(following&&!scrollbar.pressed&&!conversation.contentItem.moving)latest()}
    onWidthChanged:widthTimer.restart()
    Timer {id:widthTimer;interval:150;onTriggered:if(pane.width>=168)pane.controller.model.call("width",[Math.min(712,pane.width-48)])}
    Connections {target:pane.controller;function onDataChanged(){if(pane.following)Qt.callLater(pane.followLatest)}}
    ColumnLayout {
        x:(parent.width-width)/2;width:Math.max(0,Math.min(760,parent.width-48));height:parent.height;spacing:16
        RowLayout {
            objectName:"conversationHeader";Layout.fillWidth:true;Layout.minimumHeight:48;Layout.preferredHeight:48;Layout.maximumHeight:48;spacing:12
            Item {objectName:"conversationDragArea";Layout.fillWidth:true;Layout.fillHeight:true
                Label {anchors.verticalCenter:parent.verticalCenter;width:parent.width;text:pane.controller.data.title||pane.translate("Gespräch mit Lumen");color:pane.colors.text;font.pixelSize:18;font.weight:Font.Medium;elide:Text.ElideRight}
                DragHandler {target:null;onActiveChanged:if(active)pane.detached?pane.Window.window.startSystemMove():pane.detachRequested(true)}
            }
            BarButton {objectName:"detachConversation";colors:pane.colors;glyph:pane.detached?"pin":"go-up";text:pane.translate(pane.detached?"In Leiste anheften":"Als Fenster öffnen");iconOnly:parent.width<560;onClicked:pane.detached?pane.reattachRequested():pane.detachRequested(false)}
            BarButton {objectName:"newTopbarConversation";colors:pane.colors;glyph:"list-add";text:pane.translate("Neues Gespräch");iconOnly:true;enabled:!pane.controller.busy&&!pane.request.pending;onClicked:pane.controller.model.call("reset")}
            BarButton {objectName:"collapseConversation";colors:pane.colors;glyph:"arrow-up";text:pane.translate("Gespräch einklappen");iconOnly:true;onClicked:pane.collapseRequested()}
        }
        Item {
            Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:100
            ScrollView {
                id:conversation;objectName:"topbarConversationScroll";anchors.fill:parent;clip:true
                contentWidth:availableWidth;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                onContentHeightChanged:if(pane.following)Qt.callLater(pane.followLatest)
                ScrollBar.vertical:ScrollBar {id:scrollbar;onPressedChanged:if(pressed)pane.following=false}
                Connections {target:conversation.contentItem;function onMovementStarted(){pane.following=false}function onMovementEnded(){pane.following=conversation.contentHeight-conversation.contentItem.contentY-conversation.availableHeight<28}}
                ColumnLayout {
                    width:conversation.availableWidth;spacing:24
                    Label {visible:!pane.controller.messages.length;Layout.fillWidth:true;text:pane.translate("Wobei kann ich dir helfen?");color:pane.colors.text;font.pixelSize:24;wrapMode:Text.Wrap}
                    Repeater {
                        model:pane.controller.messages.length
                        ColumnLayout {
                            id:message;required property int index
                            readonly property var row:pane.controller.messages[index]||({})
                            readonly property bool user:row.role==="user"
                            Layout.fillWidth:true;Layout.leftMargin:user?32:0;spacing:12
                            RowLayout {spacing:8
                                Kirigami.Icon {visible:!message.user;source:"qrc:/lumen/symbols/halo.svg";isMask:true;color:pane.colors.accent;Layout.preferredWidth:20;Layout.preferredHeight:20}
                                Label {text:message.user?pane.translate("Du"):"Lumen";color:pane.colors.muted;font.pixelSize:12}
                            }
                            TextArea {visible:message.user;Layout.fillWidth:true;text:message.row.body||"";textFormat:TextEdit.RichText;readOnly:true;selectByMouse:true;wrapMode:TextEdit.Wrap;font.pixelSize:pane.controller.theme.fontSize;color:pane.colors.text;background:Rectangle {radius:10;color:pane.colors.base} padding:14;onLinkActivated:link=>pane.controller.open_link(link)}
                            Search.AnswerBlocks {visible:!message.user;Layout.fillWidth:true;blocks:message.row.blocks||[];theme:pane.controller.theme;controller:pane.controller;messageKey:message.row.key||""}
                            Loader {Layout.fillWidth:true;active:!!message.row.presentation;visible:active
                                sourceComponent:Search.ResultView {view:pane.controller.richView;theme:pane.controller.theme;onDialogVisibleChanged:pane.dialogVisible=dialogVisible;Component.onDestruction:pane.dialogVisible=false}
                            }
                            RowLayout {visible:!!message.row.actions && !pane.controller.busy;Layout.fillWidth:true
                                BarButton {colors:pane.colors;text:pane.translate("Kopieren");glyph:"edit-copy";onClicked:pane.controller.model.call("copy")}
                                BarButton {colors:pane.colors;text:pane.translate("Für mich speichern");glyph:"bookmark-new";onClicked:pane.controller.model.call("save",[false])}
                            }
                        }
                    }
                    Repeater {model:pane.controller.permissions
                        ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:12
                            Label {text:pane.translate("Aktion erlauben?");color:pane.colors.text;font.pixelSize:16}
                            Label {Layout.fillWidth:true;text:modelData.label+"\n"+(modelData.patterns||[]).join("\n");textFormat:Text.PlainText;wrapMode:Text.WrapAnywhere;color:pane.colors.muted}
                            RowLayout {
                                BarButton {colors:pane.colors;text:pane.translate("Ablehnen");onClicked:pane.controller.permission_reply(parent.parent.modelData.id,false)}
                                BarButton {colors:pane.colors;text:pane.translate("Einmal erlauben");primary:true;onClicked:pane.controller.permission_reply(parent.parent.modelData.id,true)}
                            }
                        }
                    }
                    Repeater {model:pane.controller.questions;Search.QuestionCard {required property var modelData;controller:pane.controller;request:modelData;Layout.fillWidth:true}}
                    Label {visible:!!text;Layout.fillWidth:true;text:pane.request.error||pane.controller.error;textFormat:Text.PlainText;wrapMode:Text.Wrap;color:pane.colors.text}
                    BarButton {visible:!!pane.controller.data.voiceSetupRequired;colors:pane.colors;text:pane.translate("Sprache einrichten");onClicked:pane.controller.model.call("voice_setup")}
                    ColumnLayout {Layout.fillWidth:true;spacing:8;visible:(pane.controller.data.steps||[]).length>0
                        property bool expanded:false
                        BarButton {objectName:"conversationSteps";colors:pane.colors;text:(pane.controller.data.steps||[]).length+" "+pane.translate((pane.controller.data.steps||[]).length===1?"Arbeitsschritt":"Arbeitsschritte");glyph:parent.expanded?"arrow-up":"arrow-down";onClicked:{parent.expanded=!parent.expanded;if(parent.expanded)Qt.callLater(pane.latest)}}
                        Label {visible:parent.expanded;Layout.fillWidth:true;text:(pane.controller.data.steps||[]).map(s=>s.title+" · "+s.status).join("\n");textFormat:Text.PlainText;wrapMode:Text.Wrap;color:pane.colors.muted}
                    }
                    Label {visible:pane.controller.busy||pane.request.pending;Layout.fillWidth:true;text:pane.request.pending?pane.translate("Frage wird gesendet …"):pane.controller.status;color:pane.colors.muted;wrapMode:Text.Wrap}
                }
            }
            BarButton {objectName:"conversationLatest";visible:!pane.following;anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom;colors:pane.colors;text:pane.translate("Zur neuesten Nachricht");glyph:"arrow-down";onClicked:pane.latest()}
        }
        Rectangle {
            Layout.fillWidth:true;implicitHeight:composerBox.implicitHeight+24;radius:12;color:pane.colors.base;border.color:composer.activeFocus?pane.colors.accent:pane.colors.border
            ColumnLayout {id:composerBox;anchors.fill:parent;anchors.margins:12;spacing:8
                TextArea {id:composer;objectName:"conversationComposer";Layout.fillWidth:true;Layout.maximumHeight:140;wrapMode:TextEdit.Wrap;placeholderText:pane.translate("Weiter mit Lumen besprechen …");Accessible.name:placeholderText;color:pane.colors.text;selectByMouse:true;font.pixelSize:pane.controller.theme.fontSize;background:null;padding:0
                    Binding {target:composer;property:"text";value:pane.request.draft}
                    onTextChanged:if(pane.request.draft!==text)pane.request.draft=text
                    Keys.onReturnPressed:event=>{if(!(event.modifiers&Qt.ShiftModifier)){pane.submit();event.accepted=true}else event.accepted=false}
                }
                RowLayout {Layout.fillWidth:true
                    Label {text:pane.controller.data.voiceActive?pane.controller.data.voiceStatus:pane.translate("Dieses Gespräch");color:pane.colors.muted;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:12}
                    BarButton {objectName:"conversationDictate";colors:pane.colors;glyph:"microphone-sensitivity-high";text:pane.translate("Diktieren");iconOnly:true;onClicked:pane.controller.model.call("voice")}
                    BarButton {objectName:"conversationSend";colors:pane.colors;glyph:pane.controller.busy?"media-playback-stop":"go-up";text:pane.translate(pane.controller.busy?"Abbrechen":"Senden");primary:true;iconOnly:true;enabled:pane.controller.busy||(!pane.request.pending&&!!pane.request.draft.trim());onClicked:pane.controller.busy?pane.controller.model.call("stop"):pane.submit()}
                }
            }
        }
        Item {Layout.preferredHeight:8}
    }
}
