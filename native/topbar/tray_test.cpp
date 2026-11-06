// SPDX-License-Identifier: MIT
#include "tray.h"
#include <QDBusConnection>
#include <QDBusObjectPath>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTest>

class TestWatcher:public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface","org.kde.StatusNotifierWatcher")
    Q_PROPERTY(QStringList RegisteredStatusNotifierItems MEMBER registered)
public:
    QStringList registered;
    QString host;
public slots:
    void RegisterStatusNotifierHost(const QString &value){host=value;}
signals:
    void StatusNotifierItemUnregistered(const QString &identity);
};
class TestItem:public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface","org.kde.StatusNotifierItem")
    Q_PROPERTY(QString Id READ id)
    Q_PROPERTY(QString Title READ title)
    Q_PROPERTY(QString Status READ status)
    Q_PROPERTY(QString IconName READ icon)
    Q_PROPERTY(bool ItemIsMenu READ isMenu)
    Q_PROPERTY(QDBusObjectPath Menu READ menu)
public:
    int activations=0;
    QString id()const{return "synthetic-item";}
    QString title()const{return "Synthetische Trayprobe";}
    QString status()const{return "Active";}
    QString icon()const{return "application-x-executable";}
    bool isMenu()const{return false;}
    QDBusObjectPath menu()const{return QDBusObjectPath("/Menu");}
public slots:
    void Activate(int,int){++activations;}
};
class TrayTest:public QObject {
    Q_OBJECT
private slots:
    void discoverActivateAndRemove(){
        auto bus=QDBusConnection::sessionBus();TestWatcher watcher;TestItem item;
        QVERIFY(bus.registerService("org.kde.StatusNotifierWatcher"));
        QVERIFY(bus.registerObject("/StatusNotifierWatcher",&watcher,QDBusConnection::ExportAllContents));
        QVERIFY(bus.registerService("org.lumen.TestTrayItem"));
        QVERIFY(bus.registerObject("/StatusNotifierItem",&item,QDBusConnection::ExportAllContents));
        const QString identity="org.lumen.TestTrayItem/StatusNotifierItem";watcher.registered={identity};
        Tray tray;QTRY_COMPARE_WITH_TIMEOUT(tray.items().size(),1,3000);
        QCOMPARE(tray.items()[0].toMap()["title"].toString(),item.title());
        QVERIFY(watcher.host.startsWith("org.kde.StatusNotifierHost.lumen."));
        QQuickWindow window;QQuickItem anchor(window.contentItem());
        tray.activate(identity,&anchor);QTRY_COMPARE_WITH_TIMEOUT(item.activations,1,3000);
        tray.activate("invalid; command",&anchor);QTest::qWait(50);QCOMPARE(item.activations,1);
        watcher.registered.clear();emit watcher.StatusNotifierItemUnregistered(identity);
        QTRY_VERIFY_WITH_TIMEOUT(tray.items().isEmpty(),3000);
    }
};
QTEST_MAIN(TrayTest)
#include "tray_test.moc"
