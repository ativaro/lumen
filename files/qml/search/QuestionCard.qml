pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    required property var controller
    required property var request
    readonly property var theme: controller.theme
    property var answers: ({})
    implicitHeight: body.implicitHeight + 32
    color: theme.button; radius: theme.radius
    border.color: Qt.alpha(theme.accent, 0.45)
    ColumnLayout {
        id: body
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 16; spacing: 12
        Repeater {
            model: card.request.questions
            ColumnLayout {
                id: question
                required property var modelData
                required property int index
                Layout.fillWidth: true; spacing: 6
                property var choices: []
                function publish() {
                    var values = choices.slice()
                    if (custom.visible && custom.text.trim()) {
                        if (!modelData.multiple) values = []
                        values.push(custom.text.trim())
                    }
                    card.answers[index] = values
                }
                function choose(label, checked) {
                    choices = choices.filter(function(value) { return value !== label })
                    if (checked) choices = modelData.multiple ? choices.concat([label]) : [label]
                    publish()
                }
                Label { text: question.modelData.question; Layout.fillWidth: true; wrapMode: Text.Wrap; color: card.theme.text; font.pixelSize: 14; font.weight: Font.Medium; textFormat: Text.PlainText }
                ButtonGroup { id: optionsGroup; exclusive: !question.modelData.multiple }
                Repeater {
                    model: question.modelData.options || []
                    CheckBox {
                        id: choice
                        objectName: "choice-" + card.request.id + "-" + question.index + "-" + modelData.label
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData.label; ButtonGroup.group: optionsGroup
                        palette.windowText: card.theme.text; palette.highlight: card.theme.accent
                        contentItem: Label { leftPadding: 30; text: choice.text; color: card.theme.text; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        onToggled: question.choose(modelData.label, checked)
                        ToolTip.visible: hovered && (modelData.description || "").length > 0
                        ToolTip.text: modelData.description || ""
                    }
                }
                TextField {
                    id: custom
                    objectName: "question-" + card.request.id + "-" + question.index
                    Layout.fillWidth: true; visible: question.modelData.custom !== false
                    placeholderText: card.controller.text("Eigene Antwort")
                    color: card.theme.text; placeholderTextColor: card.theme.muted
                    selectByMouse: true; font.pixelSize: 14; padding: 10; implicitHeight: 40
                    background: Rectangle { color: card.theme.base; radius: 8; border.color: custom.activeFocus ? card.theme.accent : card.theme.border }
                    onTextEdited: question.publish()
                    Accessible.name: placeholderText + ": " + question.modelData.question
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            LumenButton { theme: card.theme; quiet: true; text: card.controller.text("Überspringen"); onClicked: card.controller.skip_question(card.request.id) }
            Item { Layout.fillWidth: true }
            LumenButton {
                objectName: "reply-" + card.request.id
                theme: card.theme; primary: true; text: card.controller.text("Antwort senden")
                onClicked: {
                    var values = []
                    for (var i = 0; i < card.request.questions.length; i++) values.push(card.answers[i] || [])
                    card.controller.question_reply(card.request.id, values)
                }
            }
        }
    }
}
