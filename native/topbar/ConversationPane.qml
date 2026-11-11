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
    // True only while this pane moves the view itself, so its own jumps are not read as the user scrolling.
    property bool jumping:false
    signal detachRequested(bool dragging)
    signal collapseRequested()
    signal reattachRequested()
    function focusInput(){composer.forceActiveFocus()}
    function submit(){if(!request.draft.trim()||request.pending||controller.busy)return;following=true;request.error="";request.submitted=request.draft;request.submittedNote=JSON.stringify(request.note);request.pending=true;request.pendingAction=host.ask(request.submitted,request.note)}
    function latest(){if(conversation.contentItem){following=true;jumping=true;conversation.contentItem.cancelFlick();conversation.contentItem.contentY=Math.max(0,conversation.contentHeight-conversation.availableHeight);jumping=false}}
    function followLatest(){if(following&&!scrollbar.pressed&&!conversation.contentItem.moving)latest()}
    onWidthChanged:if(visible)widthTimer.restart()
    onVisibleChanged:visible?widthTimer.restart():widthTimer.stop()
    Timer {id:widthTimer;interval:150;onTriggered:if(pane.visible&&pane.width>=168)pane.controller.model.call("width",[Math.min(712,pane.width-48)])}
    Connections {target:pane.controller;function onDataChanged(){if(pane.following)Qt.callLater(pane.followLatest)}}
    readonly property var steps:controller.data.steps||[]
    property bool stepsClosed:false
    // Message bubbles are rounded like a chat, with one tighter corner pointing at the speaker.
    readonly property int bubbleRadius:18
    readonly property int bubbleTail:6
    function stepStatus(value){const names={completed:"Erledigt",running:"Läuft",pending:"Wartet",error:"Fehlgeschlagen",failed:"Fehlgeschlagen"};return names[value]?translate(names[value]):(value||"")}
    // Wide docked conversations show the steps beside the answer; otherwise they stay a collapsible line below it.
    readonly property bool sideSteps:!detached && steps.length>0 && !stepsClosed && width>=1100
    readonly property real sideWidth:sideSteps?324:0
    Rectangle {
        visible:!pane.detached;z:-1;anchors.fill:parent;anchors.leftMargin:1;anchors.rightMargin:1;anchors.bottomMargin:1
        color:pane.colors.base;radius:(pane.colors.radius||10)+6;topLeftRadius:0;topRightRadius:0
        Rectangle {width:parent.width;height:1;color:pane.colors.border}
    }
    ColumnLayout {
        id:stepsPanel;objectName:"conversationStepsPanel";visible:pane.sideSteps
        x:mainColumn.x+mainColumn.width+24;y:16;width:300;height:parent.height-32;spacing:12
        RowLayout {Layout.fillWidth:true
            Label {text:pane.translate("Arbeitsschritte");color:pane.colors.muted;font.pixelSize:12;font.weight:Font.Medium;Layout.fillWidth:true}
            BarButton {objectName:"closeConversationSteps";compact:true;colors:pane.colors;glyph:"window-close";text:pane.translate("Arbeitsschritte schließen");iconOnly:true;onClicked:pane.stepsClosed=true}
        }
        ScrollView {Layout.fillWidth:true;Layout.fillHeight:true;clip:true;contentWidth:availableWidth;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            ColumnLayout {width:stepsPanel.width;spacing:12
                Repeater {model:pane.steps.length
                    ColumnLayout {required property int index;readonly property var step:pane.steps[index]||({});Layout.fillWidth:true;spacing:2
                        Label {Layout.fillWidth:true;text:parent.step.title||"";textFormat:Text.PlainText;wrapMode:Text.Wrap;color:pane.colors.text}
                        Label {Layout.fillWidth:true;visible:!!text;text:pane.stepStatus(parent.step.status);textFormat:Text.PlainText;wrapMode:Text.Wrap;color:pane.colors.muted;font.pixelSize:12}
                    }
                }
            }
        }
    }
    ColumnLayout {
        id:mainColumn
        x:(parent.width-width-pane.sideWidth)/2;width:Math.max(0,Math.min(760,parent.width-48-pane.sideWidth));height:parent.height;spacing:16
        RowLayout {
            objectName:"conversationHeader";Layout.fillWidth:true;Layout.minimumHeight:48;Layout.preferredHeight:48;Layout.maximumHeight:48;spacing:12
            Item {objectName:"conversationDragArea";Layout.fillWidth:true;Layout.fillHeight:true
                Label {anchors.verticalCenter:parent.verticalCenter;width:parent.width;text:pane.controller.data.title||pane.translate("Gespräch mit Lumen");color:pane.colors.text;font.pixelSize:18;font.weight:Font.Medium;elide:Text.ElideRight}
                MouseArea {
                    anchors.fill:parent;enabled:!pane.detached
                    property point origin
                    property bool started:false
                    onPressed:mouse=>{origin=Qt.point(mouse.x,mouse.y);started=false}
                    onPositionChanged:mouse=>{
                        if(pressed&&!started&&Math.hypot(mouse.x-origin.x,mouse.y-origin.y)>=Qt.styleHints.startDragDistance){started=true;pane.detachRequested(true)}
                    }
                }
                MouseArea {anchors.fill:parent;enabled:pane.detached;onPressed:pane.Window.window.startSystemMove()}
            }
            BarButton {objectName:"detachConversation";colors:pane.colors;glyph:pane.detached?"pin":"go-up";text:pane.translate(pane.detached?"In Leiste anheften":"Als Fenster öffnen");iconOnly:parent.width<560;onClicked:pane.detached?pane.reattachRequested():pane.detachRequested(false)}
            BarButton {objectName:"newTopbarConversation";colors:pane.colors;glyph:"list-add";text:pane.translate("Neues Gespräch");iconOnly:true;enabled:!pane.controller.busy&&!pane.request.pending;onClicked:pane.controller.model.call("reset")}
            BarButton {objectName:"conversationMinimize";monochrome:true;visible:pane.detached;colors:pane.colors;glyph:"qrc:/lumen/window-controls/minimize.svg";text:pane.translate("Minimieren");iconOnly:true;onClicked:pane.Window.window.showMinimized()}
            BarButton {objectName:"conversationMaximize";monochrome:true;visible:pane.detached;colors:pane.colors;glyph:"qrc:/lumen/window-controls/"+(pane.Window.window?.visibility===Window.Maximized?"restore":"maximize")+".svg";text:pane.translate("Maximieren oder wiederherstellen");iconOnly:true;onClicked:pane.Window.window.visibility===Window.Maximized?pane.Window.window.showNormal():pane.Window.window.showMaximized()}
            BarButton {objectName:"collapseConversation";monochrome:true;colors:pane.colors;glyph:pane.detached?"qrc:/lumen/window-controls/close.svg":"arrow-up";text:pane.translate(pane.detached?"Gespräch schließen":"Gespräch einklappen");iconOnly:true;onClicked:pane.collapseRequested()}
        }
        Item {
            Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:100
            ScrollView {
                id:conversation;objectName:"topbarConversationScroll";anchors.fill:parent;clip:true
                contentWidth:availableWidth;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                onContentHeightChanged:if(pane.following)Qt.callLater(pane.followLatest)
                ScrollBar.vertical:ScrollBar {
                    id:scrollbar;parent:conversation;x:conversation.width-width;height:conversation.availableHeight;policy:ScrollBar.AsNeeded
                    onPressedChanged:if(pressed)pane.following=false
                    contentItem:Rectangle {implicitWidth:6;radius:3;color:pane.colors.muted;opacity:scrollbar.size<1?(scrollbar.pressed||scrollbar.hovered?0.9:0.5):0}
                }
                // Follow new text only while the reader is at the end. Wheels and touchpads move the view without
                // movement signals, so the position itself decides.
                Connections {target:conversation.contentItem;function onContentYChanged(){if(!pane.jumping)pane.following=conversation.contentHeight-conversation.contentItem.contentY-conversation.availableHeight<28}}
                ColumnLayout {
                    width:conversation.availableWidth-14;spacing:24  // leaves the scrollbar its own lane
                    Label {visible:!pane.controller.messages.length;Layout.fillWidth:true;text:pane.translate("Wobei kann ich dir helfen?");color:pane.colors.text;font.pixelSize:24;wrapMode:Text.Wrap}
                    Repeater {
                        model:pane.controller.messages.length
                        ColumnLayout {
                            id:message;required property int index
                            readonly property var row:pane.controller.messages[index]||({})
                            readonly property bool user:row.role==="user"
                            Layout.fillWidth:true;Layout.maximumWidth:mainColumn.width;spacing:12
                            RowLayout {spacing:8;Layout.alignment:message.user?Qt.AlignRight:Qt.AlignLeft
                                Kirigami.Icon {visible:!message.user;source:"qrc:/lumen/symbols/halo.svg";isMask:true;color:pane.colors.accent;Layout.preferredWidth:20;Layout.preferredHeight:20}
                                Label {text:message.user?pane.translate("Deine Nachricht"):"Lumen";color:pane.colors.muted;font.pixelSize:12}
                            }
                            TextArea {visible:message.user;Layout.alignment:Qt.AlignRight;Layout.maximumWidth:Math.min(620,mainColumn.width-32);text:message.row.body||"";textFormat:TextEdit.RichText;readOnly:true;selectByMouse:true;wrapMode:TextEdit.Wrap;font.pixelSize:pane.controller.theme.fontSize;color:pane.colors.text;background:Rectangle {radius:pane.bubbleRadius;bottomRightRadius:pane.bubbleTail;color:pane.colors.alternate} leftPadding:16;rightPadding:16;topPadding:10;bottomPadding:10;onLinkActivated:link=>pane.controller.open_link(link)}
                            Rectangle {
                                visible:!message.user && (message.row.blocks||[]).length>0
                                Layout.fillWidth:true;Layout.rightMargin:32;implicitHeight:answerBlocks.implicitHeight+24
                                radius:pane.bubbleRadius;bottomLeftRadius:pane.bubbleTail;color:pane.detached?pane.colors.base:pane.colors.window
                                Search.AnswerBlocks {id:answerBlocks;x:16;y:12;width:parent.width-32;blocks:message.row.blocks||[];theme:pane.controller.theme;controller:pane.controller;messageKey:message.row.key||""}
                            }
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
                    ColumnLayout {Layout.fillWidth:true;spacing:8;visible:pane.steps.length>0 && !pane.sideSteps
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
            Layout.fillWidth:true;implicitHeight:composerBox.implicitHeight+24;radius:pane.colors.innerRadius||7;color:pane.colors.base;border.color:composer.activeFocus?pane.colors.accent:pane.colors.border
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
