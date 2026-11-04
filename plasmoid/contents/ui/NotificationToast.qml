pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import "Translations.js" as I18n

PlasmaCore.Dialog {
    id: toast
    property var notice: null
    property string uiLanguage: "de"
    property var anchorItem: null
    signal action(string identity, string operation)
    signal centerRequested()
    function tr(text) { return I18n.tr(text,uiLanguage); }
    function present(row) { notice=row; visible=true; lifetime.restart(); }
    function dismiss() { visible=false; notice=null; lifetime.stop(); }
    title: "Lumen Notification"
    type: PlasmaCore.Dialog.Notification
    flags: Qt.WindowDoesNotAcceptFocus | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    location: PlasmaCore.Types.Floating
    backgroundHints: PlasmaCore.Types.NoBackground
    visible:false
    x:Screen.virtualX+Screen.width-width-24
    y:Screen.virtualY+76
    mainItem: Rectangle {
        color: Kirigami.Theme.backgroundColor; radius: 18
        border.width: 1; border.color: Qt.alpha(Kirigami.Theme.textColor,0.16)
        width: 392; height: content.implicitHeight+36
        HoverHandler { id: hover }
        ColumnLayout {
            id: content; anchors.fill: parent; anchors.margins: 18; spacing: 10
            RowLayout {
                LumenIcon { name: "lumen"; color: Kirigami.Theme.highlightColor; Layout.preferredWidth: 24; Layout.preferredHeight: 24 }
                PC.Label { text: "Lumen Notification"; Layout.fillWidth: true; font.pixelSize: 12; color: Qt.alpha(Kirigami.Theme.textColor,0.68) }
                LumenButton { flat: true; implicitHeight: 28; icon.name: "window-close"; Accessible.name: toast.tr("Popup schließen"); onClicked: toast.dismiss() }
            }
            PC.Label { text: toast.notice ? toast.notice.title : ""; color: Kirigami.Theme.textColor; textFormat: Text.PlainText; font.pixelSize: 17; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
            PC.Label { text: toast.notice ? toast.notice.body : ""; color: Kirigami.Theme.textColor; textFormat: Text.PlainText; visible: text!==""; font.pixelSize: 14; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
            PC.Label { text: toast.notice ? toast.notice.source : ""; textFormat: Text.PlainText; font.pixelSize: 12; color: Qt.alpha(Kirigami.Theme.textColor,0.68); Layout.fillWidth: true; elide: Text.ElideRight }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: toast.notice ? toast.notice.actions.slice(0,2) : []
                    delegate: LumenButton {
                        required property var modelData
                        objectName: "notificationToastAction"
                        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.maximumWidth: 150; text: modelData.label; prominent: true
                        onClicked: { toast.action(toast.notice.id,modelData.key); Qt.callLater(toast.dismiss); }
                    }
                }
                LumenButton { flat: true; text: toast.tr("Zentrale"); onClicked: {toast.dismiss();toast.centerRequested();} }
            }
        }
    }
    property Timer expiryTimer: Timer { id: lifetime; interval: 8000; running: toast.visible && !hover.hovered; onTriggered: toast.dismiss() }
}
