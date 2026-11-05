import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: menu
    required property string topic
    required property var colors
    required property var controller
    required property var translate
    required property bool quiet
    readonly property bool notices:topic==="notifications"
    readonly property var noticeState:controller.noticePreview
    readonly property var detailData:controller.details[topic]||({})
    readonly property var entries:rows()
    readonly property string title:t(({notifications:"Mitteilungen",network:"Netzwerk",audio:"Audio",settings:"Einstellungen"})[topic]||"Lumen")
    signal drill(string key)
    signal dismiss()
    signal toggleQuiet()
    spacing:2
    function t(label){return translate(label)}
    function rows(){
        if(notices)return (noticeState.items||[]).map(n=>({key:n.key,title:n.title,caption:n.source,
            detail:n.body,icon:n.icon,unread:n.unread,time:Qt.formatTime(new Date(n.updated*1000),"hh:mm")}))
        if(topic==="settings")return [
            {key:"network",title:t("Netzwerk"),icon:"network-wireless"},
            {key:"audio",title:t("Audio"),icon:"audio-card"},
            {key:"preferences",title:t("Lumen-Einstellungen"),icon:"settings-configure"}]
        if(topic==="network"){
            const devices=detailData.devices||[]
            const active=types=>devices.filter(d=>types.includes(d.type)&&d.profile && d.profile!=="--").map(d=>d.profile).join(", ")
            return [{key:"1",title:t("WLAN"),detail:active(["wifi"]),icon:"network-wireless"},
                {key:"2",title:t("Kabel & Adapter"),detail:active(["ethernet"]),icon:"network-wired"},
                {key:"3",title:t("VPN & Proxy"),detail:(detailData.profiles||[]).filter(p=>p.active && ["vpn","wireguard"].includes(p.type)).map(p=>p.name).join(", "),icon:"network-vpn"}]
        }
        if(topic==="audio"){
            const device=items=>{const d=(items||[]).find(d=>d.default);return d ? [d.name,d.muted?t("Stumm"):typeof d.volume==="number"?Math.round(d.volume)+" %":""].filter(Boolean).join(" · "):""}
            return [{key:"1",title:t("Ausgabe"),detail:device(detailData.outputs),icon:"audio-volume-high"},
                {key:"2",title:t("Mikrofon"),detail:device(detailData.inputs),icon:"audio-input-microphone"},
                {key:"3",title:t("Apps"),detail:(detailData.playback||[]).map(p=>p.name).slice(0,2).join(", "),icon:"multimedia-player"}]
        }
        return []
    }
    RowLayout {
        Layout.fillWidth:true
        Label {text:menu.title;color:menu.colors.text;font.pixelSize:20;font.weight:Font.Medium;Layout.fillWidth:true}
        BarButton {colors:menu.colors;text:menu.t("Schließen");glyph:"window-close";iconOnly:true;onClicked:menu.dismiss()}
    }
    RowLayout {visible:menu.notices && menu.noticeState.unread>0;Layout.fillWidth:true
        Label {text:menu.noticeState.unread+" "+menu.t("ungelesen");color:menu.colors.muted;Layout.fillWidth:true}
        BarButton {colors:menu.colors;text:menu.t("Alle als gelesen");onClicked:menu.controller.noticeCommand("read")}
    }
    Label {
        Layout.fillWidth:true;visible:menu.notices && !noticeList.count
        text:menu.noticeState.unavailable?menu.t("Kurzansicht derzeit nicht verfügbar."):menu.noticeState.locked?menu.t("Bildschirm gesperrt"):menu.noticeState.items?menu.t("Keine aktuellen Mitteilungen"):menu.t("Mitteilungen werden geladen …")
        color:menu.colors.muted;wrapMode:Text.Wrap
    }
    Repeater {
        id:noticeList;model:menu.entries.length
        Button {
            id:row
            required property int index
            readonly property var modelData:menu.entries[index]||({})
            property string pressedKey:""
            objectName:"quickRow_"+modelData.key
            Layout.fillWidth:true;hoverEnabled:true;focusPolicy:Qt.StrongFocus
            padding:8;implicitHeight:Math.max(42,contentItem.implicitHeight+16)
            Accessible.name:[modelData.caption,modelData.title,modelData.detail].filter(Boolean).join(" · ")
            onPressed:pressedKey=modelData.key
            onClicked:if(pressedKey===modelData.key)menu.drill(pressedKey)
            background:Rectangle {radius:7;color:row.hovered||row.visualFocus?menu.colors.alternate:"transparent";border.width:row.visualFocus?2:0;border.color:menu.colors.accent}
            contentItem:RowLayout {spacing:10
                Kirigami.Icon {source:row.modelData.icon||"notifications";implicitWidth:20;implicitHeight:20;color:menu.colors.muted}
                ColumnLayout {Layout.fillWidth:true;spacing:2
                    RowLayout {visible:!!row.modelData.caption;Layout.fillWidth:true;spacing:6
                        Label {text:row.modelData.caption||"";color:menu.colors.muted;font.pixelSize:12;textFormat:Text.PlainText;elide:Text.ElideRight;Layout.maximumWidth:row.width*0.50}
                        Rectangle {visible:!!row.modelData.unread;width:6;height:6;radius:3;color:menu.colors.accent}
                        Item {Layout.fillWidth:true}
                        Label {text:row.modelData.time||"";color:menu.colors.muted;font.pixelSize:12}
                    }
                    Label {text:row.modelData.title;Layout.fillWidth:true;color:menu.colors.text;font.weight:Font.Medium;textFormat:Text.PlainText;wrapMode:Text.Wrap;maximumLineCount:2;elide:Text.ElideRight}
                    Label {visible:!!row.modelData.detail;text:row.modelData.detail||"";Layout.fillWidth:true;color:menu.colors.muted;textFormat:Text.PlainText;wrapMode:Text.Wrap;maximumLineCount:2;elide:Text.ElideRight}
                }
                Kirigami.Icon {visible:!menu.notices;source:"go-next";implicitWidth:16;implicitHeight:16;color:menu.colors.muted}
            }
        }
    }
    Rectangle {color:menu.colors.border;implicitHeight:1;Layout.topMargin:5;Layout.fillWidth:true}
    RowLayout {
        Layout.fillWidth:true
        BarButton {objectName:"quickMore";colors:menu.colors;text:menu.t(({notifications:"Alle Mitteilungen",network:"Netzwerk öffnen",audio:"Audio öffnen",settings:"Systemsteuerung öffnen"})[menu.topic]||"Öffnen");glyph:"go-next";onClicked:menu.drill("")}
        Item {Layout.fillWidth:true}
        BarButton {visible:menu.notices;colors:menu.colors;text:menu.t("Nicht stören");glyph:menu.quiet?"notifications-disabled":"notifications";current:menu.quiet;onClicked:menu.toggleQuiet()}
    }
}
