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

class DataTest:public QObject {
    Q_OBJECT
    QTemporaryDir settingsDirectory;
private slots:
    void initTestCase(){QVERIFY(settingsDirectory.isValid());QSettings::setPath(QSettings::NativeFormat,QSettings::UserScope,settingsDirectory.path());}
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
        const auto first=data.ask(" ");const auto second=data.ask("Frage",settingsDirectory.path());
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
};
QTEST_MAIN(DataTest)
#include "paneldata_test.moc"
