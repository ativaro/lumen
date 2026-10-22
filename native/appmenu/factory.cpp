// SPDX-License-Identifier: GPL-2.0-or-later
#include <KPluginFactory>
#include <KPluginMetaData>
#include <Plasma/Applet>
#include <Plasma/Theme>
#include <QAbstractItemModel>
#include <QAction>
#include <QApplication>
#include <QMenu>
#include <QSet>

class MenuPalette : public QObject
{
    Q_OBJECT
public:
    explicit MenuPalette(Plasma::Applet *applet)
        : QObject(applet), m_applet(applet), m_theme(this)
    {
        connect(&m_theme, &Plasma::Theme::themeChanged, this, &MenuPalette::apply);
    }
public Q_SLOTS:
    void apply()
    {
        const int current = m_applet->property("currentIndex").toInt();
        auto model = m_applet->property("model").value<QAbstractItemModel *>();
        auto menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
        if (current < 0 || !model || !menu) return;
        const auto index = m_applet->property("view").toInt() == 1 ? QModelIndex() : model->index(current, 0);
        auto action = model->data(index, model->roleNames().key("activeActions", -1)).value<QAction *>();
        if (!action || action->menu() != menu) return;
        const auto palette = m_theme.palette();
        QList<QMenu *> pending{menu};
        QSet<QMenu *> visited;
        while (!pending.isEmpty()) {
            auto currentMenu = pending.takeLast();
            if (visited.contains(currentMenu)) continue;
            visited.insert(currentMenu);
            currentMenu->setPalette(palette);
            if (auto parentMenu = qobject_cast<QMenu *>(currentMenu->parentWidget())) pending.append(parentMenu);
            for (auto entry : currentMenu->actions()) if (entry->menu()) pending.append(entry->menu());
        }
    }
private:
    Plasma::Applet *m_applet;
    Plasma::Theme m_theme;
};

class LumenAppMenuFactory : public KPluginFactory
{
    Q_OBJECT
    Q_INTERFACES(KPluginFactory)
    Q_PLUGIN_METADATA(IID KPluginFactory_iid FILE "../../plasmoid/appmenu/metadata.json")
public:
    LumenAppMenuFactory()
    {
        registerPlugin<Plasma::Applet>([](QWidget *, QObject *parent, const KPluginMetaData &metadata, const QVariantList &args) -> QObject * {
            const auto backend = KPluginFactory::loadFactory(KPluginMetaData(QStringLiteral("plasma/applets/org.kde.plasma.appmenu")));
            if (!backend.plugin) {
                return nullptr;
            }
            // RootPath also forces KDE's embedded QML in Plasma 6.8; retain our package metadata instead.
            const auto previous = backend.plugin->metaData();
            backend.plugin->setMetaData(metadata);
            auto applet = backend.plugin->create<Plasma::Applet>(parent, args);
            backend.plugin->setMetaData(previous);
            if (applet) QObject::connect(applet, SIGNAL(currentIndexChanged()), new MenuPalette(applet), SLOT(apply()));
            return applet;
        });
    }
};

#include "factory.moc"
