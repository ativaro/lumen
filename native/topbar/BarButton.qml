import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Button {
    id: control
    required property var colors
    property var glyph: ""
    property bool iconOnly: false
    property bool key: false
    property bool current: false
    property bool primary: false
    property bool monochrome: false
    property bool compact: false
    property bool outlined: false
    property string symbol: ""
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    leftPadding: compact?6:9; rightPadding: compact?6:9; topPadding: compact?3:6; bottomPadding: compact?3:6
    implicitHeight: compact?28:Math.max(key?44:36, label.implicitHeight+12)
    readonly property int glyphSize: compact?16:22
    readonly property real naturalWidth:leftPadding+rightPadding+(symbol?33:glyph?glyphSize+7:0)+label.implicitWidth
    implicitWidth:iconOnly?leftPadding+rightPadding+(glyph||symbol?glyphSize:0):naturalWidth
    Accessible.name: text
    background: Item {
        readonly property bool pressed:control.down || control.current || control.highlighted
        Rectangle {visible:control.key;anchors.fill:parent;anchors.topMargin:2;anchors.bottomMargin:-2;radius:control.colors.radius||8;color:control.colors.shadow||"#65000000"}
        Rectangle {
            anchors.fill:parent;anchors.topMargin:control.key && parent.pressed?1:0
            radius:control.key?(control.colors.radius||8):Math.max(3,(control.colors.innerRadius||7)-(control.compact?2:0))
            color:control.primary && control.enabled?control.colors.accent:control.key?(parent.pressed?(control.colors.inset||control.colors.base):(control.colors.key||control.colors.window)):(parent.pressed?control.colors.alternate:"transparent")
            border.width:control.visualFocus?2:control.key || control.outlined || (control.enabled && control.hovered && !control.down)?1:0
            border.color:control.visualFocus || (control.enabled && control.hovered && !control.down)?control.colors.accent:control.colors.border
            Behavior on border.color {ColorAnimation {duration:Kirigami.Units.shortDuration}}
            Rectangle {visible:control.key;anchors.top:parent.top;anchors.topMargin:1;anchors.horizontalCenter:parent.horizontalCenter;width:parent.width-12;height:1;color:control.colors.highlight||"#12ffffff"}
            Rectangle {
                anchors.fill:parent;radius:parent.radius
                color:control.primary?control.colors.onAccent:control.colors.text
                opacity:control.enabled && control.hovered && !control.down?0.07:0
                Behavior on opacity {NumberAnimation {duration:Kirigami.Units.shortDuration}}
            }
            Rectangle {visible:control.key && control.current;anchors.bottom:parent.bottom;anchors.bottomMargin:4;anchors.horizontalCenter:parent.horizontalCenter;width:16;height:2;radius:1;color:control.colors.accent}
        }
    }
    contentItem: Row {
        id: row; spacing: 7
        Item {visible:!!control.symbol;width:26;height:26;anchors.verticalCenter:parent.verticalCenter
            Kirigami.Icon {anchors.fill:parent;source:"qrc:/lumen/symbols/halo.svg";isMask:true;color:control.colors.ring||control.colors.accent}
            Kirigami.Icon {anchors.fill:parent;source:control.symbol?"qrc:/lumen/symbols/lumen-"+control.symbol+".svg":"";isMask:true;color:control.colors.ink||control.colors.text}
        }
        Kirigami.Icon {source: control.glyph;visible: !!control.glyph && !control.symbol;width:control.glyphSize;height:control.glyphSize;anchors.verticalCenter:parent.verticalCenter;color:control.glyph==="qrc:/lumen/icons/lumen-mark.svg"?(control.colors.ring||control.colors.accent):control.primary && control.enabled?control.colors.onAccent:control.colors.text;isMask:control.monochrome || control.primary || control.glyph==="qrc:/lumen/icons/lumen-mark.svg"}
        Text {id:label;text:control.text;visible:!control.iconOnly;width:Math.max(0,control.availableWidth-(control.symbol?33:control.glyph?control.glyphSize+7:0));elide:Text.ElideRight;color:control.enabled?(control.primary?control.colors.onAccent:control.colors.text):control.colors.muted;font:control.font;anchors.verticalCenter:parent.verticalCenter;textFormat:Text.PlainText}
    }
    function updateTip(){
        tipDelay.stop();panelData.tooltip(control,"")
        if(visible && enabled && hovered && !down && text)tipDelay.start()
    }
    Timer {id:tipDelay;interval:400;onTriggered:panelData.tooltip(control,control.text)}
    onHoveredChanged:updateTip()
    onDownChanged:updateTip()
    onEnabledChanged:updateTip()
    onVisibleChanged:updateTip()
    onTextChanged:if(hovered)updateTip()
}
