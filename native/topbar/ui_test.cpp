// SPDX-License-Identifier: MIT
#include "appmenu.h"
#include "paneldata.h"
#include "tray.h"
#include <QApplication>
#include <QFont>
#include <QAbstractItemModel>
#include <QDBusInterface>
#include <QDBusReply>
#include <QFile>
#include <QMenu>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QScreen>
#include <QSignalSpy>
#include <QTest>
#include <QSettings>
#include <LayerShellQt/Window>

class UiTest:public QObject {
    Q_OBJECT
    static QQuickItem *find(QQuickItem *root,const QString &name){
        if(!root)return nullptr;
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
        QProcess input;input.start("/build/topbar-input");QVERIFY(input.waitForStarted());
        // Flush Qt/Wayland before the separate client injects its next input event.
        const auto send=[&](const QByteArray &command){
            QGuiApplication::sync();if(input.write(command)!=command.size())return false;
            // Keep handling Wayland configuration while the external input client acknowledges a move.
            if(!QTest::qWaitFor([&]{return input.canReadLine() || input.state()==QProcess::NotRunning;},2000)){qWarning()<<"Input acknowledgement timeout"<<command.trimmed()<<input.state()<<input.errorString()<<input.bytesToWrite()<<input.readAllStandardError();return false;}
            const auto reply=input.readLine().trimmed();if(reply!="OK")qWarning()<<"Input acknowledgement invalid"<<command.trimmed()<<reply<<input.state()<<input.errorString();
            return reply=="OK";
        };
        qmlRegisterType<AppMenu>("Lumen.Topbar",1,0,"AppMenu");
        PanelData data;Tray tray;QQmlEngine engine;engine.rootContext()->setContextProperty("panelData",&data);
        if(qEnvironmentVariableIsSet("LUMEN_QA_SHORTCUTS") && !qgetenv("LUMEN_QA_SHORTCUTS").isEmpty()){
            QVERIFY(QDBusConnection::sessionBus().registerService("org.lumen.Topbar"));
            QVERIFY(QDBusConnection::sessionBus().registerObject("/Topbar",&data,QDBusConnection::ExportScriptableSlots));
        }
        engine.rootContext()->setContextProperty("trayModel",&tray);
        QQmlComponent component(&engine,QUrl("qrc:/lumen/Topbar.qml"));
        QScopedPointer<QObject> owner(component.create());
        for(const auto &error:component.errors())qWarning().noquote()<<error.toString();
        auto window=qobject_cast<QQuickWindow*>(owner.data());QVERIFY(window);
        auto screen=QGuiApplication::primaryScreen();window->setScreen(screen);window->setWidth(screen->geometry().width());
        auto layer=LayerShellQt::Window::get(window);layer->setScreen(screen);
        layer->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop)|LayerShellQt::Window::AnchorLeft|LayerShellQt::Window::AnchorRight);
        layer->setExclusiveZone(window->property("barSize").toInt());layer->setLayer(LayerShellQt::Window::LayerTop);layer->setActivateOnShow(false);
        layer->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityOnDemand);
        window->setProperty("ready",true);QTRY_VERIFY_WITH_TIMEOUT(window->isExposed(),5000);
        QTRY_COMPARE_WITH_TIMEOUT(data.snapshot()["apps"].toList().size(),5,5000);
        auto menus=window->findChild<AppMenu*>("applicationMenus");QVERIFY(menus);
        QTRY_COMPARE_WITH_TIMEOUT(menus->entries().size(),4,6000);
        QCOMPARE(menus->entries()[0].toMap()["label"].toString(),QStringLiteral("Datei"));
        QTRY_VERIFY_WITH_TIMEOUT(item("applicationMenu_0"),3000);
        QTest::qWait(150);
        auto island=item("leftIsland");QVERIFY(island);
        for(int index=0;index<menus->entries().size();++index){
            auto entry=item("applicationMenu_"+QString::number(index));QVERIFY(entry);
            if(entry->isVisible())QVERIFY2(entry->mapToItem(window->contentItem(),QPointF(entry->width(),0)).x()<=window->width()-6,"Application menu clipped by the right island");
        }
        auto button=item("applicationMenu_0");
        QTRY_VERIFY(button->isVisible() || item("menuOverflowButton")->isVisible());
        if(!button->isVisible()){auto overflow=item("menuOverflowButton");QVERIFY(overflow);const auto point=overflow->mapToGlobal(QPointF(overflow->width()/2,overflow->height()/2));QVERIFY(send("click "+QByteArray::number(point.x())+" "+QByteArray::number(point.y())+"\n"));QTRY_VERIFY(item("overflowMenu_0"));button=item("overflowMenu_0");QTest::qWait(150);}
        QVERIFY(button->isVisible());
        const auto click=[&](QQuickItem *value){
            if(!value || !value->window() || !value->isVisible())return false;
            QGuiApplication::sync();
            if(value->objectName().startsWith("start")){value->forceActiveFocus(Qt::TabFocusReason);QTest::qWait(100);}
            QSignalSpy rendered(value->window(),&QQuickWindow::frameSwapped);value->window()->update();
            if(!QTest::qWaitFor([&]{return rendered.count()>0;},1000))return false;
            const auto point=value->mapToGlobal(QPointF(value->width()/2,value->height()/2));
            return send("click "+QByteArray::number(point.x())+" "+QByteArray::number(point.y())+"\n");
        };
        if(button->objectName()=="applicationMenu_0"){
            QVERIFY(click(button));QTRY_VERIFY(menus->opened());
            QVERIFY(click(button));QTRY_VERIFY(!menus->opened());
        }
        QVERIFY(click(button));QTRY_VERIFY_WITH_TIMEOUT(QApplication::activePopupWidget()!=nullptr,3000);
        auto popup=qobject_cast<QMenu*>(QApplication::activePopupWidget());QVERIFY(popup);
        QCOMPARE(popup->font().pixelSize(),QApplication::font().pixelSize());
        qInfo()<<"MENU_POSITION"<<popup->geometry()<<button->mapToGlobal(QPointF(0,button->height()));
        QVERIFY(popup->grab().save("/profile/captures/native-file-menu.png"));
        QVERIFY(send("key 108\n"));QTest::qWait(70);QVERIFY(send("key 28\n"));
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/saved-A.txt"),3000);
        QTRY_VERIFY_WITH_TIMEOUT(!menus->opened(),3000);
        QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),1,4000);
        QTRY_VERIFY_WITH_TIMEOUT(item("trayItem_0"),2000);
        if(window->width()>=900)QTRY_VERIFY_WITH_TIMEOUT(item("trayItem_0")->isVisible(),2000);
        QVERIFY(window->grabWindow().save("/profile/captures/native-topbar.png"));
        auto hover=item("activeAppButton");QVERIFY(hover && hover->isVisible());
        const auto origin=hover->mapToItem(window->contentItem(),QPointF());const auto size=hover->size();const auto scale=window->devicePixelRatio();
        const QRect region(qRound(origin.x()*scale),qRound(origin.y()*scale),qRound(size.width()*scale),qRound(size.height()*scale));
        const auto resting=window->grabWindow().copy(region);
        const auto hoverPoint=hover->mapToGlobal(QPointF(size.width()/2,size.height()/2));
        QVERIFY(send("move "+QByteArray::number(hoverPoint.x())+" "+QByteArray::number(hoverPoint.y())+"\n"));
        QTRY_VERIFY(hover->property("hovered").toBool());QTest::qWait(250);
        QVERIFY(window->grabWindow().copy(region)!=resting);QCOMPARE(hover->size(),size);
        QVERIFY(window->grabWindow().save("/profile/captures/native-topbar-hover.png"));
        QWidget *tip=nullptr;
        QTRY_VERIFY_WITH_TIMEOUT(([&]{for(auto widget:QApplication::topLevelWidgets())if(widget->objectName()=="lumenButtonTooltip" && widget->isVisible()){tip=widget;return true;}return false;})(),2000);
        QCOMPARE(tip->property("text").toString(),hover->property("text").toString());
        QVERIFY(tip);QVERIFY(tip->y()>=hover->mapToGlobal(QPointF(0,hover->height())).y());
        QVERIFY(screen->geometry().contains(tip->frameGeometry()));
        QVERIFY(tip->grab().save("/profile/captures/native-button-tooltip.png"));
        QCOMPARE(window->height(),window->property("barSize").toInt());
        auto clockTarget=item("clockButton");const auto clockPoint=clockTarget->mapToGlobal(QPointF(clockTarget->width()/2,clockTarget->height()/2));
        QVERIFY(send("move "+QByteArray::number(clockPoint.x())+" "+QByteArray::number(clockPoint.y())+"\n"));
        QTRY_VERIFY(!tip->isVisible());
        QTRY_VERIFY(tip->isVisible() && tip->property("text")==clockTarget->property("text"));
        QVERIFY(screen->geometry().contains(tip->frameGeometry()));
        QVERIFY(tip->grab().save("/profile/captures/native-clock-tooltip.png"));
        auto temporaryAnchor=new QQuickItem(window->contentItem());temporaryAnchor->setSize(QSizeF(20,20));
        data.tooltip(temporaryAnchor,"Kurzlebige App-Taste");QVERIFY(tip->isVisible());
        delete temporaryAnchor;QTRY_VERIFY(!tip->isVisible());
        for(const auto &name:{"launcherButton","activeAppButton","applicationMenu_0","clockButton"})
            QCOMPARE(qvariant_cast<QFont>(item(name)->property("font")).pixelSize(),QApplication::font().pixelSize());
        const auto twice=[&](const QString &trigger,const char *name){
            auto control=item(trigger);auto menu=window->findChild<QObject*>(name);
            QVERIFY2(control && menu && control->isVisible(),qPrintable(trigger));
            QVERIFY2(click(control),qPrintable(trigger));QTRY_VERIFY2(menu->property("opened").toBool(),qPrintable(trigger));
            QVERIFY2(click(control),qPrintable(trigger));QTRY_VERIFY2(!menu->property("visible").toBool(),qPrintable(trigger));
        };
        twice("programsButton","appsPopup");twice("launcherButton","appsPopup");
        twice("notificationsButton","quickMenu");twice("compactControlsButton","quickMenu");
        twice("clockButton","calendarPopup");twice("activeAppButton","windowMenu");
        twice("recentContentButton","activityPopup");twice("windowOverviewButton","activityPopup");
        twice(data.layout()=="classic"?"activityButton":"activityCompactButton","activityPopup");
        if(item("networkButton")->isVisible())twice("networkButton","quickMenu");
        if(item("systemControlsButton")->isVisible())twice("systemControlsButton","quickMenu");
        if(item("menuOverflowButton")->isVisible())twice("menuOverflowButton",menus->entries().isEmpty()?"windowMenu":"menuOverflow");
        if(item("askButton")->isVisible())twice("askButton","askPopup");
        QVERIFY(click(item("clockButton")));QTRY_VERIFY(window->findChild<QObject*>("calendarPopup")->property("opened").toBool());
        QVERIFY(click(item("launcherButton")));QTRY_VERIFY(window->findChild<QObject*>("appsPopup")->property("opened").toBool());
        QVERIFY(!window->findChild<QObject*>("calendarPopup")->property("visible").toBool());
        QVERIFY(click(item("recentContentButton")));QTRY_VERIFY(window->findChild<QObject*>("activityPopup")->property("opened").toBool());
        QVERIFY(!window->findChild<QObject*>("appsPopup")->property("visible").toBool());
        QVERIFY(click(item("windowOverviewButton")));QTRY_COMPARE(window->findChild<QObject*>("activityPopup")->property("page").toString(),QString("windows"));
        QVERIFY(click(item("windowOverviewButton")));QTRY_VERIFY(!window->findChild<QObject*>("activityPopup")->property("visible").toBool());
        QVERIFY(click(item("notificationsButton")));
        auto notesPeek=window->findChild<QObject*>("quickMenu");
        QTRY_VERIFY(notesPeek && notesPeek->property("opened").toBool());
        QTRY_VERIFY(window->height()>150);
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!notesPeek->property("opened").toBool());
        auto launch=item("launcherButton");QVERIFY(launch);QVERIFY(click(launch));
        auto quick=window->findChild<QObject*>("quickMenu");QVERIFY(quick);
        auto apps=window->findChild<QObject*>("appsPopup");QVERIFY(apps);QTRY_VERIFY_WITH_TIMEOUT(apps->property("opened").toBool(),3000);
        QVERIFY(!quick->property("visible").toBool());QVERIFY(item("startMenu")->property("lumenOnly").toBool());
        QTRY_VERIFY(item("programSearch")->hasActiveFocus());
        QCOMPARE(item("programSearch")->property("text").toString(),QString());
        for(const auto &entry:data.snapshot()["apps"].toList()){
            const QString id=entry.toMap()["id"].toString();
            QTRY_VERIFY(item("openApp_"+id) && item("openApp_"+id)->isVisible());
        }
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
        auto programsButton=item("programsButton");QVERIFY(programsButton && programsButton->isVisible());
        QVERIFY(programsButton->mapToItem(window->contentItem(),QPointF(programsButton->width(),0)).x()<=launch->mapToItem(window->contentItem(),QPointF()).x());
        const auto openStartHome=[&]{
            QVERIFY(click(programsButton));QTRY_VERIFY(apps->property("opened").toBool());
            QVERIFY(!quick->property("visible").toBool());
            QVERIFY(!item("startMenu")->property("lumenOnly").toBool());
            QVERIFY(!item("startMenu")->property("library").toBool());
        };
        openStartHome();
        QTRY_VERIFY(item("programSearch")->hasActiveFocus());
        QCOMPARE(apps->property("x").toInt(),12);
        QCOMPARE(apps->property("y").toInt(),window->property("barSize").toInt()-(window->property("classic").toBool()?13:1));
        QVERIFY(send("key 37\n"));QTRY_VERIFY(apps->property("opened").toBool());
        QTRY_COMPARE(item("programSearch")->property("text").toString(),QString("k"));
        QVERIFY(send("key 18\n"));QTRY_COMPARE(item("programSearch")->property("text").toString(),QString("ke"));
        QVERIFY(send("key 1\n"));QTRY_COMPARE(item("programSearch")->property("text").toString(),QString());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
        openStartHome();QVERIFY(click(item("startLibraryButton")));
        QVERIFY(item("startMenu")->property("library").toBool());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
        openStartHome();QTRY_VERIFY(!item("startMenu")->property("lumenOnly").toBool());
        for(int cycle=0;cycle<8;++cycle){
            QTest::qWait(650);QVERIFY2(apps->property("opened").toBool(),qPrintable("Start menu closed during hover cycle "+QString::number(cycle)));QVERIFY(window->isActive());
            if(cycle<7){QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());openStartHome();}
        }
        QDBusInterface focusFixture("org.lumen.MenuTestA","/Control",QString());QVERIFY(focusFixture.isValid());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
        QTRY_VERIFY(([&]{const QDBusReply<bool> active=focusFixture.call("active");return active.isValid() && active.value();})());
        openStartHome();
        QTRY_VERIFY(item("startPin_5") && item("startPin_5")->isVisible());
        QTRY_VERIFY(item("startRecent_1") && item("startRecent_1")->isVisible());
        QTRY_VERIFY(!data.controlBusy());QTest::qWait(150);
        QVERIFY(window->grabWindow().save("/profile/captures/native-start-home.png"));
        QTRY_VERIFY_WITH_TIMEOUT(item("programSearch"),4000);
        auto programQuery=item("programSearch");QVERIFY(programQuery->isVisible());QTest::qWait(250);QVERIFY(apps->property("opened").toBool());programQuery->setProperty("text","lumen testprogramm");
        QTRY_COMPARE_WITH_TIMEOUT(item("programList")->property("count").toInt(),1,4000);
        const auto pins=data.pinnedApps();
        QTRY_VERIFY(item("program_0") && item("program_0")->isVisible());auto result=item("program_0");
        const auto resultPoint=result->mapToGlobal(QPointF(result->width()/2,result->height()/2));
        QVERIFY(send("right "+QByteArray::number(resultPoint.x())+" "+QByteArray::number(resultPoint.y())+"\n"));
        auto appContext=window->findChild<QObject*>("startAppContext");QVERIFY(appContext);QTRY_VERIFY(appContext->property("opened").toBool());
        QVERIFY(!appContext->property("favoriteId").toString().isEmpty());
        QVERIFY(window->grabWindow().save("/profile/captures/native-start-context.png"));
        auto favorites=window->findChild<QObject*>("startFavorites");QVERIFY(favorites);
        const auto canonicalPins=favorites->property("favorites").toStringList();
        QSignalSpy pinClicked(item("startContextPin"),SIGNAL(clicked()));QVERIFY(pinClicked.isValid());
        auto pinButton=item("startContextPin");
        QTRY_VERIFY(pinButton->window() && pinButton->window()->isExposed());
        // Locate the separate Wayland popup through its parent, after exposure.
        const auto popupOrigin=item("startMenu")->mapToGlobal(QPointF(appContext->property("x").toDouble(),appContext->property("y").toDouble()));
        const auto pinPoint=popupOrigin+pinButton->mapToScene(QPointF(pinButton->width()/2,pinButton->height()/2));
        QVERIFY(pinButton->window()->grabWindow().save("/profile/captures/native-start-context-menu.png"));
        QVERIFY(send("click "+QByteArray::number(pinPoint.x())+" "+QByteArray::number(pinPoint.y())+"\n"));
        QTRY_COMPARE(pinClicked.count(),1);
        QTRY_COMPARE(data.pinnedApps().size(),pins.size()+1);
        programQuery->setProperty("text","");QTRY_VERIFY(item("startPin_6") && item("startPin_6")->isVisible());
        QSignalSpy homePainted(window,&QQuickWindow::frameSwapped);window->update();QTRY_VERIFY(homePainted.count()>0);
        QVERIFY(click(item("startEditButton")));QTRY_VERIFY(item("startMenu")->property("editing").toBool());
        QVERIFY(click(item("startPin_6")));QTRY_COMPARE(data.pinnedApps(),canonicalPins);
        QVERIFY(click(item("startEditButton")));QTRY_VERIFY(!item("startMenu")->property("editing").toBool());
        item("startPowerButton")->forceActiveFocus(Qt::TabFocusReason);
        QTest::qWait(150);
        QTRY_VERIFY(item("startPowerButton")->mapToItem(window->contentItem(),QPointF(0,item("startPowerButton")->height())).y()<=window->height()-16);
        auto power=window->findChild<QObject*>("startPowerMenu");QVERIFY(power);
        QSignalSpy powerClicked(item("startPowerButton"),SIGNAL(clicked()));
        QVERIFY(window->grabWindow().save("/profile/captures/native-start-before-power.png"));
        QVERIFY(click(item("startPowerButton")));QTest::qWait(150);
        QTRY_COMPARE(powerClicked.count(),1);QTRY_VERIFY(power->property("opened").toBool());
        auto powerContent=qvariant_cast<QQuickItem*>(power->property("contentItem"));QVERIFY(powerContent);QTRY_VERIFY(powerContent->window() && powerContent->window()->isExposed());
        QVERIFY(powerContent->window()->grabWindow().save("/profile/captures/native-start-power.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!power->property("opened").toBool());QVERIFY(apps->property("opened").toBool());
        QVERIFY(click(item("startLibraryButton")));QTRY_VERIFY(item("startMenu")->property("library").toBool());
        QTest::qWait(150);QVERIFY(window->grabWindow().save("/profile/captures/native-start-library.png"));
        const int allAppsCount=item("programList")->property("count").toInt();QVERIFY(allAppsCount>0);
        QTRY_VERIFY(item("startCategory_0") && item("startCategory_0")->isVisible());QVERIFY(click(item("startCategory_0")));
        QTRY_VERIFY(item("programList")->property("count").toInt()>0 && item("programList")->property("count").toInt()<allAppsCount);
        QTest::qWait(100);QVERIFY(window->grabWindow().save("/profile/captures/native-start-category.png"));
        QVERIFY(click(item("startCategoryAll")));QTRY_COMPARE(item("programList")->property("count").toInt(),allAppsCount);
        QVERIFY(click(item("startCategoryLumen")));QTRY_VERIFY(item("openApp_files") && item("openApp_files")->isVisible());
        QVERIFY(click(item("startLibraryButton")));QTRY_VERIFY(!item("startMenu")->property("lumenOnly").toBool());
        programQuery->setProperty("text","lumen testprogramm");
        QTRY_COMPARE(item("programList")->property("count").toInt(),1);
        QVERIFY(click(programQuery));QTest::qWait(150);QVERIFY(apps->property("opened").toBool());
        QVERIFY(window->grabWindow().save("/profile/captures/native-start-menu.png"));
        QVERIFY(send("key 28\n"));QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/program-started"),4000);
        QTRY_VERIFY(!apps->property("opened").toBool());
        openStartHome();
        programQuery=item("programSearch");QVERIFY(programQuery);programQuery->setProperty("text","lumen testprogramm");
        QTRY_COMPARE(item("programList")->property("count").toInt(),1);QTRY_VERIFY(item("program_0") && item("program_0")->isVisible());
        QVERIFY(click(programQuery));QTest::qWait(150);
        const auto actionAnchor=item("program_0")->mapToGlobal(QPointF(30,30));
        QVERIFY(send("right "+QByteArray::number(actionAnchor.x())+" "+QByteArray::number(actionAnchor.y())+"\n"));
        QTRY_VERIFY(appContext->property("opened").toBool());QQuickItem *jump=nullptr;
        QTRY_VERIFY(([&]{for(auto node:window->findChildren<QQuickItem*>())if(node->objectName().startsWith("startNativeAction_") && node->property("text").toString()=="Neues Testfenster"){jump=node;return true;}return false;})());
        QTRY_VERIFY(jump->window() && jump->window()->isExposed());
        const auto actionOrigin=item("startMenu")->mapToGlobal(QPointF(appContext->property("x").toDouble(),appContext->property("y").toDouble()));
        const auto actionPoint=actionOrigin+jump->mapToScene(QPointF(jump->width()/2,jump->height()/2));
        QVERIFY(send("click "+QByteArray::number(actionPoint.x())+" "+QByteArray::number(actionPoint.y())+"\n"));
        QTRY_VERIFY(QFile::exists("/profile/program-new-window"));QTRY_VERIFY(!apps->property("opened").toBool());
        openStartHome();QTRY_VERIFY(!data.controlBusy());
        QTRY_VERIFY(item("startRecent_0") && item("startRecent_0")->isVisible());const auto beforeRecent=actions().size();
        QVERIFY(click(item("startRecent_0")));QTRY_VERIFY(actions().size()>beforeRecent && actions().contains("/profile/example.txt"));QTRY_VERIFY(!apps->property("opened").toBool());
        QVERIFY(click(launch));QTRY_VERIFY(apps->property("opened").toBool());
        QVERIFY(!quick->property("visible").toBool());QVERIFY(item("startMenu")->property("lumenOnly").toBool());
        QVERIFY(send("key 33\n"));QTRY_COMPARE(programQuery->property("text").toString(),QString("f"));
        QVERIFY(click(programsButton));QTRY_VERIFY(apps->property("opened").toBool() && !item("startMenu")->property("lumenOnly").toBool());
        QVERIFY(programQuery->property("text").toString().isEmpty());
        QVERIFY(click(launch));QTRY_VERIFY(apps->property("opened").toBool() && item("startMenu")->property("lumenOnly").toBool());
        QVERIFY(!item("startMenu")->property("searching").toBool());QTRY_VERIFY(programQuery->hasActiveFocus());
        QTest::qWait(160);QVERIFY(window->grabWindow().save("/profile/captures/native-direct-lumen.png"));
        QTest::qWait(180);QVERIFY(click(item("startLibraryButton")));QTRY_VERIFY(!item("startMenu")->property("lumenOnly").toBool());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
        QVERIFY(!QFile::exists("/profile/conversation-started"));
        auto composer=item("inlineComposer");QVERIFY(composer);
        if(!composer->isVisible()){QVERIFY(click(item("askButton")));QTest::qWait(180);composer=item("popupComposer");}
        QVERIFY(composer);auto question=find(composer,"lumenQuestion");QVERIFY(question && question->isVisible());
        QCOMPARE(qvariant_cast<QFont>(question->property("font")).pixelSize(),QApplication::font().pixelSize());
        const QString questionText=QStringLiteral("Was muss ich für den VCF Workshop noch vorbereiten?");
        question->setProperty("text",questionText);QVERIFY(click(question));QTRY_VERIFY(question->hasActiveFocus());QTest::qWait(150);QVERIFY(question->hasActiveFocus());
        QVERIFY(window->grabWindow().save("/profile/captures/native-question.png"));
        QVERIFY(send("key 28\n"));QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/asked.json"),3000);
        QFile asked("/profile/asked.json");QVERIFY(asked.open(QIODevice::ReadOnly));
        QCOMPARE(QJsonDocument::fromJson(asked.readAll()).object()["prompt"].toString(),questionText);
        QTRY_VERIFY(question->property("text").toString().isEmpty());
        auto conversation=item("topbarConversation");QVERIFY(conversation);
        QTRY_VERIFY(window->property("conversationOpen").toBool());
        QTRY_VERIFY(find(conversation,"conversationComposer"));
        QTest::qWait(150);QVERIFY(window->grabWindow().save("/profile/captures/native-conversation-attached.png"));
        QVERIFY(island->height()>window->property("barSize").toInt());
        auto followup=find(conversation,"conversationComposer");QVERIFY(followup);
        followup->setProperty("text",QString("Dieselbe Folgefrage behalten"));
        QVERIFY(click(find(conversation,"detachConversation")));
        auto detached=window->findChild<QQuickWindow*>("detachedConversation");QVERIFY(detached);
        QTRY_VERIFY(detached->isVisible() && !window->property("conversationOpen").toBool());
        QTRY_VERIFY_WITH_TIMEOUT(detached->isActive(),3000);
        QTRY_VERIFY(conversation->window()==detached);
        QCOMPARE(followup->property("text").toString(),QString("Dieselbe Folgefrage behalten"));
        QTest::qWait(150);QVERIFY(detached->grabWindow().save("/profile/captures/native-conversation-detached.png"));
        auto maximize=find(conversation,"conversationMaximize");QVERIFY(maximize);
        maximize->forceActiveFocus(Qt::TabFocusReason);QVERIFY(send("key 57\n"));QTRY_COMPARE(detached->visibility(),QWindow::Maximized);
        maximize->forceActiveFocus(Qt::TabFocusReason);QVERIFY(send("key 57\n"));QTRY_COMPARE(detached->visibility(),QWindow::Windowed);
        {
            auto state=window->findChild<QObject*>("activeWindowState");QVERIFY(state);
            auto tasks=qobject_cast<QAbstractItemModel*>(qvariant_cast<QObject*>(state->property("windowModel")));QVERIFY(tasks);
            const auto roles=tasks->roleNames();const int pidRole=roles.key("AppPid",-1),minimizedRole=roles.key("IsMinimized",-1);QVERIFY(pidRole>=0 && minimizedRole>=0);
            const auto minimized=[&]{for(int row=0;row<tasks->rowCount();++row){const auto index=tasks->index(row,0);if(tasks->data(index,pidRole).toLongLong()==QCoreApplication::applicationPid())return tasks->data(index,minimizedRole).toBool();}return false;};
            auto minimize=find(conversation,"conversationMinimize");QVERIFY(minimize);
            minimize->forceActiveFocus(Qt::TabFocusReason);QVERIFY(send("key 57\n"));QTRY_VERIFY(minimized());
            detached->showNormal();detached->requestActivate();QTRY_VERIFY(!minimized() && detached->isActive());
        }
        // Wayland does not expose a normal window's global position; use its real keyboard focus.
        auto reattach=find(conversation,"detachConversation");QVERIFY(reattach);
        reattach->forceActiveFocus(Qt::TabFocusReason);QTRY_VERIFY(reattach->hasActiveFocus());
        QVERIFY(send("key 57\n"));QTRY_VERIFY(!detached->isVisible() && window->property("conversationOpen").toBool());
        QCOMPARE(conversation->window(),window);
        QCOMPARE(followup->property("text").toString(),QString("Dieselbe Folgefrage behalten"));
        for(int gesture=0;gesture<2;++gesture){
            QGuiApplication::sync();QSignalSpy frame(window,&QQuickWindow::frameSwapped);window->update();QTRY_VERIFY(!frame.isEmpty());
            qInfo()<<"CONVERSATION_GESTURE"<<gesture;
            auto dragArea=find(conversation,"conversationDragArea");QVERIFY(dragArea);
            auto dragPoint=dragArea->mapToGlobal(QPointF(40,dragArea->height()/2));
            QVERIFY(send("move "+QByteArray::number(dragPoint.x())+" "+QByteArray::number(dragPoint.y())+"\n"));
            QVERIFY(send("down\n"));QVERIFY(send("move "+QByteArray::number(dragPoint.x()+30)+" "+QByteArray::number(dragPoint.y()+100)+"\n"));
            QTRY_VERIFY(detached->isVisible());QTRY_VERIFY(window->property("conversationMoveReady").toBool());
            if(gesture==1){QVERIFY(send("move "+QByteArray::number(dragPoint.x()+90)+" "+QByteArray::number(dragPoint.y()+160)+"\n"));}QVERIFY(send("up\n"));
            QTRY_VERIFY_WITH_TIMEOUT(detached->isActive(),3000);
            if(gesture==1){QVERIFY(click(question));}
            else{reattach->forceActiveFocus(Qt::TabFocusReason);QTRY_VERIFY(reattach->hasActiveFocus());QVERIFY(send("key 57\n"));}
            QTRY_VERIFY(!detached->isVisible() && window->property("conversationOpen").toBool());
            QTRY_VERIFY_WITH_TIMEOUT(window->isActive(),3000);
            QCOMPARE(followup->property("text").toString(),QString("Dieselbe Folgefrage behalten"));
        }
        QVERIFY(click(find(conversation,"collapseConversation")));QTRY_VERIFY(!window->property("conversationOpen").toBool());
        QVERIFY(click(item("conversationToggle")));QTRY_VERIFY(window->property("conversationOpen").toBool());
        QCOMPARE(followup->property("text").toString(),QString("Dieselbe Folgefrage behalten"));
        followup->setProperty("text",QString());
        auto dictate=item("compactDictateButton");if(!dictate->isVisible())dictate=find(item("inlineComposer"),"dictateButton");
        QVERIFY(dictate && dictate->isVisible());QVERIFY(click(dictate));QTRY_VERIFY_WITH_TIMEOUT(actions().contains("\"voice\""),3000);
        QVERIFY(click(item("windowOverviewButton")));
        auto activities=window->findChild<QObject*>("activityPopup");QVERIFY(activities);QTRY_VERIFY(activities->property("opened").toBool());
        QTRY_VERIFY(item("overviewWindow_0") && item("overviewWindow_0")->isVisible());QTest::qWait(150);
        QVERIFY(window->grabWindow().save("/profile/captures/native-window-overview.png"));
        auto activeState=window->findChild<QObject*>("activeWindowState");QVERIFY(activeState);
        auto windowModel=qvariant_cast<QObject*>(activeState->property("windowModel"));QVERIFY(windowModel);
        QQuickItem *notesWindow=nullptr;
        for(int index=0;index<windowModel->property("count").toInt();++index){
            auto candidate=item("overviewWindow_"+QString::number(index));
            if(candidate && candidate->property("text").toString().startsWith(QStringLiteral("Lumen Menütest A"))){notesWindow=candidate;break;}
        }
        QVERIFY(notesWindow);QVERIFY(click(notesWindow));QTRY_VERIFY(!activities->property("opened").toBool());
        QTRY_VERIFY(([&]{const QDBusReply<bool> active=focusFixture.call("active");return active.isValid() && active.value();})());
        QTRY_COMPARE(menus->entries().size(),4);
        QVERIFY(click(item("recentContentButton")));QTRY_VERIFY(activities->property("opened").toBool());
        QTRY_COMPARE(activities->property("page").toString(),QString("recent"));
        QTRY_VERIFY(item("recentContent_0") && item("recentContent_0")->isVisible());
        QTRY_VERIFY(!data.controlBusy());QVERIFY(click(item("recentContent_0")));QTRY_VERIFY(actions().contains("/profile/example.txt"));
        QVERIFY(window->grabWindow().save("/profile/captures/native-recent-content.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!activities->property("opened").toBool());
        QVERIFY(click(item(data.layout()=="classic"?"activityButton":"activityCompactButton")));QTRY_VERIFY(activities->property("opened").toBool());
        QTRY_VERIFY(item("reviewDecision_0") && item("reviewDecision_0")->isVisible());QTRY_VERIFY(!data.controlBusy());
        QVERIFY(click(item("reviewDecision_0")));QTRY_VERIFY(actions().contains(QByteArray(32,'b')));
        QFile resolved("/profile/decision-resolved");QVERIFY(resolved.open(QIODevice::WriteOnly));resolved.close();
        QTRY_VERIFY(!data.controlBusy());data.refresh();QTRY_VERIFY(data.snapshot()["activity"].toMap()["decisions"].toList().isEmpty());QTest::qWait(180);
        QVERIFY(click(item("activitySection_focus")));QTRY_VERIFY(item("focusToggleButton")->isVisible());QTest::qWait(180);QTRY_VERIFY(!data.controlBusy());
        QVERIFY(window->grabWindow().save("/profile/captures/native-focus-before-start.png"));
        QVERIFY(click(item("focusToggleButton")));QTRY_COMPARE(data.snapshot()["activity"].toMap()["focus"].toMap()["state"].toString(),QString("running"));
        QTest::qWait(150);QVERIFY(window->grabWindow().save("/profile/captures/native-focus.png"));
        QTRY_VERIFY(!data.controlBusy());QVERIFY(click(item("focusToggleButton")));QTRY_COMPARE(data.snapshot()["activity"].toMap()["focus"].toMap()["state"].toString(),QString("paused"));
        QVERIFY(click(item("activitySection_dnd")));QTRY_VERIFY(item("dndToggleButton")->isVisible());QTest::qWait(180);QVERIFY(click(item("dndToggleButton")));QTRY_VERIFY(window->property("quiet").toBool());
        QVERIFY(click(item("dndToggleButton")));QTRY_VERIFY(!window->property("quiet").toBool());
        QVERIFY(click(item("activitySection_media")));QTest::qWait(180);QTRY_COMPARE(data.players().size(),1);QTRY_VERIFY(item("mediaPlayButton")->isEnabled());
        QVERIFY(click(item("mediaPlayButton")));QTRY_VERIFY(data.players()[0].toMap()["playing"].toBool());
        QVERIFY(window->grabWindow().save("/profile/captures/native-media.png"));
        QVERIFY(click(item("mediaNextButton")));QTRY_VERIFY(QFile::exists("/profile/media-next"));
        QVERIFY(click(item("activitySection_update")));QTRY_VERIFY(item("openUpdaterButton")->isVisible());QTest::qWait(180);QTRY_VERIFY(!data.controlBusy());
        QVERIFY(click(item("openUpdaterButton")));QTRY_VERIFY(actions().contains("update"));
        QVERIFY(click(item("activitySection_focus")));QTest::qWait(180);QTRY_VERIFY(!data.controlBusy());QVERIFY(click(item("focusStopButton")));QTRY_COMPARE(data.snapshot()["activity"].toMap()["focus"].toMap()["state"].toString(),QString("off"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!activities->property("opened").toBool());
        auto clock=item("clockButton");QVERIFY(clock);QVERIFY(click(clock));
        auto calendar=window->findChild<QObject*>("calendarPopup");QVERIFY(calendar);
        QTRY_VERIFY(calendar->property("opened").toBool());QTest::qWait(200);
        QVERIFY(calendar->property("opened").toBool());QVERIFY(window->height()>56);
        QVERIFY(window->grabWindow().save("/profile/captures/native-calendar.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!calendar->property("opened").toBool());
        QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),1,4000);
        QTRY_VERIFY_WITH_TIMEOUT(item("trayItem_0"),2000);
        auto trayButton=item("trayItem_0");
        if(!trayButton->isVisible()){QVERIFY(click(item("trayMoreButton")));QTRY_VERIFY(item("overflowTray_0"));trayButton=item("overflowTray_0");QTest::qWait(180);}
        QVERIFY(trayButton->isVisible());
        const auto trayPoint=trayButton->mapToGlobal(QPointF(trayButton->width()/2,trayButton->height()/2));
        QVERIFY(send("right "+QByteArray::number(trayPoint.x())+" "+QByteArray::number(trayPoint.y())+"\n"));
        QTRY_VERIFY_WITH_TIMEOUT(tray.opened(),3000);
        auto trayMenu=qobject_cast<QMenu*>(QApplication::activePopupWidget());QVERIFY(trayMenu);
        QTRY_VERIFY(trayMenu->isActiveWindow());QTRY_VERIFY(trayMenu->windowHandle()->isExposed());
        QTRY_VERIFY(!trayMenu->actions().isEmpty() && trayMenu->actions()[0]->text()==QStringLiteral("Tray-Testaktion"));
        QVERIFY(trayMenu->grab().save("/profile/captures/native-tray-menu.png"));
        QVERIFY(send("key 108\n"));QTRY_VERIFY(trayMenu->activeAction()!=nullptr);QTest::qWait(70);QVERIFY(send("key 28\n"));
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/tray-action.txt"),3000);
        QDBusInterface trayControl("org.lumen.TrayTest","/Control",QString());
        QVERIFY(trayControl.call("populate",4).type()!=QDBusMessage::ErrorMessage);
        QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),4,4000);
        if(window->width()>=900)QTRY_VERIFY_WITH_TIMEOUT(item("trayItem_0")->isVisible(),2000);
        QTest::qWait(150);QVERIFY(window->grabWindow().save("/profile/captures/native-tray-applications.png"));
        const auto population=trayControl.call("populate",40);
        QVERIFY2(population.type()!=QDBusMessage::ErrorMessage,qPrintable(population.errorMessage()));
        QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),40,4000);
        QTRY_VERIFY_WITH_TIMEOUT(window->property("shownTray").toInt()<40,2000);
        QTRY_VERIFY_WITH_TIMEOUT(item("trayMoreButton")->isVisible(),2000);
        QVERIFY(item("inlineComposer")->width()>=200);
        auto lastVisible=item("trayItem_"+QString::number(window->property("shownTray").toInt()-1));
        if(lastVisible){QVERIFY(lastVisible->isVisible());QVERIFY(lastVisible->mapToItem(window->contentItem(),QPointF()).x()>=0);}
        twice("trayMoreButton","trayPopup");
        QVERIFY(click(item("trayMoreButton")));
        auto trayPopup=window->findChild<QObject*>("trayPopup");QVERIFY(trayPopup);
        QTRY_VERIFY_WITH_TIMEOUT(trayPopup->property("opened").toBool(),2000);
        QTRY_VERIFY(window->isActive());
        QTRY_VERIFY_WITH_TIMEOUT(item("overflowTray_39") && item("overflowTray_39")->isVisible(),2000);
        auto lastTray=item("overflowTray_39");
        QTRY_VERIFY(lastTray->y()>39*lastTray->height());
        lastTray->forceActiveFocus(Qt::TabFocusReason);
        QTRY_VERIFY(lastTray->hasActiveFocus());
        QTRY_VERIFY(lastTray->mapToItem(window->contentItem(),QPointF(0,lastTray->height())).y()<=window->height()-16);
        QSignalSpy painted(window,&QQuickWindow::frameSwapped);window->update();QTRY_VERIFY(painted.count()>0);
        QTest::qWait(150);QVERIFY(window->grabWindow().save("/profile/captures/native-tray-overflow.png"));
        const auto lastTrayPoint=lastTray->mapToGlobal(QPointF(lastTray->width()/2,lastTray->height()/2));
        QVERIFY(send("move "+QByteArray::number(lastTrayPoint.x())+" "+QByteArray::number(lastTrayPoint.y())+"\n"));
        QTRY_VERIFY(lastTray->property("hovered").toBool());
        QVERIFY(send("right "+QByteArray::number(lastTrayPoint.x())+" "+QByteArray::number(lastTrayPoint.y())+"\n"));
        QTRY_VERIFY_WITH_TIMEOUT(tray.opened(),3000);
        QTRY_VERIFY(QApplication::activePopupWidget() && QApplication::activePopupWidget()->isActiveWindow());
        QTRY_VERIFY(QApplication::activePopupWidget()->windowHandle()->isExposed());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!tray.opened());
        QVERIFY(send("key 1\n"));
        QVERIFY(trayControl.call("quit").type()!=QDBusMessage::ErrorMessage);
        QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),0,3000);
        QTRY_COMPARE(window->property("shownTray").toInt(),0);
        QTRY_VERIFY(!item("trayMoreButton")->isVisible());
        QDBusInterface fixture("org.lumen.MenuTestA","/Control",QString());QVERIFY(fixture.call("command","fullscreen").type()!=QDBusMessage::ErrorMessage);
        QTRY_VERIFY_WITH_TIMEOUT(!window->isVisible(),3000);
        QVERIFY(fixture.call("command","normal").type()!=QDBusMessage::ErrorMessage);QTRY_VERIFY_WITH_TIMEOUT(window->isVisible(),3000);
        if(!qgetenv("LUMEN_QA_SHORTCUTS").isEmpty()){QVERIFY(send("key 125\n"));}
        else data.ShowApps();
        QTRY_VERIFY(apps->property("opened").toBool());QTRY_VERIFY(window->isActive());
        QVERIFY(!quick->property("visible").toBool());QTRY_VERIFY(item("programSearch")->hasActiveFocus());
        QTRY_VERIFY(item("startPin_0")->isVisible());
        if(!qgetenv("LUMEN_QA_SHORTCUTS").isEmpty()){
            QVERIFY(!item("startMenu")->property("lumenOnly").toBool());
            QVERIFY(window->grabWindow().save("/profile/captures/native-shortcut-start.png"));
            QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
            QVERIFY(send("press 56\n"));QVERIFY(send("key 57\n"));QVERIFY(send("release 56\n"));
            QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/lumen-shortcut-started"),5000);
        }
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
        auto audioPopup=window->findChild<QObject*>("audioPopup");auto networkPopup=window->findChild<QObject*>("networkPopup");QVERIFY(audioPopup && networkPopup);
        const auto openDevice=[&](const char* button,const QString &topic,QObject *full){
            if(item(button)->isVisible()){
                QVERIFY(click(item(button)));QTRY_VERIFY(quick->property("opened").toBool());
                QTest::qWait(180);QVERIFY(window->grabWindow().save("/profile/captures/native-"+topic+"-preview.png"));
                QVERIFY(click(item("quickRow_1")));
            }else{
                QVERIFY(click(item("compactControlsButton")));QTRY_VERIFY(quick->property("opened").toBool());
                QVERIFY(click(item("quickRow_"+topic)));QTRY_VERIFY(full->property("opened").toBool());
                QCOMPARE(full->property("section").toInt(),0);QVERIFY(click(item(topic+"Section1")));
            }
            QTRY_VERIFY(full->property("opened").toBool());QCOMPARE(full->property("section").toInt(),1);
        };
        openDevice("systemControlsButton","audio",audioPopup);QVERIFY(!networkPopup->property("opened").toBool());
        QTRY_VERIFY_WITH_TIMEOUT(data.details()["audio"].toMap()["available"].toBool(),3000);
        QVERIFY(window->grabWindow().save("/profile/captures/native-audio-overview.png"));
        for(int section=1;section<6;++section){
            QVERIFY(click(item("audioSection"+QString::number(section))));QTest::qWait(50);
            QCOMPARE(audioPopup->property("section").toInt(),section);
            QVERIFY(window->grabWindow().save("/profile/captures/native-audio-"+QString::number(section)+".png"));
        }
        QVERIFY(click(item("audioSection1")));QTest::qWait(80);item("deviceDefaultoutput8")->forceActiveFocus();QTest::qWait(100);QVERIFY(click(item("deviceDefaultoutput8")));
        QTRY_VERIFY(data.details()["audio"].toMap()["outputs"].toList()[1].toMap()["default"].toBool());
        QVERIFY(click(item("audioSection2")));QTest::qWait(80);item("deviceMuteinput9")->forceActiveFocus();QTest::qWait(100);QVERIFY(click(item("deviceMuteinput9")));
        QTRY_VERIFY(data.details()["audio"].toMap()["inputs"].toList()[0].toMap()["muted"].toBool());
        QVERIFY(click(item("audioSection3")));QTest::qWait(80);
        auto route=item("streamRoute12");QVERIFY(route && route->isVisible());route->forceActiveFocus();QTest::qWait(100);QVERIFY(click(route));
        auto routePopup=qvariant_cast<QObject*>(route->property("popup"));QVERIFY(routePopup);QTRY_VERIFY(routePopup->property("visible").toBool());
        auto routeBackground=qvariant_cast<QQuickItem*>(routePopup->property("background"));QVERIFY(routeBackground);
        const auto routeTop=routeBackground->mapToGlobal(QPointF());
        QVERIFY(routeTop.y()>=audioPopup->property("y").toReal()-1);
        QVERIFY(routeTop.y()+routeBackground->height()<=audioPopup->property("y").toReal()+audioPopup->property("height").toReal()+1);
        const auto anchorTop=route->mapToGlobal(QPointF()).y();const auto anchorBottom=anchorTop+route->height();
        const auto above=anchorTop-audioPopup->property("y").toReal()-16;
        const auto below=audioPopup->property("y").toReal()+audioPopup->property("height").toReal()-16-anchorBottom;
        if(qMax(above,below)>=routeBackground->height())QVERIFY(routeTop.y()>=anchorBottom-1 || routeTop.y()+routeBackground->height()<=anchorTop+1);
        QVERIFY(window->grabWindow().save("/profile/captures/native-audio-routing.png"));
        QVERIFY(send("key 108\n"));QVERIFY(send("key 28\n"));
        QTRY_COMPARE(data.details()["audio"].toMap()["playback"].toList()[0].toMap()["device"].toString(),QString("8"));
        QVERIFY(click(item("audioSection0")));QTest::qWait(50);
        auto slider=item("volumeSlider");QVERIFY(slider);slider->forceActiveFocus();QVERIFY(send("key 106\n"));
        QTRY_COMPARE_WITH_TIMEOUT(data.snapshot()["system"].toMap()["volume"].toInt(),51,3000);
        QTRY_VERIFY(!slider->property("pending").toBool());
        QVERIFY(click(item("muteButton")));QTRY_VERIFY_WITH_TIMEOUT(data.snapshot()["system"].toMap()["muted"].toBool(),3000);
        data.control("volume",13);data.control("hardware");
        QTRY_VERIFY_WITH_TIMEOUT(data.error().contains("Synthetischer Kontrollfehler"),3000);
        QVERIFY(item("systemErrorButton")->isVisible());
        QVERIFY(window->grabWindow().save("/profile/captures/native-controls.png"));
        QVERIFY(send("key 1\n"));
        openDevice("networkButton","network",networkPopup);QVERIFY(!audioPopup->property("opened").toBool());
        QTRY_VERIFY_WITH_TIMEOUT(data.details()["network"].toMap()["available"].toBool(),3000);
        QVERIFY(window->grabWindow().save("/profile/captures/native-network-overview.png"));
        for(int section=1;section<6;++section){
            QVERIFY(click(item("networkSection"+QString::number(section))));QTest::qWait(50);
            QCOMPARE(networkPopup->property("section").toInt(),section);
            QVERIFY(window->grabWindow().save("/profile/captures/native-network-"+QString::number(section)+".png"));
        }
        QVERIFY(click(item("networkSection1")));QTest::qWait(80);
        auto wifi=item("wifiSwitch");QVERIFY(wifi && wifi->isVisible());QVERIFY(click(wifi));
        QTRY_VERIFY(!data.details()["network"].toMap()["wifiEnabled"].toBool());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!networkPopup->property("opened").toBool());
        QVERIFY(item("compactControlsButton")->isVisible());QVERIFY(click(item("compactControlsButton")));
        QTRY_VERIFY(quick->property("opened").toBool());
        QCOMPARE(quick->property("x").toInt()+quick->property("width").toInt(),window->width()-12);
        QTest::qWait(120);QVERIFY(window->grabWindow().save("/profile/captures/native-settings-preview.png"));
        QVERIFY(click(item("quickMore")));
        auto generalControls=window->findChild<QObject*>("systemPopup");QVERIFY(generalControls);QTRY_VERIFY(generalControls->property("opened").toBool());
        QVERIFY(!audioPopup->property("opened").toBool());QVERIFY(!networkPopup->property("opened").toBool());
        QVERIFY(window->grabWindow().save("/profile/captures/native-general-controls.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!generalControls->property("opened").toBool());
        openStartHome();
        item("startSettingsButton")->forceActiveFocus();QTest::qWait(120);QVERIFY(click(item("startSettingsButton")));
        QTRY_VERIFY(quick->property("opened").toBool());QCOMPARE(window->property("quickTopic").toString(),QString("settings"));
        QVERIFY(click(item("quickRow_preferences")));QTRY_VERIFY(actions().contains("--settings"));
        QQmlComponent secondComponent(&engine,QUrl("qrc:/lumen/Topbar.qml"));
        QScopedPointer<QObject> secondOwner(secondComponent.create());auto second=qobject_cast<QQuickWindow*>(secondOwner.data());QVERIFY(second);
        auto secondScreen=QGuiApplication::screens()[1];second->setScreen(secondScreen);second->setGeometry(secondScreen->geometry().x(),secondScreen->geometry().y(),secondScreen->geometry().width(),56);
        auto secondLayer=LayerShellQt::Window::get(second);secondLayer->setScreen(secondScreen);
        secondLayer->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop)|LayerShellQt::Window::AnchorLeft|LayerShellQt::Window::AnchorRight);
        secondLayer->setLayer(LayerShellQt::Window::LayerTop);secondLayer->setExclusiveZone(second->property("barSize").toInt());secondLayer->setActivateOnShow(false);
        second->setProperty("ready",true);QTRY_VERIFY(second->isExposed());
        QCOMPARE(second->width(),secondScreen->geometry().width());QCOMPARE(second->x(),secondScreen->geometry().x());
        QVERIFY(second->grabWindow().save("/profile/captures/native-second-screen.png"));
        data.control("display");QTRY_VERIFY(data.error().isEmpty());
        const auto originalLayout=data.layout();
        QSettings settings("Lumen","Assistant");
        auto draft=find(find(window->contentItem(),"inlineComposer"),"lumenQuestion");QVERIFY(draft);
        draft->setProperty("text",QStringLiteral("Entwurf bleibt beim Layoutwechsel erhalten"));
        for(const auto &layout:{"band","deck","context","classic"}){
            settings.setValue("topbar/layout",layout);settings.sync();
            QTRY_COMPARE_WITH_TIMEOUT(data.layout(),QString(layout),1500);
            const int expected=QString(layout)=="deck"?118:QString(layout)=="band"?68:QString(layout)=="context"?60:window->width()<1320?118:80;
            QTRY_COMPARE(window->property("barSize").toInt(),expected);QTRY_COMPARE(second->property("barSize").toInt(),expected);
            QTRY_COMPARE(layer->exclusionZone(),expected);QTRY_COMPARE(secondLayer->exclusionZone(),expected);
            QCOMPARE(draft->property("text").toString(),QStringLiteral("Entwurf bleibt beim Layoutwechsel erhalten"));
            QTest::qWait(120);
            QVERIFY(window->grabWindow().save("/profile/captures/layout-"+QString(layout)+".png"));
        }
        settings.setValue("topbar/layout","context");settings.sync();QTRY_COMPARE(data.layout(),QString("context"));
        QTest::qWait(180);
        auto contextComposer=find(window->contentItem(),"inlineComposer");
        QString prefix="dock";
        if(contextComposer->isVisible()){QVERIFY(click(find(contextComposer,"lumenQuestion")));}
        else{QVERIFY(click(find(window->contentItem(),"askButton")));QTRY_VERIFY(find(window->contentItem(),"popupComposer"));contextComposer=find(window->contentItem(),"popupComposer");prefix="popup";}
        QVERIFY(!find(window->contentItem(),prefix+"attachFileButton"));
        auto attachedQuestion=find(contextComposer,"lumenQuestion");QVERIFY(attachedQuestion);
        QTRY_VERIFY(find(window->contentItem(),prefix+"attachNoteButton"));
        auto attachNote=find(window->contentItem(),prefix+"attachNoteButton");QTRY_VERIFY(attachNote->isVisible());QTest::qWait(180);
        QVERIFY(click(attachNote));
        QTRY_VERIFY(window->property("noteContext").toMap().contains("reference"));
        QCOMPARE(window->property("noteContext").toMap()["reference"].toMap()["title"].toString(),QString("Workshop in Notes"));
        QTest::qWait(180);
        QVERIFY(window->grabWindow().save("/profile/captures/native-notes-context.png"));
        attachedQuestion->setProperty("text",QString("Fasse die Notes-Notiz zusammen."));
        QFile::remove("/profile/asked.json");QVERIFY(click(find(contextComposer,"sendQuestionButton")));
        QTRY_VERIFY(QFile::exists("/profile/asked.json"));QFile noteAsk("/profile/asked.json");QVERIFY(noteAsk.open(QIODevice::ReadOnly));
        QCOMPARE(QJsonDocument::fromJson(noteAsk.readAll()).object()["note"].toObject()["revision"].toInt(),3);
        QTRY_VERIFY(window->property("noteContext").toMap().isEmpty());
        settings.setValue("topbar/layout",originalLayout);settings.sync();QTRY_COMPARE(data.layout(),originalLayout);
        input.closeWriteChannel();QVERIFY(input.waitForFinished(1000));
    }
    void notificationPreview(){
        auto bus=QDBusConnection::sessionBus();
        qmlRegisterType<AppMenu>("Lumen.Topbar",1,0,"AppMenu");
        PanelData data;Tray tray;QQmlEngine engine;
        QVERIFY(bus.registerService("org.lumen.Topbar"));
        QVERIFY(bus.registerObject("/Topbar",&data,QDBusConnection::ExportScriptableSlots));
        engine.rootContext()->setContextProperty("panelData",&data);
        engine.rootContext()->setContextProperty("trayModel",&tray);
        QQmlComponent component(&engine,QUrl("qrc:/lumen/Topbar.qml"));
        QScopedPointer<QQuickWindow> window(qobject_cast<QQuickWindow*>(component.create()));
        QVERIFY2(window,qPrintable(component.errorString()));
        auto screen=QGuiApplication::primaryScreen();window->setScreen(screen);window->setWidth(screen->geometry().width());
        auto layer=LayerShellQt::Window::get(window.data());layer->setScreen(screen);layer->setLayer(LayerShellQt::Window::LayerTop);
        layer->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop)|LayerShellQt::Window::AnchorLeft|LayerShellQt::Window::AnchorRight);
        layer->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityOnDemand);
        window->setProperty("ready",true);QTRY_VERIFY(window->isExposed());
        auto click=[&](QQuickItem *button){if(!button || !button->isVisible())return false;
            const QPoint point=button->mapToScene(QPointF(button->width()/2,button->height()/2)).toPoint();
            QTest::mouseClick(window.data(),Qt::LeftButton,{},point);return true;};
        QFile file("/profile/preview-id");QVERIFY(file.open(QIODevice::ReadOnly));
        const QString key="lumen:"+QString::fromUtf8(file.readAll()).trimmed();
        QVERIFY(click(item("notificationsButton")));
        auto peek=window->findChild<QObject*>("quickMenu");
        QTRY_VERIFY(peek && peek->property("opened").toBool());
        QTRY_VERIFY_WITH_TIMEOUT(!data.noticePreview().isEmpty(),7000);
        QVERIFY2(!data.noticePreview().value("locked").toBool(),"Private QA screen is locked");
        QTRY_VERIFY_WITH_TIMEOUT(item("quickRow_"+key),7000);
        auto quick=window->findChild<QObject*>("quickMenu");QVERIFY(quick && quick->property("opened").toBool());
        QTRY_VERIFY(window->height()>=quick->property("y").toDouble()+quick->property("height").toDouble());
        QTest::qWait(250);QVERIFY(window->grabWindow().save("/profile/captures/native-notice-preview.png"));
        QVERIFY(click(item("quickRow_"+key)));QTRY_VERIFY(!quick->property("visible").toBool());
        // Only the selected local notice is marked read by the full center.
        auto isRead=[&]{for(const auto &entry:data.noticePreview().value("items").toList()){
            const auto row=entry.toMap();if(row["key"]==key)return !row["unread"].toBool();}return false;};
        data.watchNotices(window.data(),true);
        QTRY_VERIFY_WITH_TIMEOUT(isRead(),8000);
        QVERIFY(data.noticePreview().value("unread").toInt()>0);
        data.noticeCommand("read");
        QTRY_COMPARE_WITH_TIMEOUT(data.noticePreview().value("unread").toInt(),0,10000);
        data.watchNotices(window.data(),false);
    }

};
QTEST_MAIN(UiTest)
#include "ui_test.moc"
