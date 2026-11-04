import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Button {
    id: control
    required property var colors
    property string glyph: ""
    property bool iconOnly: false
    property int textSize: 14
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    leftPadding: 9; rightPadding: 9; topPadding: 6; bottomPadding: 6
    implicitHeight: Math.max(36, label.implicitHeight+12)
    implicitWidth: row.implicitWidth+leftPadding+rightPadding
    Accessible.name: text
    background: Rectangle {
        radius: 7
        color: control.down || control.hovered || control.highlighted ? control.colors.alternate : "transparent"
        border.width: control.visualFocus ? 2 : 0
        border.color: control.colors.accent
    }
    contentItem: Row {
        id: row; spacing: 7
        Kirigami.Icon {source: control.glyph;visible: !!control.glyph;width:22;height:22;anchors.verticalCenter:parent.verticalCenter;color:control.colors.text;isMask:false}
        Text {id:label;text:control.text;visible:!control.iconOnly;color:control.enabled?control.colors.text:control.colors.muted;font:control.font;anchors.verticalCenter:parent.verticalCenter;textFormat:Text.PlainText}
    }
    ToolTip.visible: hovered && iconOnly
    ToolTip.text: text
    ToolTip.delay: 650
}
