import QtQuick
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: form
    property string cfg_surface: "tasks"
    ComboBox {
        Kirigami.FormData.label: "Lumen-Bereich:"
        textRole: "label"; valueRole: "value"
        model: [{label: "Aufgabenmenü", value: "tasks"}, {label: "Lumen und Dateien", value: "home"},
                {label: "Suche", value: "search"}, {label: "Lumen Zentrale", value: "control"}]
        currentIndex: Math.max(0, indexOfValue(form.cfg_surface))
        onActivated: form.cfg_surface = currentValue
    }
}
