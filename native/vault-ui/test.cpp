#include "vault.h"
#include <QtTest>
class VaultTest : public QObject {
  Q_OBJECT
  QTemporaryDir config;
private slots:
  void initTestCase() {
    QSettings::setPath(QSettings::NativeFormat, QSettings::UserScope,
                       config.path());
    QSettings settings("Lumen", "Assistant");
    settings.setValue("uiLanguage", "de");
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
    QTest::mouseClick(window.findChild<QPushButton *>("save"), Qt::LeftButton);
    QTRY_COMPARE_WITH_TIMEOUT(
        window.findChild<QListWidget *>("entries")->count(), 1, 10000);
    QTest::mouseClick(window.findChild<QPushButton *>("copy"), Qt::LeftButton);
    QTRY_COMPARE(QApplication::clipboard()->text(),
                 QString("SYNTHETIC SECRET"));
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
    window.suspend(true);
    QVERIFY(!window.unlocked());
    QVERIFY(!window.findChild<QListWidget *>("entries"));
    QCOMPARE(QApplication::clipboard()->text(), QString());
    master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC TEST MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_COMPARE(window.findChild<QListWidget *>("entries")->count(), 1);
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
