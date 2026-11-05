// SPDX-License-Identifier: MIT
#include "paneldata.h"
#include <QElapsedTimer>
#include <QApplication>
#include <QPalette>
#include <QFile>
#include <QTemporaryDir>
#include <QTest>
#include <QSettings>
#include <QSignalSpy>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDBusConnection>
#include <QDBusMessage>

class TestPlayer:public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface","org.mpris.MediaPlayer2.Player")
    Q_PROPERTY(QString PlaybackStatus READ status)
    Q_PROPERTY(QVariantMap Metadata READ metadata)
    Q_PROPERTY(bool CanControl READ yes)
    Q_PROPERTY(bool CanPlay READ yes)
    Q_PROPERTY(bool CanPause READ yes)
    Q_PROPERTY(bool CanGoNext READ no)
    Q_PROPERTY(bool CanGoPrevious READ yes)
public:
    bool playing=false,malformed=false;int calls=0;
    QString status() const{return playing?"Playing":"Paused";}
    QVariantMap metadata() const{return {{"xesam:title","Test track"},{"xesam:artist",malformed?QVariant(QVariantList{"invalid artist array"}):QVariant(QStringList{"Test artist"})}};}
    bool yes() const{return true;}bool no() const{return false;}
public slots:
    void PlayPause(){playing=!playing;++calls;}
    void Next(){++calls;}
    void Previous(){++calls;}
};

class DataTest:public QObject {
    Q_OBJECT
    QTemporaryDir settingsDirectory;
private slots:
    void initTestCase(){QVERIFY(settingsDirectory.isValid());QSettings::setPath(QSettings::NativeFormat,QSettings::UserScope,settingsDirectory.path());qputenv("LUMEN_DATA",settingsDirectory.filePath("state").toUtf8());}
    void mediaUsesLivePlayersAndTheirCapabilities(){
        auto bus=QDBusConnection::sessionBus();TestPlayer player;
        const QString service="org.mpris.MediaPlayer2.lumenTest";
        QVERIFY(bus.registerService(service));
        QVERIFY(bus.registerObject("/org/mpris/MediaPlayer2",&player,QDBusConnection::ExportAllSlots|QDBusConnection::ExportAllProperties));
        PanelData data;QTRY_COMPARE_WITH_TIMEOUT(data.players().size(),1,2000);
        QCOMPARE(data.players()[0].toMap()["title"].toString(),QString("Test track"));
        QCOMPARE(data.players()[0].toMap()["artist"].toString(),QString("Test artist"));
        player.malformed=true;data.refreshMedia();QTRY_VERIFY_WITH_TIMEOUT(data.players()[0].toMap()["artist"].toString().isEmpty(),1000);
        data.mediaAction(service,"Next");data.mediaAction("org.mpris.MediaPlayer2.unknown","PlayPause");QTest::qWait(30);QCOMPARE(player.calls,0);
        data.mediaAction(service,"PlayPause");QTRY_COMPARE(player.calls,1);QTRY_VERIFY(data.players()[0].toMap()["playing"].toBool());
        player.playing=false;
        auto signal=QDBusMessage::createSignal("/org/mpris/MediaPlayer2","org.freedesktop.DBus.Properties","PropertiesChanged");
        signal.setArguments({"org.mpris.MediaPlayer2.Player",QVariantMap{{"PlaybackStatus","Paused"}},QStringList{}});QVERIFY(bus.send(signal));
        QTRY_VERIFY_WITH_TIMEOUT(!data.players()[0].toMap()["playing"].toBool(),1000);
        bus.unregisterObject("/org/mpris/MediaPlayer2");bus.unregisterService(service);QTRY_VERIFY_WITH_TIMEOUT(data.players().isEmpty(),1000);
    }
    void layoutsFollowAtomicSettingsWrites(){
        QFile helper(settingsDirectory.filePath("lumen-panel"));QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/bin/sh\nprintf '%s' '{\"version\":1,\"apps\":[],\"palette\":null}'\n");helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        const auto previous=qgetenv("LUMEN_BIN_DIR");qputenv("LUMEN_BIN_DIR",settingsDirectory.path().toUtf8());
        QSettings settings("Lumen","Assistant");settings.clear();settings.sync();
        PanelData data;QCOMPARE(data.layout(),QString("classic"));
        for(const auto &layout:{"band","deck","context","classic","invalid"}){
            settings.setValue("topbar/layout",layout);settings.sync();
            QTRY_COMPARE_WITH_TIMEOUT(data.layout(),QString(layout==QString("invalid")?"classic":layout),1000);
        }
        settings.clear();settings.sync();
        QSignalSpy failed(&data,&PanelData::controlFailed);
        const auto first=data.ask(" ");const auto second=data.ask("Frage",{{"invalid",QString(17000,'x')}});
        QVERIFY(first!=second);QVERIFY(failed.isEmpty());
        QTRY_COMPARE(failed.size(),2);
        QCOMPARE(failed[0][0].toString(),first);QCOMPARE(failed[1][0].toString(),second);
        if(previous.isNull())qunsetenv("LUMEN_BIN_DIR");else qputenv("LUMEN_BIN_DIR",previous);
    }
    void systemThemeClearsTheExplicitLumenPalette(){
        QTemporaryDir directory;QVERIFY(directory.isValid());
        QFile helper(directory.filePath("lumen-panel"));QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/bin/sh\nprintf '%s' '{\"version\":1,\"apps\":[],\"palette\":null,\"language\":\"en\"}'\n");helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        const auto previous=qgetenv("LUMEN_BIN_DIR");qputenv("LUMEN_BIN_DIR",directory.path().toUtf8());
        const auto original=QApplication::palette();auto explicitColors=original;explicitColors.setColor(QPalette::Window,Qt::red);QApplication::setPalette(explicitColors);
        PanelData data;QTRY_COMPARE(data.snapshot()["language"].toString(),QString("en"));
        QVERIFY(QApplication::palette().color(QPalette::Window)!=Qt::red);
        QCOMPARE(data.snapshot()["palette"].toMap()["window"].toString(),QApplication::palette().color(QPalette::Window).name());
        QApplication::setPalette(original);
        if(previous.isNull())qunsetenv("LUMEN_BIN_DIR");else qputenv("LUMEN_BIN_DIR",previous);
    }
    void stopDuringOutstandingRead(){
        QTemporaryDir directory;QVERIFY(directory.isValid());
        QFile helper(directory.filePath("lumen-panel"));QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/bin/sh\nexec sleep 30\n");helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        const auto previous=qgetenv("LUMEN_BIN_DIR");qputenv("LUMEN_BIN_DIR",directory.path().toUtf8());
        auto data=new PanelData;data->refresh();QTest::qWait(100);
        QTest::failOnWarning(QRegularExpression(".*QProcess.*Destroyed.*"));
        QElapsedTimer elapsed;elapsed.start();delete data;
        QVERIFY(elapsed.elapsed()<1500);
        auto controlling=new PanelData;controlling->control("volume",50);QTest::qWait(100);
        QVERIFY(controlling->controlBusy());elapsed.restart();delete controlling;QVERIFY(elapsed.elapsed()<1500);
        if(previous.isNull())qunsetenv("LUMEN_BIN_DIR");else qputenv("LUMEN_BIN_DIR",previous);
    }
    void systemTopicsKeepTheirOwnDataAndRejectWrongReplies(){
        QTemporaryDir directory;QVERIFY(directory.isValid());
        QFile helper(directory.filePath("lumen-panel"));QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/bin/sh\ncase \"$*\" in\n"
            "'--system-topic network') printf '%s' '{\"topic\":\"network\",\"details\":{\"available\":true},\"error\":\"\"}';;\n"
            "'--system-topic audio --system-action') cat > \"$(dirname \"$0\")/action.json\"; printf '%s' '{\"topic\":\"audio\",\"details\":{\"available\":true},\"error\":\"\"}';;\n"
            "'--system-topic audio') printf '%s' '{\"topic\":\"network\",\"details\":{},\"error\":\"\"}';;\n"
            "*) printf '%s' '{\"version\":1,\"apps\":[],\"palette\":null}';;\nesac\n");helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        const auto previous=qgetenv("LUMEN_BIN_DIR");qputenv("LUMEN_BIN_DIR",directory.path().toUtf8());
        PanelData data;data.inspect("network");QTRY_VERIFY(data.details()["network"].toMap()["available"].toBool());
        QTRY_VERIFY(!data.controlBusy());
        data.systemAction("audio","volume:input","9",42);
        QTRY_VERIFY(data.details()["audio"].toMap()["available"].toBool());
        QVERIFY(data.details()["network"].toMap()["available"].toBool());
        QFile request(directory.filePath("action.json"));QVERIFY(request.open(QIODevice::ReadOnly));
        const auto json=QJsonDocument::fromJson(request.readAll()).object();
        QCOMPARE(json["action"].toString(),QString("volume:input"));QCOMPARE(json["target"].toString(),QString("9"));QCOMPARE(json["value"].toInt(),42);
        QSignalSpy failed(&data,&PanelData::controlFailed);QTRY_VERIFY(!data.controlBusy());data.inspect("audio");
        QTRY_COMPARE(failed.size(),1);QVERIFY(data.details()["audio"].toMap()["available"].toBool());
        if(previous.isNull())qunsetenv("LUMEN_BIN_DIR");else qputenv("LUMEN_BIN_DIR",previous);
    }
};
QTEST_MAIN(DataTest)
#include "paneldata_test.moc"
