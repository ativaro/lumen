// SPDX-License-Identifier: MIT
#include "appmenu.h"
#include "paneldata.h"
#include <QApplication>
#include <QCommandLineParser>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QMap>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickWindow>
#include <QScreen>
#include <LayerShellQt/Window>

int main(int argc,char **argv){
    QApplication app(argc,argv);app.setApplicationName("lumen-topbar");app.setApplicationDisplayName("Lumen Topbar");
    app.setDesktopFileName("lumen-topbar");app.setQuitOnLastWindowClosed(false);
    QCommandLineParser parser;parser.addHelpOption();parser.addOption({"apps","Lumen Apps öffnen"});parser.process(app);
    auto bus=QDBusConnection::sessionBus();
    if(!bus.registerService("org.lumen.Topbar")){
        if(parser.isSet("apps")){QDBusInterface existing("org.lumen.Topbar","/Topbar","org.lumen.Topbar",bus);existing.asyncCall("ShowApps");}
        return 0;
    }
    qmlRegisterType<AppMenu>("Lumen.Topbar",1,0,"AppMenu");
    PanelData data;bus.registerObject("/Topbar",&data,QDBusConnection::ExportAllSlots);
    QQmlEngine engine;engine.rootContext()->setContextProperty("panelData",&data);
    QMap<QScreen*,QQuickWindow*> windows;
    const auto create=[&](QScreen *screen){
        QQmlComponent component(&engine,QUrl("qrc:/lumen/Topbar.qml"));
        auto object=component.create();auto window=qobject_cast<QQuickWindow*>(object);
        if(!window){qCritical("Lumen Topbar konnte nicht geladen werden.");for(const auto &error:component.errors())qWarning().noquote()<<error.toString();app.exit(1);return;}
        window->setScreen(screen);window->setGeometry(screen->geometry().x(),screen->geometry().y(),screen->geometry().width(),56);
        auto layer=LayerShellQt::Window::get(window);layer->setScreen(screen);layer->setScope("lumen-topbar");
        layer->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop)|LayerShellQt::Window::AnchorLeft|LayerShellQt::Window::AnchorRight);
        layer->setLayer(LayerShellQt::Window::LayerTop);layer->setExclusiveZone(56);
        layer->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityOnDemand);layer->setActivateOnShow(false);
        windows.insert(screen,window);window->setProperty("ready",true);
        QObject::connect(screen,&QScreen::geometryChanged,window,[window](const QRect &r){window->setWidth(r.width());});
    };
    for(auto screen:app.screens())create(screen);
    QObject::connect(&app,&QGuiApplication::screenAdded,&app,create);
    QObject::connect(&app,&QGuiApplication::screenRemoved,&app,[&](QScreen *screen){if(auto window=windows.take(screen)){window->close();window->deleteLater();}});
    if(windows.isEmpty())return 1;
    if(parser.isSet("apps"))QTimer::singleShot(300,&data,&PanelData::ShowApps);
    return app.exec();
}
