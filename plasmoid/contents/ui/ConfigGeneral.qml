import "Translations.js" as I18n
import QtQuick
import QtQuick.Controls
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: form
    property string helper: "/usr/bin/lumen-panel"
    property string uiLanguage: Qt.locale().name.toLowerCase().indexOf("de") === 0 ? "de" : "en"
    function tr(source, args) { return I18n.tr(source, uiLanguage, args); }
    Component.onCompleted: languageReader.connectSource(form.helper + " --language")
    P5Support.DataSource {
        id: languageReader
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            try {
                const response = JSON.parse(data["stdout"]);
                if (response.language === "de" || response.language === "en") form.uiLanguage = response.language;
            } catch (error) { /* Keep the desktop locale if the helper is unavailable. */ }
        }
    }
    property string cfg_surface: "tasks"
    ComboBox {
        Kirigami.FormData.label: form.tr("Lumen-Bereich:")
        textRole: "label"; valueRole: "value"
        model: [{label: form.tr("Aufgabenmenü"), value: "tasks"}, {label: form.tr("Lumen und Dateien"), value: "home"},
                {label: "Lumen", value: "search"}, {label: form.tr("Lumen Zentrale"), value: "control"}]
        currentIndex: Math.max(0, indexOfValue(form.cfg_surface))
        onActivated: form.cfg_surface = currentValue
    }
}
