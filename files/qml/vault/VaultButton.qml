import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    required property var theme
    property string glyph: ""
    property bool primary: false
    property bool quiet: false
    property bool selected: false
    font.family: theme.fontFamily
    font.pixelSize: theme.fontSize - 1
    implicitHeight: 44
    leftPadding: 15; rightPadding: 15
    icon.source: glyph ? "icons/" + glyph + ".svg" : ""
    icon.width: 21; icon.height: 21
    icon.color: primary ? theme.onAccent : selected ? theme.accent : theme.text
    palette.buttonText: primary ? theme.onAccent : theme.text
    background: Rectangle {
        radius: Math.min(control.theme.radius, 10)
        color: control.primary ? control.theme.accent : control.down || control.selected ? control.theme.hover
               : control.hovered ? control.theme.button : control.quiet ? "transparent" : control.theme.button
        border.width: control.visualFocus ? 2 : control.quiet && !control.selected ? 0 : 1
        border.color: control.visualFocus ? control.theme.accent : control.theme.border
        opacity: control.enabled ? 1 : 0.45
    }
    Accessible.name: text || ToolTip.text
    ToolTip.delay: 700
    ToolTip.visible: hovered && ToolTip.text.length > 0
}
