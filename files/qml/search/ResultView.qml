pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ColumnLayout {
    id: root
    required property var view
    required property var theme
    spacing: theme.spacing
    visible: view.active
    property real textSize: theme.fontSize
    property string exportKey: ""
    readonly property bool dialogVisible: exportDialog.visible
    Label { Layout.fillWidth: true; visible: text.length > 0; text: root.view.title; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: root.theme.text; font.family: root.theme.fontFamily; font.pixelSize: root.textSize + 5; font.weight: Font.DemiBold }
    Repeater {
        model: root.view.blocks
        Loader {
            id: part
            required property var modelData
            Layout.fillWidth: true
            property var block: modelData
            sourceComponent: ({table: tableBlock, slider: sliderBlock, select: selectBlock, toggle: toggleBlock, chart: chartBlock, progress: progressBlock, files: filesBlock})[block.type]
        }
    }
    LumenButton { objectName: "resultSubmit"; theme: root.theme; visible: root.view.submitLabel.length > 0; text: root.view.submitLabel; primary: true; enabled: root.view.canSubmit; onClicked: root.view.submit() }
    FileDialog { id: exportDialog; title: root.view.text("Tabelle exportieren"); fileMode: FileDialog.SaveFile; nameFilters: ["CSV (*.csv)"]; defaultSuffix: "csv"; onAccepted: root.view.export_table(root.exportKey, selectedFile.toString()) }

    component Heading: Label { Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText; color: root.theme.text; font.family: root.theme.fontFamily; font.pixelSize: root.textSize; font.weight: Font.Medium }
    component Field: TextField { font.family: root.theme.fontFamily; font.pixelSize: root.textSize - 1; color: root.theme.text; selectByMouse: true; padding: 10; placeholderTextColor: root.theme.muted; background: Rectangle { color: root.theme.base; radius: 8; border.color: parent.activeFocus ? root.theme.accent : root.theme.border } }
    Component {
        id: sliderBlock
        ColumnLayout {
            id: sliderPane
            property var block: parent.block
            spacing: 8
            Heading { text: sliderPane.block.label }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                Slider { id: slider; enabled: root.view.editable; objectName: "resultSlider_" + sliderPane.block.id; Layout.fillWidth: true; from: sliderPane.block.min; to: sliderPane.block.max; stepSize: sliderPane.block.step; value: root.view.values[sliderPane.block.id] === undefined ? sliderPane.block.value : root.view.values[sliderPane.block.id]; Accessible.name: sliderPane.block.label; onMoved: root.view.set_value(sliderPane.block.id, Math.round(value)); palette.highlight: root.theme.accent
                    background: Rectangle { x: slider.leftPadding; y: slider.topPadding + slider.availableHeight/2-height/2; width: slider.availableWidth; height: 5; radius: 2.5; color: root.theme.border
                        Rectangle { width: slider.visualPosition * parent.width; height: parent.height; radius: parent.radius; color: root.theme.accent }
                    }
                    handle: Rectangle { x: slider.leftPadding + slider.visualPosition * (slider.availableWidth-width); y: slider.topPadding + slider.availableHeight/2-height/2; implicitWidth: 20; implicitHeight: 20; radius: 10; color: root.theme.accent; border.width: slider.activeFocus ? 2 : 0; border.color: root.theme.text }
                }
                Field { id: numeric; enabled: root.view.editable; objectName: "resultNumber_" + sliderPane.block.id; Layout.preferredWidth: 105; text: String(root.view.values[sliderPane.block.id]); validator: DoubleValidator { bottom: sliderPane.block.min; top: sliderPane.block.max; decimals: 0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: sliderPane.block.label; onEditingFinished: { root.view.set_value(sliderPane.block.id, Number(text)); text = String(root.view.values[sliderPane.block.id]) } }
                Label { text: sliderPane.block.unit; color: root.theme.muted; font.pixelSize: root.textSize - 1; textFormat: Text.PlainText }
            }
        }
    }
    Component {
        id: selectBlock
        ColumnLayout {
            id: selectPane
            property var block: parent.block
            Heading { text: selectPane.block.label }
            ComboBox { id: choice; enabled: root.view.editable; objectName: "resultSelect_" + selectPane.block.id; Layout.fillWidth: true; model: selectPane.block.options; currentIndex: model.indexOf(root.view.values[selectPane.block.id]); font.family: root.theme.fontFamily; font.pixelSize: root.textSize; Accessible.name: selectPane.block.label; onActivated: root.view.set_value(selectPane.block.id,currentText); palette.base: root.theme.base; palette.button: root.theme.button; palette.text: root.theme.text; palette.buttonText: root.theme.text; palette.highlight: root.theme.accent
                padding: 12; implicitHeight: root.theme.rowHeight
                contentItem: Text { text: choice.displayText; textFormat: Text.PlainText; font: choice.font; color: root.theme.text; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; rightPadding: 24 }
                background: Rectangle { radius: 8; color: root.theme.base; border.color: choice.activeFocus ? root.theme.accent : root.theme.border }
            }
        }
    }
    Component {
        id: toggleBlock
        Switch { id: toggle; enabled: root.view.editable; property var block: parent.block; objectName: "resultToggle_" + block.id; text: block.label; checked: root.view.values[block.id] === true; font.family: root.theme.fontFamily; font.pixelSize: root.textSize; onToggled: root.view.set_value(block.id,checked); spacing: 12; padding: 0; implicitHeight: 38
            indicator: Rectangle { implicitWidth: 42; implicitHeight: 24; x: toggle.leftPadding; y: toggle.height/2-height/2; radius: 12; color: toggle.checked ? root.theme.accent : root.theme.border; border.width: toggle.activeFocus ? 2 : 0; border.color: root.theme.text
                Rectangle { width: 18; height: 18; radius: 9; x: toggle.checked ? 21 : 3; y: 3; color: toggle.checked ? root.theme.onAccent : root.theme.base }
            }
            contentItem: Text { text: toggle.text; textFormat: Text.PlainText; font: toggle.font; color: root.theme.text; leftPadding: toggle.indicator.width+toggle.spacing; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap }
        }
    }
    Component {
        id: progressBlock
        ColumnLayout { id: progressPane; property var block: parent.block
            Heading { text: progressPane.block.label + " · " + progressPane.block.value + " %" }
            ProgressBar { id: progress; Layout.fillWidth: true; from: 0; to: 100; value: progressPane.block.value; palette.highlight: root.theme.accent; Accessible.name: progressPane.block.label
                background: Rectangle { implicitHeight: 8; radius: 4; color: root.theme.border }
                contentItem: Item { implicitHeight: 8; Rectangle { width: progress.visualPosition * parent.width; height: parent.height; radius: 4; color: root.theme.accent } }
            }
        }
    }
    Component {
        id: chartBlock
        ColumnLayout {
            id: chartPane
            property var block: parent.block
            property real largest: Math.max(1,...block.items.map(function(p) { return p.value }))
            Heading { text: chartPane.block.label }
            Repeater { model: chartPane.block.items
                ColumnLayout { id: bar; required property var modelData; Layout.fillWidth: true; spacing: 4
                    RowLayout { Layout.fillWidth: true
                        Label { Layout.fillWidth: true; text: bar.modelData.label; elide: Text.ElideRight; textFormat: Text.PlainText; color: root.theme.text; font.pixelSize: root.textSize - 1 }
                        Label { text: bar.modelData.value + " " + chartPane.block.unit; textFormat: Text.PlainText; color: root.theme.muted; font.pixelSize: root.textSize - 1 }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 8; radius: 4; color: root.theme.base
                        Rectangle { height: parent.height; width: parent.width * bar.modelData.value / chartPane.largest; radius: 4; color: root.theme.accent }
                    }
                }
            }
        }
    }
    Component {
        id: filesBlock
        ColumnLayout {
            id: filesPane
            property var block: parent.block
            Heading { text: filesPane.block.label }
            Repeater { model: filesPane.block.paths
                RowLayout { id: fileRow; required property string modelData; required property int index; Layout.fillWidth: true
                    ColumnLayout { Layout.fillWidth: true
                        Label { Layout.fillWidth: true; text: fileRow.modelData.split('/').pop(); textFormat: Text.PlainText; elide: Text.ElideMiddle; color: root.theme.text; font.pixelSize: root.textSize }
                        Label { Layout.fillWidth: true; text: fileRow.modelData; textFormat: Text.PlainText; elide: Text.ElideMiddle; color: root.theme.muted; font.pixelSize: root.textSize - 3 }
                    }
                    LumenButton { theme: root.theme; quiet: true; text: root.view.text("Öffnen"); onClicked: root.view.open_file(filesPane.block.id,fileRow.index) }
                }
            }
        }
    }
    Component {
        id: tableBlock
        ColumnLayout {
            id: tablePane
            property var block: parent.block
            property var rows: root.view.table_rows(block.id,root.view.tableRevision)
            spacing: 8
            Heading { text: tablePane.block.label }
            RowLayout { Layout.fillWidth: true
                Field { objectName: "resultFilter_" + tablePane.block.id; Layout.fillWidth: true; placeholderText: root.view.text("Tabelle filtern …"); Accessible.name: placeholderText; onTextEdited: root.view.filter_table(tablePane.block.id,text) }
                LumenButton { theme: root.theme; quiet: true; text: root.view.text("Kopieren"); onClicked: root.view.copy_table(tablePane.block.id) }
                LumenButton { theme: root.theme; quiet: true; text: "CSV"; hint: root.view.text("Tabelle exportieren"); onClicked: { root.exportKey=tablePane.block.id; exportDialog.open() } }
            }
            ScrollView {
                id: tableScroll
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(340, (tablePane.rows.length + 1) * root.theme.rowHeight + 20)
                contentWidth: Math.max(availableWidth, tablePane.block.columns.length * 150 + 42)
                contentHeight: tableBody.implicitHeight; clip: true
                Column {
                    id: tableBody
                    width: tableScroll.contentWidth
                    Row {
                        width: parent.width; height: root.theme.rowHeight
                        Item { width: 42; height: parent.height }
                        Repeater { model: tablePane.block.columns
                            Button { id: column; required property string modelData; required property int index; width: (tableBody.width-42)/tablePane.block.columns.length; height: root.theme.rowHeight; text: modelData + " ↕"; font.family: root.theme.fontFamily; font.pixelSize: root.textSize - 1; font.weight: Font.DemiBold; onClicked: root.view.sort_table(tablePane.block.id,index)
                                contentItem: Text { text: column.text; textFormat: Text.PlainText; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; color: root.theme.text; font: column.font }
                                background: Rectangle { color: root.theme.base; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.theme.border } }
                            }
                        }
                    }
                    Repeater { model: tablePane.rows
                        Rectangle {
                            id: tableRow
                            required property var modelData
                            required property int index
                            width: tableBody.width; height: root.theme.rowHeight
                            color: modelData.selected ? Qt.alpha(root.theme.accent,0.14) : index%2 ? Qt.alpha(root.theme.base,0.5) : "transparent"
                            Row {
                                anchors.fill: parent
                                CheckBox { id: rowCheck; enabled: root.view.editable; width: 42; height: parent.height; checked: tableRow.modelData.selected; Accessible.name: root.view.text("Zeile auswählen") + " " + (tableRow.modelData.index+1); onClicked: root.view.select_row(tablePane.block.id,tableRow.modelData.index); palette.highlight: root.theme.accent
                                    indicator: Rectangle { width: 18; height: 18; radius: 4; anchors.centerIn: parent; color: rowCheck.checked ? root.theme.accent : "transparent"; border.color: rowCheck.activeFocus ? root.theme.accent : root.theme.border; border.width: rowCheck.activeFocus ? 2 : 1
                                        Text { anchors.centerIn: parent; text: rowCheck.checked ? "✓" : ""; color: root.theme.onAccent; font.pixelSize: 14 }
                                    }
                                }
                                Repeater { model: tableRow.modelData.cells
                                    Label { required property var modelData; width: (tableBody.width-42)/tablePane.block.columns.length; height: root.theme.rowHeight; leftPadding: 10; rightPadding: 14; text: String(modelData); textFormat: Text.PlainText; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; horizontalAlignment: typeof modelData === "number" ? Text.AlignRight : Text.AlignLeft; color: root.theme.text; font.family: root.theme.fontFamily; font.pixelSize: root.textSize - 1
                                        HoverHandler { id: cellHover }
                                        ToolTip.visible: cellHover.hovered && truncated; ToolTip.text: text
                                    }
                                }
                            }
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Qt.alpha(root.theme.border,0.45) }
                        }
                    }
                }
            }
        }
    }
}
