import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id:composer
    required property var colors
    required property var translate
    required property var controller
    property bool keyStyle:false
    readonly property bool editing:input.activeFocus
    required property var request
    readonly property bool pending:request.pending
    readonly property bool busy:!!controller.conversation.state.busy
    signal sent()
    signal inspectAttachment()
    signal voiceRequested()
    signal inputRequested()
    implicitHeight:keyStyle?44:36
    implicitWidth:row.implicitWidth
    Rectangle {z:-1;anchors.fill:parent;visible:composer.keyStyle;radius:composer.colors.radius||8;color:composer.colors.inset||composer.colors.base;border.color:input.activeFocus?composer.colors.accent:composer.colors.border}
    function focusInput(){input.forceActiveFocus()}
    function submit(){
        if(!input.text.trim() || pending || busy)return
        request.error="";request.submitted=input.text;request.submittedNote=JSON.stringify(request.note);request.pending=true
        request.pendingAction=controller.ask(request.submitted,request.note)
    }
    function setPrompt(value){request.draft=value;focusInput()}
    Binding {target:input;property:"text";value:composer.request.draft}
    RowLayout {
        id:row;anchors.fill:parent;spacing:1
        BarButton {objectName:"inspectAttachmentButton";visible:!!composer.request.note.reference;colors:composer.colors;glyph:"mail-attachment";text:translate("Angehängte Quelle")+": "+(composer.request.note.reference?.title || "");iconOnly:true;onClicked:composer.inspectAttachment()}
        TextField {
            id:input;objectName:"lumenQuestion"
            onPressed:composer.inputRequested()
            onTextChanged:if(composer.request.draft!==text)composer.request.draft=text
            Layout.fillWidth:true;Layout.minimumWidth:0
            placeholderText:translate("Frag Lumen oder erledige etwas …");Accessible.name:translate("Neue Frage an Lumen")
            maximumLength:4000;selectByMouse:true;onAccepted:composer.submit()
            palette.text:composer.colors.text;palette.placeholderText:composer.colors.muted
            background:Rectangle {color:composer.keyStyle?"transparent":composer.colors.base;radius:7;border.width:composer.keyStyle?0:1;border.color:input.activeFocus?composer.colors.accent:composer.colors.border}
        }
        BarButton {objectName:"dictateButton";colors:composer.colors;glyph:"microphone-sensitivity-high";text:translate("Mit Lumen sprechen");iconOnly:true;onClicked:{composer.voiceRequested();controller.conversation.call("voice")}}
        BarButton {objectName:"sendQuestionButton";primary:true;colors:composer.colors;glyph:"go-up";text:translate("Frage senden");iconOnly:true;visible:!!input.text.trim()||composer.pending;enabled:!composer.pending && !composer.busy && !!input.text.trim();onClicked:composer.submit()}
    }
    Connections {
        target:composer.controller
        function onControlFinished(action,value){
            if(action!==composer.request.pendingAction || !composer.pending)return
            const request=composer.request;request.pending=false;request.error=""
            if(request.draft===request.submitted && JSON.stringify(request.note)===request.submittedNote){request.draft="";request.note=({});composer.sent()}
        }
        function onControlFailed(action){if(action===composer.request.pendingAction){composer.request.pending=false;composer.request.error=composer.controller.error}}
    }
}
