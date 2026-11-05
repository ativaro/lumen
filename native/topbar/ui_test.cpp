// SPDX-License-Identifier: MIT
#include "appmenu.h"
#include "paneldata.h"
#include "tray.h"
#include <QApplication>
#include <QFont>
#include <QAbstractItemModel>
#include <QDBusInterface>
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
        const auto send=[&](const QByteArray &command){input.write(command);if(!input.waitForBytesWritten(1000) || !input.waitForReadyRead(1000))return false;return input.readAllStandardOutput().startsWith("OK");};
        qmlRegisterType<AppMenu>("Lumen.Topbar",1,0,"AppMenu");
        PanelData data;Tray tray;QQmlEngine engine;engine.rootContext()->setContextProperty("panelData",&data);
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
        const auto click=[&](QQuickItem *value){const auto point=value->mapToGlobal(QPointF(value->width()/2,value->height()/2));return send("click "+QByteArray::number(point.x())+" "+QByteArray::number(point.y())+"\n");};
        QVERIFY(click(button));QTRY_VERIFY_WITH_TIMEOUT(QApplication::activePopupWidget()!=nullptr,3000);
        auto popup=qobject_cast<QMenu*>(QApplication::activePopupWidget());QVERIFY(popup);
        QCOMPARE(popup->font().pixelSize(),QApplication::font().pixelSize());
        qInfo()<<"MENU_POSITION"<<popup->geometry()<<button->mapToGlobal(QPointF(0,button->height()));
        QVERIFY(popup->grab().save("/profile/captures/native-file-menu.png"));
        QVERIFY(send("key 108\n"));QTest::qWait(70);QVERIFY(send("key 28\n"));
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/saved-A.txt"),3000);
        QTRY_VERIFY_WITH_TIMEOUT(!menus->opened(),3000);
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
        QVERIFY(click(item("launcherButton")));QTRY_VERIFY(apps->property("opened").toBool());QTest::qWait(180);QVERIFY(click(item("programsTab")));QTRY_VERIFY(apps->property("programs").toBool());
        QTRY_VERIFY_WITH_TIMEOUT(item("programSearch"),4000);
        auto programQuery=item("programSearch");QVERIFY(programQuery->isVisible());QTest::qWait(250);QVERIFY(apps->property("opened").toBool());programQuery->setProperty("text","lumen testprogramm");
        QTRY_COMPARE_WITH_TIMEOUT(item("programList")->property("count").toInt(),1,4000);
        QVERIFY(click(programQuery));QTest::qWait(150);QVERIFY(apps->property("opened").toBool());
        QVERIFY(window->grabWindow().save("/profile/captures/native-start-menu.png"));
        QVERIFY(send("key 28\n"));QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/program-started"),4000);
        QTRY_VERIFY(!apps->property("opened").toBool());
        auto composer=item("inlineComposer");QVERIFY(composer);
        if(!composer->isVisible()){QVERIFY(click(item("askButton")));QTest::qWait(180);composer=item("popupComposer");}
        QVERIFY(composer);auto question=find(composer,"lumenQuestion");QVERIFY(question && question->isVisible());
        QCOMPARE(qvariant_cast<QFont>(question->property("font")).pixelSize(),QApplication::font().pixelSize());
        const QString questionText=QStringLiteral("Erkläre $HOME und $(echo test), ohne etwas auszuführen.");
        question->setProperty("text",questionText);QVERIFY(click(question));QTRY_VERIFY(question->hasActiveFocus());QTest::qWait(150);QVERIFY(question->hasActiveFocus());
        QVERIFY(window->grabWindow().save("/profile/captures/native-question.png"));
        QVERIFY(send("key 28\n"));QTRY_VERIFY_WITH_TIMEOUT(QFile::exists("/profile/asked.json"),3000);
        QFile asked("/profile/asked.json");QVERIFY(asked.open(QIODevice::ReadOnly));
        QCOMPARE(QJsonDocument::fromJson(asked.readAll()).object()["prompt"].toString(),questionText);
        QTRY_VERIFY(question->property("text").toString().isEmpty());
        auto dictate=item("compactDictateButton");if(!dictate->isVisible())dictate=find(item("inlineComposer"),"dictateButton");
        QVERIFY(dictate && dictate->isVisible());QVERIFY(click(dictate));QTRY_VERIFY_WITH_TIMEOUT(actions().contains("--voice"),3000);
        QVERIFY(click(item("windowOverviewButton")));
        auto activities=window->findChild<QObject*>("activityPopup");QVERIFY(activities);QTRY_VERIFY(activities->property("opened").toBool());
        QTRY_VERIFY(item("overviewWindow_0") && item("overviewWindow_0")->isVisible());QTest::qWait(150);
        QVERIFY(window->grabWindow().save("/profile/captures/native-window-overview.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!activities->property("opened").toBool());
        QVERIFY(click(item("recentContentButton")));QTRY_VERIFY(activities->property("opened").toBool());
        QTRY_VERIFY(item("recentContent_0") && item("recentContent_0")->isVisible());
        QVERIFY(!data.controlBusy());QVERIFY(click(item("recentContent_0")));QTRY_VERIFY(actions().contains("/profile/example.txt"));
        QVERIFY(window->grabWindow().save("/profile/captures/native-recent-content.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!activities->property("opened").toBool());
        QVERIFY(click(item(data.layout()=="classic"?"activityButton":"activityCompactButton")));QTRY_VERIFY(activities->property("opened").toBool());
        QTRY_VERIFY(item("reviewDecision_0") && item("reviewDecision_0")->isVisible());QTRY_VERIFY(!data.controlBusy());
        QVERIFY(click(item("reviewDecision_0")));QTRY_VERIFY(actions().contains(QByteArray(32,'b')));
        QFile resolved("/profile/decision-resolved");QVERIFY(resolved.open(QIODevice::WriteOnly));resolved.close();
        QTRY_VERIFY(!data.controlBusy());data.refresh();QTRY_VERIFY(data.snapshot()["activity"].toMap()["decisions"].toList().isEmpty());
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
        QDBusInterface trayControl("org.lumen.TrayTest","/Control",QString());QVERIFY(trayControl.call("quit").type()!=QDBusMessage::ErrorMessage);
        QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),0,3000);
        QDBusInterface fixture("org.lumen.MenuTestA","/Control",QString());QVERIFY(fixture.call("command","fullscreen").type()!=QDBusMessage::ErrorMessage);
        QTRY_VERIFY_WITH_TIMEOUT(!window->isVisible(),3000);
        QVERIFY(fixture.call("command","normal").type()!=QDBusMessage::ErrorMessage);QTRY_VERIFY_WITH_TIMEOUT(window->isVisible(),3000);
        data.ShowApps();QTRY_VERIFY(apps->property("opened").toBool());QTRY_VERIFY(window->isActive());
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!apps->property("opened").toBool());
        auto controls=item("systemControlsButton");QVERIFY(controls);if(!controls->isVisible()){QVERIFY(click(item("compactControlsButton")));QTest::qWait(180);controls=item("audioMenuEntry");}QVERIFY(controls->isVisible());QVERIFY(click(controls));QTest::qWait(180);
        auto audioPopup=window->findChild<QObject*>("audioPopup");auto networkPopup=window->findChild<QObject*>("networkPopup");QVERIFY(audioPopup && networkPopup);
        QTRY_VERIFY(audioPopup->property("opened").toBool());QVERIFY(!networkPopup->property("opened").toBool());
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
        auto networkControl=item("networkButton");QVERIFY(networkControl);
        if(!networkControl->isVisible()){QVERIFY(click(item("compactControlsButton")));QTest::qWait(100);networkControl=item("networkMenuEntry");}
        QVERIFY(click(networkControl));QTRY_VERIFY(networkPopup->property("opened").toBool());QVERIFY(!audioPopup->property("opened").toBool());
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
        auto generalControls=window->findChild<QObject*>("systemPopup");QVERIFY(generalControls);QTRY_VERIFY(generalControls->property("opened").toBool());
        QVERIFY(!audioPopup->property("opened").toBool());QVERIFY(!networkPopup->property("opened").toBool());
        QVERIFY(window->grabWindow().save("/profile/captures/native-general-controls.png"));
        QVERIFY(send("key 1\n"));QTRY_VERIFY(!generalControls->property("opened").toBool());
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
};
QTEST_MAIN(UiTest)
#include "ui_test.moc"
