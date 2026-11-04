// SPDX-License-Identifier: MIT
#include "appmenu.h"
#include "paneldata.h"
#include <QApplication>
#include <QAbstractItemModel>
#include <QDBusInterface>
#include <QFile>
#include <QMenu>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QScreen>
#include <QTest>
#include <LayerShellQt/Window>

class UiTest:public QObject {
    Q_OBJECT
    static QQuickItem *find(QQuickItem *root,const QString &name){
        if(root->objectName()==name)return root;
        for(auto child:root->childItems())if(auto value=find(child,name))return value;
        return nullptr;
    }
    static QQuickItem *item(const QString &name){
        for(auto w:QGuiApplication::allWindows())if(auto quick=qobject_cast<QQuickWindow*>(w))if(auto value=find(quick->contentItem(),name))return value;
        return nullptr;
    }
private slots:
    void realWindowMenusAndLauncher(){
        QProcess input;input.start("/old-qa/native/input");QVERIFY(input.waitForStarted());
        const auto send=[&](const QByteArray &command){input.write(command);if(!input.waitForBytesWritten(1000) || !input.waitForReadyRead(1000))return false;return input.readAllStandardOutput().startsWith("OK");};
        qmlRegisterType<AppMenu>("Lumen.Topbar",1,0,"AppMenu");
        PanelData data;QQmlEngine engine;engine.rootContext()->setContextProperty("panelData",&data);
        QQmlComponent component(&engine,QUrl("qrc:/lumen/Topbar.qml"));
        QScopedPointer<QObject> owner(component.create());
        for(const auto &error:component.errors())qWarning().noquote()<<error.toString();
        auto window=qobject_cast<QQuickWindow*>(owner.data());QVERIFY(window);
        auto screen=QGuiApplication::primaryScreen();window->setScreen(screen);window->setWidth(screen->geometry().width());
        auto layer=LayerShellQt::Window::get(window);layer->setScreen(screen);
        layer->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop)|LayerShellQt::Window::AnchorLeft|LayerShellQt::Window::AnchorRight);
        layer->setExclusiveZone(56);layer->setLayer(LayerShellQt::Window::LayerTop);layer->setActivateOnShow(false);
        layer->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityOnDemand);
        window->setProperty("ready",true);QTRY_VERIFY_WITH_TIMEOUT(window->isExposed(),5000);
        QTRY_COMPARE_WITH_TIMEOUT(data.snapshot()["apps"].toList().size(),5,5000);
        auto menus=window->findChild<AppMenu*>("applicationMenus");QVERIFY(menus);
        QTimer::singleShot(2500,window,[window]{
            auto state=window->findChild<QObject*>("activeWindowState");
            qInfo()<<"STATE"<<state->property("appName")<<state->property("service")<<state->property("path")<<state->property("screenGeometry");
            auto model=qvariant_cast<QAbstractItemModel*>(state->property("windowModel"));
            if(model){const auto roles=model->roleNames();qInfo()<<"ROWS"<<model->rowCount();for(int i=0;i<model->rowCount();i++){QVariantMap row;for(auto it=roles.cbegin();it!=roles.cend();++it){if(it.value()=="AppName" || it.value()=="IsActive" || it.value()=="ApplicationMenuServiceName" || it.value()=="ApplicationMenuObjectPath")row[it.value()]=model->data(model->index(i,0),it.key());}qInfo()<<row;}}
        });
        QTRY_COMPARE_WITH_TIMEOUT(menus->entries().size(),4,6000);
        QCOMPARE(menus->entries()[0].toMap()["label"].toString(),QStringLiteral("Datei"));
        QTRY_VERIFY_WITH_TIMEOUT(item("applicationMenu_0"),3000);
        auto button=item("applicationMenu_0");QVERIFY(button->isVisible());
        const auto click=[&](QQuickItem *value){const auto point=value->mapToGlobal(QPointF(value->width()/2,value->height()/2));return send("click "+QByteArray::number(point.x())+" "+QByteArray::number(point.y())+"\n");};
        QVERIFY(click(button));QTRY_VERIFY_WITH_TIMEOUT(QApplication::activePopupWidget()!=nullptr,3000);
        auto popup=qobject_cast<QMenu*>(QApplication::activePopupWidget());QVERIFY(popup);
        qInfo()<<"MENU_POSITION"<<popup->geometry()<<button->mapToGlobal(QPointF(0,button->height()));
        QVERIFY(popup->grab().save("/profile/captures/native-file-menu.png"));
        QVERIFY(send("key 108\n"));QTest::qWait(70);QVERIFY(send("key 28\n"));
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/saved-A.txt"),3000);
        QTRY_VERIFY_WITH_TIMEOUT(!menus->opened(),3000);
        QVERIFY(window->grabWindow().save("/profile/captures/native-topbar.png"));
        auto launch=item("launcherButton");QVERIFY(launch);QVERIFY(click(launch));
        auto apps=window->findChild<QObject*>("appsPopup");QVERIFY(apps);QTRY_VERIFY_WITH_TIMEOUT(apps->property("opened").toBool(),3000);
        QTRY_VERIFY_WITH_TIMEOUT(item("openApp_files"),3000);
        auto files=item("openApp_files");QTRY_VERIFY(files->window()!=nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(files->window()->isExposed(),3000);
        QTest::qWait(200);
        qInfo()<<"LAUNCHER"<<files->window()->geometry()<<files->mapToGlobal(QPointF(files->width()/2,files->height()/2))<<files->size()<<apps->property("height")<<apps->property("x")<<apps->property("y");
        auto background=qvariant_cast<QQuickItem*>(apps->property("background"));QVERIFY(background);
        qInfo()<<"POPUP_BACKGROUND"<<background->mapToGlobal(QPointF(0,0))<<background->size();
        QVERIFY(qAbs(background->mapToGlobal(QPointF(0,0)).x()-12)<=2);
        QVERIFY(files->window()->grabWindow().save("/profile/captures/native-launcher.png"));QVERIFY(click(files));
        QTRY_VERIFY_WITH_TIMEOUT(!apps->property("opened").toBool(),2000);
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/actions.jsonl"),3000);
        const auto actions=[](){QFile file("/profile/actions.jsonl");if(!file.open(QIODevice::ReadOnly))return QByteArray();return file.readAll();};
        QTRY_VERIFY_WITH_TIMEOUT(actions().contains("--open-app"),3000);
        input.closeWriteChannel();QVERIFY(input.waitForFinished(1000));
    }
};
QTEST_MAIN(UiTest)
#include "ui_test.moc"
