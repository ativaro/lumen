import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: root
    required property var controller
    readonly property var t: controller.theme
    readonly property var detail: controller.detail
    readonly property bool narrow: width < 1220
    width: 1440; height: 920
    minimumWidth: Math.max(1020, t.fontSize * 55); minimumHeight: 700
    title: "Lumen Vault · " + tx("Designvorschau")
    color: t.window
    font.family: t.fontFamily
    font.pixelSize: t.fontSize
    function tx(value) { return controller.text(value) }
    function kindName(kind) { return tx(({login:"Anmeldung",token:"API-Token",note:"Sichere Notiz",recovery:"Wiederherstellungscodes"})[kind] || "Anmeldung") }
    function entryIcon(id) { return ({mail:"mail-message",git:"code-context",nas:"network-server",api:"weather-clouds",note:"document-edit",codes:"view-barcode"})[id] || "document-encrypt" }

    component Caption: Label {
        color: root.t.muted
        font.pixelSize: root.t.fontSize - 2
        textFormat: Text.PlainText
    }
    component Rule: Rectangle { color: root.t.border; opacity: 0.45; implicitHeight: 1; Layout.fillWidth: true }
    component Glyph: VaultButton {
        theme: root.t; quiet: true; enabled: false
        implicitWidth: 42; implicitHeight: 42
        leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
        icon.color: root.t.muted
        background: Item {}
    }
    component Nav: VaultButton {
        id: nav
        required property string category
        theme: root.t; quiet: true
        Layout.fillWidth: true
        selected: root.controller.activeCategory === category
        implicitHeight: 48
        ToolTip.text: text
        contentItem: RowLayout {
            spacing: 12
            Glyph { glyph: nav.glyph; icon.color: nav.selected ? root.t.accent : root.t.muted; implicitWidth: 27; implicitHeight: 30; icon.width: 23; icon.height: 23 }
            Label { text: nav.text; color: root.t.text; font: nav.font; Layout.fillWidth: true; elide: Text.ElideRight }
        }
        onClicked: root.controller.choose_category(category)
        Rectangle { width: 3; radius: 2; color: root.t.accent; height: 28; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; visible: parent.selected }
    }
    component DetailField: ColumnLayout {
        required property string caption
        required property string value
        property bool secret: false
        property bool accent: false
        spacing: 9
        Layout.fillWidth: true
        Caption { text: caption }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 52
            color: root.t.base; radius: 9; border.color: root.t.border
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 16; spacing: 3
                Label {
                    Layout.fillWidth: true
                    text: value; textFormat: Text.PlainText; elide: Text.ElideRight
                    color: accent ? root.t.accent : root.t.text
                    font.pixelSize: root.t.fontSize
                    font.letterSpacing: secret ? 1.4 : 0
                }
                VaultButton {
                    visible: secret; theme: root.t; quiet: true
                    glyph: root.detail.revealed ? "view-hidden" : "view-visible"
                    implicitWidth: 46; implicitHeight: 48; leftPadding: 11; rightPadding: 11
                    ToolTip.text: root.tx(root.detail.revealed ? "Beispiel verbergen" : "Beispiel 10 Sekunden anzeigen")
                    onClicked: root.controller.reveal()
                }
                VaultButton {
                    theme: root.t; quiet: true; glyph: "edit-copy"
                    implicitWidth: 46; implicitHeight: 48; leftPadding: 11; rightPadding: 11
                    ToolTip.text: root.tx("Kopieren · in der Vorschau deaktiviert")
                    onClicked: root.controller.explain("copy")
                }
            }
        }
    }

    Shortcut { sequence: "Ctrl+L"; onActivated: controller.lock() }
    Shortcut { sequence: "Ctrl+F"; onActivated: { if (body.item) body.item.focusSearch() } }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 88; color: root.t.window
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 26; anchors.rightMargin: 26; spacing: 20
                Glyph { glyph: "document-encrypt"; icon.color: root.t.accent; icon.width: 34; icon.height: 34; implicitWidth: 44 }
                ColumnLayout {
                    spacing: 2
                    Label { text: "Lumen Vault"; color: root.t.text; font.pixelSize: 27; font.weight: Font.Medium }
                    Caption { text: root.tx("Deine Daten. In deiner Hand.") }
                }
                Item { Layout.fillWidth: true }
                RowLayout {
                    spacing: 0
                    VaultButton { theme: root.t; text: root.tx("Tresor"); primary: true; implicitWidth: 126 }
                    VaultButton { theme: root.t; text: root.tx("Sicherungen"); implicitWidth: Math.max(140, implicitContentWidth + leftPadding + rightPadding); onClicked: root.controller.backups() }
                }
                Item { Layout.fillWidth: true }
                Caption { text: root.tx("Vorschau"); color: root.t.accent }
                VaultButton { objectName: "lockPreview"; theme: root.t; glyph: "object-locked"; text: root.tx("Sperren"); visible: !controller.locked; onClicked: controller.lock() }
            }
        }
        Rule {}
        Loader {
            id: body
            Layout.fillWidth: true; Layout.fillHeight: true
            sourceComponent: controller.locked ? lockedPage : unlockedPage
        }
        Rule {}
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Math.max(50, statusText.implicitHeight + 26)
            color: root.t.base
            RowLayout {
                anchors.fill: parent; anchors.margins: 13; anchors.leftMargin: 25; anchors.rightMargin: 25; spacing: 12
                Glyph { glyph: "dialog-information"; implicitHeight: 24; implicitWidth: 26 }
                Caption {
                    id: statusText
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    text: controller.status || root.tx("Designvorschau · feste Beispieldaten · kein Passwortspeicher")
                }
                Caption { visible: !controller.locked && !root.narrow; text: root.tx("Automatisch sperren · 5 min") }
            }
        }
    }
    Component {
        id: lockedPage
        Item {
            ColumnLayout {
                anchors.centerIn: parent; width: Math.min(parent.width - 100, 560); spacing: 20
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter; width: 88; height: 88; radius: 44
                    color: root.t.button; border.color: root.t.border
                    Glyph { anchors.centerIn: parent; glyph: "document-encrypt"; icon.color: root.t.accent; icon.width: 38; icon.height: 38; implicitWidth: 60; implicitHeight: 60 }
                }
                Label {
                    Layout.fillWidth: true; text: root.tx("Ein eigener Ort für deine Zugänge.")
                    color: root.t.text; font.pixelSize: 30; font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                }
                Caption {
                    Layout.fillWidth: true; text: root.tx("Passwörter, Tokens und sichere Notizen – im neuen Vault-Entwurf. Erkunde die Bedienung mit festen Beispielen.")
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                    font.pixelSize: root.t.fontSize; lineHeight: 1.35
                }
                VaultButton {
                    objectName: "showDemo"; Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 12
                    theme: root.t; primary: true; text: root.tx("Beispiel-Tresor ansehen"); glyph: "go-next"
                    implicitHeight: 50; onClicked: root.controller.show_demo()
                }
                Caption {
                    Layout.fillWidth: true; Layout.topMargin: 10
                    text: root.tx("Eigene Zugangsdaten sind noch nicht freigegeben. Speicher-Engine und unabhängige Sicherheitsprüfung stehen aus.")
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; lineHeight: 1.35
                }
            }
        }
    }
    Component {
        id: unlockedPage
        RowLayout {
            spacing: 0
            function focusSearch() { search.forceActiveFocus() }
            Rectangle {
                Layout.preferredWidth: Math.max(root.narrow ? 200 : 242, root.t.fontSize * 12); Layout.fillHeight: true; color: root.t.base
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; spacing: 5
                    ScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ColumnLayout {
                            width: parent.width; spacing: 5
                            Caption { text: root.tx("Mein Tresor"); Layout.margins: 14; font.weight: Font.Medium }
                            Nav { category: "all"; text: root.tx("Alle Einträge"); glyph: "view-list-details" }
                            Nav { category: "favorites"; text: root.tx("Favoriten"); glyph: "favorite" }
                            Nav { category: "login"; text: root.tx("Passwörter"); glyph: "dialog-password" }
                            Nav { category: "token"; text: root.tx("API-Tokens"); glyph: "code-context" }
                            Nav { category: "note"; text: root.tx("Sichere Notizen"); glyph: "document-edit" }
                            Nav { category: "recovery"; text: root.tx("Recovery-Codes"); glyph: "view-barcode" }
                            Rule { Layout.topMargin: 16; Layout.bottomMargin: 9; Layout.leftMargin: 14; Layout.rightMargin: 14 }
                            RowLayout {
                                Layout.fillWidth: true; Layout.leftMargin: 14
                                Caption { text: root.tx("Sammlungen"); Layout.fillWidth: true; font.weight: Font.Medium }
                                VaultButton { theme: root.t; quiet: true; glyph: "list-add"; implicitWidth: 36; leftPadding: 7; rightPadding: 7; ToolTip.text: root.tx("Sammlung hinzufügen"); onClicked: controller.explain("collection") }
                            }
                            Repeater {
                                model: [root.tx("Privat"),root.tx("Arbeit"),root.tx("Server")]
                                Nav { required property string modelData; category: modelData; text: modelData; glyph: "folder" }
                            }
                        }
                    }
                    Nav { category: "trash"; text: root.tx("Papierkorb"); glyph: "user-trash" }
                }
            }
            Rectangle { Layout.fillHeight: true; width: 1; color: root.t.border; opacity: 0.5 }
            ColumnLayout {
                Layout.preferredWidth: root.narrow ? 300 : 370; Layout.fillHeight: true
                Layout.margins: 16; spacing: 14
                TextField {
                    id: search; objectName: "vaultDemoSearch"
                    Layout.fillWidth: true; implicitHeight: 46
                    placeholderText: root.tx("Im Beispiel-Tresor suchen …")
                    color: root.t.text; placeholderTextColor: root.t.muted
                    selectedTextColor: root.t.onAccent; selectionColor: root.t.accent
                    font.family: root.t.fontFamily; font.pixelSize: root.t.fontSize - 1
                    leftPadding: 14; maximumLength: 256
                    Accessible.name: placeholderText
                    background: Rectangle { color: root.t.base; radius: 8; border.color: search.activeFocus ? root.t.accent : root.t.border }
                    onTextChanged: root.controller.filter(text)
                }
                VaultButton {
                    Layout.fillWidth: true; theme: root.t; glyph: "list-add"; text: root.tx("Neuer Eintrag")
                    onClicked: root.controller.explain("new")
                }
                ListView {
                    id: entries; objectName: "vaultDemoEntries"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: controller.entries; spacing: 3; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ItemDelegate {
                        id: entry
                        required property var modelData
                        width: entries.width; height: root.t.fontSize * 2 + 44
                        text: modelData.title
                        Accessible.name: modelData.title + ", " + root.kindName(modelData.kind)
                        background: Rectangle {
                            color: root.detail.id === entry.modelData.id ? root.t.hover : entry.hovered ? root.t.button : "transparent"
                            radius: 9
                            Rectangle { visible: root.detail.id === entry.modelData.id; width: 3; radius: 2; color: root.t.accent; anchors.left: parent.left; height: parent.height - 18; anchors.verticalCenter: parent.verticalCenter }
                        }
                        contentItem: RowLayout {
                            spacing: 13
                            Glyph { glyph: root.entryIcon(entry.modelData.id); icon.width: 28; icon.height: 28; implicitWidth: 40 }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 5
                                Label { Layout.fillWidth: true; text: entry.modelData.title; color: root.t.text; font.pixelSize: root.t.fontSize; elide: Text.ElideRight; textFormat: Text.PlainText }
                                Caption { Layout.fillWidth: true; text: root.kindName(entry.modelData.kind) + " · " + entry.modelData.collection; elide: Text.ElideRight }
                            }
                            Glyph { glyph: "go-next"; implicitWidth: 22; icon.width: 16; icon.height: 16 }
                        }
                        onClicked: root.controller.select(modelData.id)
                    }
                    Caption { anchors.centerIn: parent; width: parent.width - 20; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; visible: entries.count === 0; text: root.tx("Keine passenden Beispiele.") }
                }
                Caption { text: root.tx("Feste Beispieldaten · nur für diese Ansicht"); Layout.fillWidth: true; wrapMode: Text.WordWrap }
            }
            Rectangle { Layout.fillHeight: true; width: 1; color: root.t.border; opacity: 0.5 }
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: parent.width; spacing: 21
                    visible: !!root.detail.id
                    RowLayout {
                        Layout.fillWidth: true; Layout.margins: 26; Layout.bottomMargin: 8; spacing: 20
                        Rectangle {
                            width: root.narrow ? 68 : 84; height: width; radius: width / 2
                            color: root.t.button; border.color: root.t.border
                            Glyph { anchors.centerIn: parent; glyph: root.entryIcon(root.detail.id); icon.width: 38; icon.height: 38; implicitWidth: 58; implicitHeight: 58; icon.color: root.t.accent }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 6
                            Label { text: root.detail.title || ""; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 27; font.weight: Font.Medium; color: root.t.text; textFormat: Text.PlainText }
                            Caption { text: root.kindName(root.detail.kind) + " · " + (root.detail.collection || ""); Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        }
                        VaultButton {
                            theme: root.t; quiet: true; glyph: "favorite"; selected: !!root.detail.favorite
                            implicitWidth: 44; leftPadding: 10; rightPadding: 10
                            ToolTip.text: root.tx(root.detail.favorite ? "Aus Favoriten entfernen" : "Zu Favoriten hinzufügen")
                            onClicked: root.controller.favorite()
                        }
                    }
                    Rule { Layout.leftMargin: 26; Layout.rightMargin: 26 }
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26; spacing: 22
                        DetailField { caption: root.tx("Website"); value: root.detail.website || ""; accent: true; visible: !!root.detail.website }
                        DetailField { caption: root.tx("Benutzername"); value: root.detail.username || ""; visible: !!root.detail.username }
                        DetailField {
                            caption: root.tx(root.detail.kind === "token" ? "API-Token" : root.detail.kind === "recovery" ? "Wiederherstellungscodes" : "Passwort")
                            value: root.detail.secret || ""; secret: true; visible: root.detail.kind !== "note"
                        }
                        Caption { visible: root.detail.kind !== "note"; text: root.tx("Beispiel kurz anzeigen · nach 10 Sekunden wieder verborgen"); Layout.fillWidth: true; wrapMode: Text.WordWrap; Layout.topMargin: -13 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 9
                            Caption { text: root.tx("Notiz") }
                            Label { Layout.fillWidth: true; text: root.detail.note || ""; wrapMode: Text.WordWrap; color: root.t.text; textFormat: Text.PlainText; lineHeight: 1.35; font.pixelSize: root.t.fontSize - 1 }
                        }
                    }
                    Rule { Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.topMargin: 4 }
                    RowLayout {
                        Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26; spacing: 12
                        Glyph { glyph: "object-locked"; Layout.alignment: Qt.AlignTop }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 8
                            Label { text: root.tx("Zugriff durch Apps"); color: root.t.text; font.pixelSize: root.t.fontSize }
                            Caption { text: root.tx("Nicht freigegeben"); color: root.t.accent }
                            Caption { text: root.tx("Keine Verbindung zu KI, MCP oder anderen Apps."); Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        }
                    }
                    Rule { Layout.leftMargin: 26; Layout.rightMargin: 26 }
                    RowLayout {
                        Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.bottomMargin: 24
                        VaultButton { theme: root.t; quiet: true; glyph: root.detail.trashed ? "edit-undo" : "user-trash"; ToolTip.text: root.tx(root.detail.trashed ? "Beispiel wiederherstellen" : "Beispiel in den Papierkorb"); onClicked: controller.trash() }
                        Item { Layout.fillWidth: true }
                        VaultButton { theme: root.t; text: root.tx("Bearbeiten"); glyph: "document-edit"; onClicked: controller.explain("edit") }
                    }
                }
            }
        }
    }
}
