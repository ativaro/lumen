import QtQuick
import QtQuick.Layouts
Rectangle {
    id: card
    required property var theme
    required property var metric
    required property int seconds
    radius: theme.radius; color: Qt.alpha(theme.base, .78)
    border.color: Qt.alpha(theme.border, .45); implicitHeight: 190
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 22; spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Text { text: metric.title; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.fontSize-1; Layout.fillWidth: true }
            Text { text: ({cpu:'CPU',gpu:'GPU',memory:'RAM',disk:'DISK'})[metric.key]; color: theme.accent; font.pixelSize: 11; font.letterSpacing: 1.5 }
        }
        Text { text: metric.value; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 33; font.weight: Font.DemiBold }
        Text { text: metric.name; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.fontSize-3; elide: Text.ElideRight; Layout.fillWidth: true }
        Item { Layout.fillHeight: true }
        Trend { visible: metric.key !== 'disk'; Layout.fillWidth: true; Layout.preferredHeight: 32; points: metric.series; colors: [theme.accent]; seconds: card.seconds }
        Rectangle {
            visible: metric.key === 'disk'; Layout.fillWidth: true; Layout.preferredHeight: 5; radius: 3; color: theme.hover
            Rectangle { width: parent.width * (metric.percent || 0)/100; height: parent.height; radius: 3; color: theme.accent }
        }
        Text { text: metric.detail; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.fontSize-3; elide: Text.ElideRight; Layout.fillWidth: true }
    }
    Accessible.role: Accessible.StaticText
    Accessible.name: metric.title + ': ' + metric.value + '. ' + metric.name + '. ' + metric.detail
}
