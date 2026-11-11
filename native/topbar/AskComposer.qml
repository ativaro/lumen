import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id:composer
    required property var colors
    required property var translate
    required property var controller
    property bool keyStyle:false
    // The inline bar owns the docked conversation; popups have none to toggle.
    property bool showToggle:false
    property bool conversationOpen:false
    readonly property bool editing:input.activeFocus
    required property var request
    readonly property bool pending:request.pending
    readonly property var conversation:controller.conversation.state||({})
    readonly property bool busy:!!conversation.busy
    readonly property bool listening:!!conversation.voiceActive
    readonly property bool failed:!!request.error && !pending
    signal sent()
    signal inspectAttachment()
    signal voiceRequested()
    signal inputRequested()
    signal toggleRequested()
    implicitHeight:keyStyle?44:36
    implicitWidth:row.implicitWidth+16
    HoverHandler {id:pointer}
    Rectangle {
        z:-1;anchors.fill:parent;radius:composer.keyStyle?(composer.colors.radius||8):(composer.colors.innerRadius||7)
        color:composer.keyStyle?(composer.colors.inset||composer.colors.base):composer.colors.base
        border.width:input.activeFocus || composer.failed?2:1
        border.color:composer.failed?composer.colors.text:input.activeFocus?composer.colors.accent:pointer.hovered?composer.colors.muted:composer.colors.border
    }
    function focusInput(){input.forceActiveFocus()}
    function submit(){
        if(!input.text.trim() || pending || busy)return
        request.error="";request.submitted=input.text;request.submittedNote=JSON.stringify(request.note);request.pending=true
        request.pendingAction=controller.ask(request.submitted,request.note)
    }
    function setPrompt(value){request.draft=value;focusInput()}
    Binding {target:input;property:"text";value:composer.request.draft}
    RowLayout {
        id:row;anchors.fill:parent;anchors.leftMargin:composer.request.note.reference?4:12;anchors.rightMargin:4;spacing:4
        Kirigami.Icon {visible:!composer.request.note.reference;source:composer.failed?"dialog-warning":composer.busy?"qrc:/lumen/icons/lumen-mark.svg":"search";isMask:!composer.failed;color:composer.busy?(composer.colors.ring||composer.colors.accent):composer.colors.muted;implicitWidth:16;implicitHeight:16;Layout.rightMargin:4}
        BarButton {objectName:"inspectAttachmentButton";compact:true;current:true;visible:!!composer.request.note.reference;colors:composer.colors;glyph:"mail-attachment";text:(composer.request.note.reference?.title || translate("Angehängte Quelle"));Accessible.name:translate("Angehängte Quelle")+": "+(composer.request.note.reference?.title || "");iconOnly:composer.width<420;Layout.maximumWidth:220;onClicked:composer.inspectAttachment()}
        BarButton {objectName:"removeAttachmentButton";compact:true;visible:!!composer.request.note.reference && !composer.pending;colors:composer.colors;glyph:"window-close";text:translate("Notiz entfernen");iconOnly:true;onClicked:composer.request.note=({})}
        TextField {
            id:input;objectName:"lumenQuestion"
            onPressed:composer.inputRequested()
            onTextChanged:if(composer.request.draft!==text)composer.request.draft=text
            Layout.fillWidth:true;Layout.minimumWidth:0
            leftPadding:0;rightPadding:0
            readOnly:composer.pending
            placeholderText:composer.listening?translate("Ich höre zu …"):composer.busy?translate("Lumen arbeitet")+(composer.conversation.title?" · "+composer.conversation.title:""):translate("Frag Lumen oder erledige etwas …")
            Accessible.name:translate("Neue Frage an Lumen")
            maximumLength:4000;selectByMouse:true;onAccepted:composer.submit()
            palette.text:composer.pending?composer.colors.muted:composer.colors.text;palette.placeholderText:composer.colors.muted
            background:Item {}
        }
        Label {visible:composer.pending;text:translate("Wird gesendet …");color:composer.colors.muted;font.pixelSize:12;textFormat:Text.PlainText}
        BusyIndicator {visible:composer.pending;running:visible;implicitWidth:20;implicitHeight:20}
        BarButton {objectName:"retryQuestionButton";compact:true;visible:composer.failed && !!input.text.trim();colors:composer.colors;text:translate("Erneut senden");onClicked:composer.submit()}
        BarButton {objectName:"dictateButton";compact:true;visible:!composer.pending;colors:composer.colors;glyph:"microphone-sensitivity-high";text:composer.listening?translate("Diktat läuft"):translate("Mit Lumen sprechen");iconOnly:true;primary:composer.listening;onClicked:{composer.voiceRequested();controller.conversation.call("voice")}}
        BarButton {objectName:composer.showToggle?"conversationToggle":"";compact:true;visible:composer.showToggle;colors:composer.colors;current:composer.conversationOpen;glyph:composer.conversationOpen?"arrow-up":"arrow-down";text:translate(composer.conversationOpen?"Gespräch einklappen":"Gespräch aufklappen");iconOnly:true;onClicked:composer.toggleRequested()}
        BarButton {objectName:"stopQuestionButton";compact:true;visible:composer.busy && !composer.pending;colors:composer.colors;glyph:"media-playback-stop";text:translate("Abbrechen");iconOnly:true;onClicked:controller.conversation.call("stop")}
        BarButton {objectName:"sendQuestionButton";compact:true;primary:true;colors:composer.colors;glyph:"go-up";text:translate("Frage senden");iconOnly:true;visible:!!input.text.trim() && !composer.pending && !composer.failed;enabled:!composer.busy;onClicked:composer.submit()}
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
