#include "vault.h"
#include <QtTest>
class VaultTest : public QObject {
  Q_OBJECT
  QTemporaryDir config;
  static QStringList history() {
    QDBusInterface k("org.kde.klipper", "/klipper", "org.kde.klipper.klipper");
    QDBusPendingCallWatcher watcher(k.asyncCall("getClipboardHistoryMenu"));
    QEventLoop loop;
    QObject::connect(&watcher, &QDBusPendingCallWatcher::finished, &loop,
                     &QEventLoop::quit);
    QTimer::singleShot(5000, &loop, &QEventLoop::quit);
    if (!watcher.isFinished())
      loop.exec();
    QDBusPendingReply<QStringList> reply = watcher;
    if (reply.isError())
      qWarning() << "Private test Klipper:" << reply.error().name();
    return reply.isFinished() && !reply.isError() ? reply.value()
                                                  : QStringList{};
  }
private slots:
  void initTestCase() {
    QSettings::setPath(QSettings::NativeFormat, QSettings::UserScope,
                       config.path());
    QSettings settings("Lumen", "Assistant");
    settings.setValue("uiLanguage", "de");
  }
  void queuedRequestsAreNotDropped() {
    QTemporaryDir root;
    Channel channel(root.path());
    bool created = false, listed = false;
    QSignalSpy failures(&channel, &Channel::failed);
    channel.call({"create", "SYNTHETIC QUEUE MASTER"},
                 [&](QStringList) { created = true; });
    channel.call({"page", "0"}, [&](QStringList fields) {
      listed = fields == QStringList{QString()};
    });
    QTRY_VERIFY_WITH_TIMEOUT(created && listed, 10000);
    QCOMPARE(failures.count(), 0);
    channel.stop();
  }
  void clipboardOwnershipAndLock() {
    QTemporaryDir root;
    VaultWindow window(root.path());
    window.show();
    window.copySecret("SYNTHETIC CLIPBOARD");
    QCOMPARE(QApplication::clipboard()->mimeData()->data(
                 "x-kde-passwordManagerHint"),
             QByteArray("secret"));
    window.clearOwnClipboard();
    QCOMPARE(QApplication::clipboard()->text(), QString());
    window.copySecret("SYNTHETIC CLIPBOARD");
    QApplication::clipboard()->setText("someone else");
    window.clearOwnClipboard();
    QCOMPARE(QApplication::clipboard()->text(), QString("someone else"));
    window.screenLock(true);
    QVERIFY(!window.unlocked());
    QVERIFY(!window.findChild<QListWidget *>("entries"));
  }
  void createSaveLockReopen() {
    QTemporaryDir root;
    VaultWindow window(root.path());
    window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC TEST MASTER");
    window.findChild<QLineEdit *>("confirm")->setText("SYNTHETIC TEST MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_VERIFY(window.findChild<QPushButton *>("new"));
    QTest::mouseClick(window.findChild<QPushButton *>("new"), Qt::LeftButton);
    QTRY_VERIFY(window.findChild<QLineEdit *>("editTitle"));
    window.findChild<QLineEdit *>("editTitle")->setText("SYNTHETIC TITLE");
    window.findChild<QLineEdit *>("editPassword")->setText("SYNTHETIC SECRET");
    auto *notes = window.findChild<QPlainTextEdit *>("editNotes");
    notes->setPlainText("SYNTHETIC NOTE");
    notes->setFocus();
    QTest::keyClick(notes, Qt::Key_A, Qt::ControlModifier);
    QTest::keyClick(notes, Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->text(), QString("SYNTHETIC NOTE"));
    QCOMPARE(QApplication::clipboard()->mimeData()->data(
                 "x-kde-passwordManagerHint"),
             QByteArray("secret"));
    if (QApplication::clipboard()->supportsSelection()) {
      QTest::qWait(50);
      QVERIFY(!QApplication::clipboard()
                   ->text(QClipboard::Selection)
                   .contains("SYNTHETIC NOTE"));
      QTest::mouseDClick(notes->viewport(), Qt::LeftButton, Qt::NoModifier,
                         QPoint(25, 15));
      QTest::qWait(50);
      QVERIFY(!QApplication::clipboard()
                   ->text(QClipboard::Selection)
                   .contains("SYNTHETIC"));
    }
    QMimeData *large = new QMimeData;
    large->setText(QString(17000, 'x'));
    QApplication::clipboard()->setMimeData(large);
    notes->selectAll();
    notes->paste();
    QCOMPARE(notes->toPlainText(), QString("SYNTHETIC NOTE"));
    QInputMethodEvent ime;
    ime.setCommitString(QString(17000, 'x'));
    QApplication::sendEvent(notes, &ime);
    QCOMPARE(notes->toPlainText(), QString("SYNTHETIC NOTE"));
    QTest::mouseClick(window.findChild<QPushButton *>("save"), Qt::LeftButton);
    QTRY_COMPARE_WITH_TIMEOUT(
        window.findChild<QListWidget *>("entries")->count(), 1, 10000);
    if (qEnvironmentVariableIsSet("LUMEN_PRIVATE_KDE_TEST")) {
      window.activateWindow();
      window.raise();
      QTRY_VERIFY_WITH_TIMEOUT(window.isActiveWindow(), 5000);
      QApplication::clipboard()->setText("PUBLIC CONTROL");
      auto recorded = [] {
        return history().join(" ").contains("PUBLIC CONTROL");
      };
      QTRY_VERIFY_WITH_TIMEOUT(recorded(), 5000);
    }
    QTest::mouseClick(window.findChild<QPushButton *>("copy"), Qt::LeftButton);
    QTRY_COMPARE(QApplication::clipboard()->text(),
                 QString("SYNTHETIC SECRET"));
    if (qEnvironmentVariableIsSet("LUMEN_PRIVATE_KDE_TEST")) {
      QDBusInterface klipper("org.kde.klipper", "/klipper",
                             "org.kde.klipper.klipper",
                             QDBusConnection::sessionBus());
      QVERIFY2(klipper.isValid(),
               "Klipper must run in the private KDE test session");
      const auto values = history();
      QVERIFY(values.join(" ").contains("PUBLIC CONTROL"));
      QVERIFY(!values.join(" ").contains("SYNTHETIC"));
    }
    if (qEnvironmentVariableIsSet("LUMEN_VAULT_CAPTURE")) {
      for (const auto &theme :
           QStringList{"glass", "graphite", "atelier", "midnight"}) {
        QSettings settings("Lumen", "Assistant");
        settings.setValue("appearance", theme);
        settings.sync();
        QTest::qWait(2100);
        window.grab().save("/tmp/lumen-vault-native-" + theme + ".png");
      }
    }
    if (qEnvironmentVariableIsSet("LUMEN_PRIVATE_KDE_TEST")) {
      auto bus = QDBusConnection::sessionBus();
      QVERIFY(bus.registerService("org.freedesktop.ScreenSaver"));
      auto signal = QDBusMessage::createSignal(
          "/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged");
      signal << true;
      QVERIFY(bus.send(signal));
      QTRY_VERIFY(!window.unlocked());
    } else
      window.suspend(true);
    QVERIFY(!window.unlocked());
    QVERIFY(!window.findChild<QListWidget *>("entries"));
    if (qEnvironmentVariableIsSet("LUMEN_PRIVATE_KDE_TEST"))
      QVERIFY(!QApplication::clipboard()->text().contains(
          "SYNTHETIC")); // Klipper may restore the previous public item.
    else
      QCOMPARE(QApplication::clipboard()->text(), QString());
    master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC TEST MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_COMPARE(window.findChild<QListWidget *>("entries")->count(), 1);
    if (qEnvironmentVariableIsSet("LUMEN_PRIVATE_KDE_TEST")) {
      auto bus = QDBusConnection::systemBus();
      QVERIFY(bus.registerService("org.freedesktop.login1"));
      auto signal = QDBusMessage::createSignal("/org/freedesktop/login1",
                                               "org.freedesktop.login1.Manager",
                                               "PrepareForSleep");
      signal << true;
      QVERIFY(bus.send(signal));
      QTRY_VERIFY(!window.unlocked());
    } else
      window.lock();
    for (const auto &file : QDir(root.path()).entryList(QDir::Files)) {
      QFile f(root.path() + "/" + file);
      QVERIFY(f.open(QIODevice::ReadOnly));
      QVERIFY(!f.readAll().contains("SYNTHETIC"));
    }
  }
};
QTEST_MAIN(VaultTest)
#include "test.moc"
