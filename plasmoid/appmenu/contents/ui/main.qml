// SPDX-FileCopyrightText: 2013 Heena Mahour <heena393@gmail.com>
// SPDX-FileCopyrightText: 2013 Sebastian Kügler <sebas@kde.org>
// SPDX-FileCopyrightText: 2016 Kai Uwe Broulik <kde@privat.broulik.de>
// SPDX-License-Identifier: GPL-2.0-or-later
// Keep KDE's full and compact presenters separate so their native menus retain ownership.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.private.keyboardindicator as KeyboardIndicator
import org.kde.kirigami as Kirigami
import plasma.applet.org.kde.plasma.appmenu as AppMenu

PlasmoidItem {
    id: root
    objectName: "lumenAppMenu"
    readonly property bool compactView: Plasmoid.configuration.compactView
    readonly property int widthBudget: Math.max(40, Plasmoid.configuration.widthBudget)
    readonly property bool menusAvailable: appMenuModel.menuAvailable && windowState.hasMenu && !windowState.fullScreen
    readonly property bool menuBar: menusAvailable && windowState.maximized && fullRepresentationItem && fullRepresentationItem.menuWidth <= widthBudget
    readonly property bool available: menusAvailable && (compactView ? !menuBar : menuBar)
    readonly property string appName: windowState.appName || i18n("Anwendung")
    Plasmoid.constraintHints: Plasmoid.CanFillArea
    Plasmoid.status: !available ? PlasmaCore.Types.HiddenStatus
        : Plasmoid.currentIndex >= 0 ? PlasmaCore.Types.NeedsAttentionStatus : PlasmaCore.Types.ActiveStatus
    preferredRepresentation: compactView ? compactRepresentation : fullRepresentation
    preloadFullRepresentation: true
    onCompactViewChanged: Plasmoid.view = compactView ? 1 : 0
    Component.onCompleted: { Plasmoid.model = appMenuModel; Plasmoid.view = compactView ? 1 : 0; }
    WindowMenuState {
        id: windowState
        screenGeometry: root.screenGeometry
        holdActiveWindow: Plasmoid.currentIndex >= 0 || Plasmoid.containment.status === PlasmaCore.Types.AcceptingInputStatus
    }
    AppMenu.AppMenuModel {
        id: appMenuModel
        containmentStatus: Plasmoid.containment.status
        screenGeometry: root.screenGeometry
        allScreens: false
        onRequestActivateIndex: index => Plasmoid.requestActivateIndex(index)
    }
    // Clients may hide their own menubar even for normal windows.
    compactRepresentation: PlasmaComponents.ToolButton {
        objectName: "compactApplicationMenu"
        icon.name: "application-menu"
        Layout.fillWidth: false
        Layout.fillHeight: false
        Layout.minimumWidth: implicitWidth
        Layout.maximumWidth: implicitWidth
        text: root.appName
        display: PlasmaComponents.AbstractButton.IconOnly
        enabled: root.available
        down: Plasmoid.currentIndex >= 0
        Accessible.name: i18n("Menü von %1 öffnen", root.appName)
        onPressed: Plasmoid.trigger(this, 0)
    }
    fullRepresentation: RowLayout {
        id: buttons
        readonly property real menuWidth: {
            let result = Math.min(120, title.implicitWidth) + 12;
            for (let i = 0; i < menus.count; ++i) {
                const item = menus.itemAt(i);
                if (item && item.text !== "" && (item.activeActions?.visible ?? false)) result += item.implicitWidth;
            }
            return result;
        }
        Layout.minimumWidth: menuWidth
        Layout.maximumWidth: menuWidth
        Layout.minimumHeight: implicitHeight
        spacing: 0
        Binding { target: Plasmoid; property: "buttonGrid"; value: buttons }
        PlasmaComponents.Label {
            id: title
            text: root.appName
            font.weight: Font.DemiBold
            Layout.maximumWidth: 120
            Layout.rightMargin: 12
            elide: Text.ElideRight
        }
        Repeater {
            id: menus
            model: appMenuModel.visible ? appMenuModel : null
            AppMenu.MenuDelegate {
                required property int index
                required property string activeMenu
                required property PlasmaCore.Action activeActions
                readonly property int buttonIndex: index
                objectName: "applicationMenuButton" + index
                Layout.fillHeight: true
                text: activeMenu
                visible: text !== "" && (activeActions?.visible ?? false)
                enabled: activeActions?.enabled ?? false
                down: Plasmoid.currentIndex === index
                menuIsOpen: Plasmoid.currentIndex !== -1
                Kirigami.MnemonicData.active: alt.pressed
                onActivated: if (root.available) Plasmoid.trigger(this, index)
                KeyboardIndicator.KeyState { id: alt; key: Qt.Key_Alt }
            }
        }
        Connections {
            target: Plasmoid
            function onRequestActivateIndex(index: int) {
                if (!root.available) return;
                if (root.compactView) Plasmoid.trigger(root.compactRepresentationItem, 0);
                else {
                    const button = menus.itemAt(index);
                    if (button && button.enabled && button.visible) button.activated();
                }
            }
            function onActivated() {
                if (!root.available) return;
                if (root.compactView) Plasmoid.trigger(root.compactRepresentationItem, 0);
                else {
                    const first = menus.itemAt(0);
                    if (first && first.enabled && first.visible) first.activated();
                }
            }
        }
    }
}
