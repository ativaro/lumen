pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: answer
    required property var blocks
    required property var theme
    required property var controller
    required property string messageKey
    property int checkRevision: 0
    function isChecked(item) {
        const revision = checkRevision
        return controller.answer_item_checked(messageKey, item.key, item.checked)
    }
    Connections {
        target: answer.controller
        function onAnswerChecksChanged() { answer.checkRevision += 1 }
    }
    spacing: 16
    Repeater {
        model: answer.blocks
        Frame {
            id: block
            required property var modelData
            readonly property bool prose: modelData.kind === "text"
            Layout.fillWidth: true
            padding: prose ? 0 : 16
            background: Rectangle {
                visible: !block.prose; radius: 12
                color: Qt.alpha(answer.theme.base, 0.8)
                border.color: Qt.alpha(answer.theme.border, 0.8)
            }
            contentItem: ColumnLayout {
                spacing: 12
                RowLayout {
                    visible: !block.prose; Layout.fillWidth: true
                    Label {
                        Layout.fillWidth: true; text: block.modelData.title || ""
                        textFormat: Text.PlainText; wrapMode: Text.Wrap
                        color: answer.theme.text; font.pixelSize: answer.theme.fontSize - 2; font.weight: Font.DemiBold
                    }
                    Label {
                        visible: block.modelData.kind === "checklist"
                        text: (block.modelData.items || []).filter(x => answer.isChecked(x)).length + " / " + (block.modelData.items || []).length
                        color: answer.theme.muted; font.pixelSize: 12
                        Accessible.name: answer.controller.text("Checkliste") + " " + text
                    }
                }
                TextArea {
                    id: body
                    objectName: "answerBlockText"
                    visible: block.modelData.kind !== "checklist"
                    Layout.fillWidth: true
                    text: block.modelData.kind === "table" ? answer.controller.answer_table(block.modelData, width) : (block.modelData.body || "")
                    textFormat: TextEdit.RichText; readOnly: true; selectByMouse: true
                    wrapMode: TextEdit.Wrap; color: answer.theme.text
                    font.pixelSize: answer.theme.fontSize
                    font.family: block.modelData.kind === "code" ? "monospace" : answer.theme.fontFamily
                    background: null; padding: 0
                    onLinkActivated: function(link) { answer.controller.open_link(link) }
                }
                Repeater {
                    model: block.modelData.items || []
                    RowLayout {
                        id: task
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: Math.min(task.modelData.indent, 4) * 16
                        spacing: 10
                        CheckBox {
                            objectName: "answerCheck"
                            Layout.alignment: Qt.AlignTop
                            checked: answer.isChecked(task.modelData)
                            Accessible.name: task.modelData.text
                            padding: 0; implicitWidth: 24; implicitHeight: 28
                            indicator: Rectangle {
                                x: 2; y: 4; width: 18; height: 18; radius: 5
                                color: parent.checked ? answer.theme.accent : "transparent"
                                border.color: parent.activeFocus ? answer.theme.accent : answer.theme.muted
                                border.width: parent.activeFocus ? 2 : 1
                                Label { anchors.centerIn: parent; text: "✓"; visible: answer.isChecked(task.modelData); color: answer.theme.onAccent; font.pixelSize: 14 }
                            }
                            onClicked: answer.controller.check_answer_item(answer.messageKey, task.modelData.key, checked)
                        }
                        TextArea {
                            Layout.fillWidth: true; text: task.modelData.body
                            textFormat: TextEdit.RichText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                            color: answer.isChecked(task.modelData) ? answer.theme.muted : answer.theme.text
                            font.pixelSize: answer.theme.fontSize; background: null; padding: 0; topPadding: 3
                            onLinkActivated: function(link) { answer.controller.open_link(link) }
                        }
                    }
                }
                Label {
                    visible: block.modelData.kind === "checklist"; Layout.fillWidth: true
                    text: answer.controller.text("Abhaken führt keine Aktion aus.")
                    wrapMode: Text.Wrap; color: answer.theme.muted; font.pixelSize: 12
                }
            }
        }
    }
}
