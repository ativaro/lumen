import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id:composer
    required property var colors
    required property var translate
    required property var controller
    readonly property bool editing:input.activeFocus
    property bool pending:false
    property string submitted:""
    signal sent()
    spacing:1
    function focusInput(){input.forceActiveFocus()}
    function submit(){
        if(!input.text.trim() || pending)return
        submitted=input.text;pending=true;controller.ask(submitted)
    }
    BarButton {objectName:"searchLumenButton";colors:composer.colors;glyph:"search";text:translate("Lumen fragen oder suchen");iconOnly:true;onClicked:controller.launch("search")}
    TextField {
        id:input;objectName:"lumenQuestion"
        Layout.fillWidth:true;Layout.minimumWidth:0
        placeholderText:translate("Frag Lumen …");Accessible.name:translate("Neue Frage an Lumen")
        maximumLength:4000;selectByMouse:true;onAccepted:composer.submit()
        palette.text:composer.colors.text;palette.placeholderText:composer.colors.muted
        background:Rectangle {color:composer.colors.base;radius:7;border.color:input.activeFocus?composer.colors.accent:composer.colors.border}
    }
    BarButton {objectName:"dictateButton";colors:composer.colors;glyph:"microphone-sensitivity-high";text:translate("Mit Lumen sprechen");iconOnly:true;onClicked:controller.launch("voice")}
    BarButton {objectName:"sendQuestionButton";colors:composer.colors;glyph:"go-up";text:translate("Frage senden");iconOnly:true;enabled:!composer.pending && !!input.text.trim();onClicked:composer.submit()}
    Connections {
        target:composer.controller
        function onControlFinished(action,value){if(action==="ask" && composer.pending){composer.pending=false;if(input.text===composer.submitted)input.clear();composer.sent()}}
        function onControlFailed(action){if(action==="ask")composer.pending=false}
    }
}
