#include "backup_wizard.h"
#include "backups.h"
#include "vault.h"
#include <QScopeGuard>
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
  void recoveryKeyCannotFollowAliasesIntoRepository() {
    QTemporaryDir root;
    const auto repository = root.path() + "/backup";
    QVERIFY(QDir().mkdir(repository));
    QFile target(repository + "/key.txt");
    QVERIFY(target.open(QIODevice::WriteOnly));
    target.close();
    QVERIFY(QFile::link(repository, root.path() + "/folder-alias"));
    QVERIFY(QFile::link(target.fileName(), root.path() + "/file-alias"));
    QVERIFY(!backupKeyDestinationAllowed(root.path() + "/folder-alias/key.txt",
                                         repository));
    QVERIFY(
        !backupKeyDestinationAllowed(root.path() + "/file-alias", repository));
    QVERIFY(backupKeyDestinationAllowed(root.path() + "/independent.txt",
                                        repository));
  }
  void guidedBackupCompletesOnlyAfterProbe() {
    QTemporaryDir root;
    VaultWindow parent(root.path());
    QStringList operations;
    QJsonObject prepared;
    std::function<void(QJsonValue)> finish;
    std::function<void(QString)> fail;
    BackupWizard wizard(
        false,
        [&](QJsonObject args, auto done, auto failed) {
          fail = failed;
          operations << args["op"].toString();
          if (args["op"] == "setup_inventory")
            done(QJsonObject{
                {"files",
                 QJsonArray{QJsonObject{{"label", "Dokumente"},
                                        {"path", "/home/example/Documents"}}}},
                {"lumen",
                 QJsonArray{QJsonObject{{"label", "Wissen"},
                                        {"path", "/home/example/Wissen"}}}},
                {"vault",
                 QJsonArray{QJsonObject{{"label", "Passwort-Tresor"},
                                        {"path", "/home/example/Vault"}}}}});
          else if (args["op"] == "test_target")
            done(QJsonObject{{"path", "/media/Backup"},
                             {"tested", true},
                             {"free", 1024.0 * 1024 * 1024 * 500}});
          else if (args["op"] == "configure") {
            prepared = args;
            done(QJsonObject{{"id", "synthetic-plan"}});
          } else if (args["op"] == "finish_setup")
            finish = done;
        },
        &parent);
    wizard.show();
    QTest::qWait(30);
    QCOMPARE(wizard.pageIds().size(), 4);
    auto capture = [&](const QString &name) {
      const auto dir = qEnvironmentVariable("LUMEN_TEST_BACKUP_SCREENSHOTS");
      if (!dir.isEmpty()) {
        QDir().mkpath(dir);
        QVERIFY(wizard.grab().save(dir + '/' + name + ".png"));
      }
    };
    capture("sources");
    wizard.next();
    QCOMPARE(wizard.currentId(), 1);
    wizard.findChild<QLineEdit *>("backupDestination")
        ->setText("/media/Backup");
    wizard.next();
    QCOMPARE(wizard.currentId(), 2);
    auto *key = wizard.findChild<QLineEdit *>("backupRecoveryKey");
    QCOMPARE(key->echoMode(), QLineEdit::Password);
    QCOMPARE(key->text().size(), 64);
    for (auto *check : wizard.findChildren<QCheckBox *>())
      if (check->text().contains("unabhängig"))
        check->setChecked(true);
    capture("protection");
    wizard.next();
    QCOMPARE(wizard.currentId(), 3);
    capture("review");
    QTest::mouseClick(wizard.button(QWizard::FinishButton), Qt::LeftButton);
    QCOMPARE(prepared["groups"].toObject()["vault"].toArray().size(), 1);
    QVERIFY(prepared["recovery_confirmed"].toBool());
    QVERIFY(finish);
    QVERIFY(!wizard.button(QWizard::FinishButton)->isEnabled());
    QVERIFY(!wizard.button(QWizard::BackButton)->isEnabled());
    QTimer::singleShot(0, [] {
      if (auto *box =
              qobject_cast<QMessageBox *>(QApplication::activeModalWidget()))
        box->accept();
    });
    fail("Synthetic offline failure");
    QVERIFY(!wizard.button(QWizard::BackButton)->isEnabled());
    QVERIFY(wizard.button(QWizard::FinishButton)->isEnabled());
    QTest::mouseClick(wizard.button(QWizard::FinishButton), Qt::LeftButton);
    finish(QJsonObject{{"verified", true}});
    QVERIFY(wizard.isVisible());
    QVERIFY(!wizard.button(QWizard::BackButton)->isEnabled());
    QVERIFY(key->text().isEmpty());
    QTest::mouseClick(wizard.button(QWizard::FinishButton), Qt::LeftButton);
    QCOMPARE(wizard.result(), int(QDialog::Accepted));
    QCOMPARE(operations.count("configure"), 1);
    QCOMPARE(operations.count("finish_setup"), 2);
  }
  void backupsTabsKeepOneWindowAndSelection() {
    QTemporaryDir root;
    const auto oldRuntime = qgetenv("XDG_RUNTIME_DIR");
    const auto oldTools = qgetenv("LUMEN_TOOLS_DATA");
    auto restore = qScopeGuard([=] {
      qputenv("XDG_RUNTIME_DIR", oldRuntime);
      qputenv("LUMEN_TOOLS_DATA", oldTools);
    });
    qputenv("XDG_RUNTIME_DIR", root.path().toUtf8());
    qputenv("LUMEN_TOOLS_DATA", root.path().toUtf8());
    const auto endpoint = root.path() + "/lumen-backups-" +
                          QCryptographicHash::hash(root.path().toUtf8(),
                                                   QCryptographicHash::Sha256)
                              .toHex()
                              .left(16);
    QLocalServer service;
    QVERIFY(service.listen(endpoint));
    int requests = 0;
    connect(&service, &QLocalServer::newConnection, &service, [&] {
      auto *peer = service.nextPendingConnection();
      connect(peer, &QLocalSocket::readyRead, &service, [&, peer] {
        if (!peer->canReadLine())
          return;
        const auto request = QJsonDocument::fromJson(peer->readLine()).object();
        ++requests;
        QJsonObject reply{{"state", "idle"}};
        if (request["command"] == "start")
          reply = {{"state", "done"},
                   {"op", "list"},
                   {"result",
                    QJsonArray{QJsonObject{
                        {"id", "synthetic"},
                        {"title", "Meine Sicherung"},
                        {"repository", "/media/Backup"},
                        {"sources", QJsonArray{"/home/example/Documents"}}}}}};
        peer->write(QJsonDocument(reply).toJson(QJsonDocument::Compact) + '\n');
        peer->disconnectFromServer();
      });
      connect(peer, &QLocalSocket::disconnected, peer, &QObject::deleteLater);
    });
    QTemporaryDir store;
    VaultWindow window(store.path());
    window.show();
    const auto wid = window.winId();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC UNSENT");
    auto *tabs = window.findChild<QTabBar *>("vaultSections");
    QTest::qWait(10);
    const auto tabPosition = tabs->mapTo(&window, QPoint());
    const auto windowSize = window.size();
    if (qEnvironmentVariableIsSet("LUMEN_VAULT_CAPTURE"))
      window.grab().save("/tmp/lumen-vault-tabs-locked.png");
    QTest::mouseClick(tabs, Qt::LeftButton, Qt::NoModifier,
                      tabs->tabRect(1).center());
    auto *page = window.findChild<BackupPage *>();
    QVERIFY(page);
    QTRY_COMPARE(page->findChild<QListWidget *>("backupPlans")->count(), 1);
    auto *plans = page->findChild<QListWidget *>("backupPlans");
    plans->setCurrentRow(0);
    const auto count = requests;
    for (int i = 0; i < 3; ++i) {
      QCOMPARE(window.findChildren<QTabBar *>("vaultSections").size(), 1);
      QCOMPARE(tabs->mapTo(&window, QPoint()), tabPosition);
      QCOMPARE(window.size(), windowSize);
      QTest::mouseClick(tabs, Qt::LeftButton, Qt::NoModifier,
                        tabs->tabRect(0).center());
      QCOMPARE(window.section(), 0);
      QCOMPARE(master->text(), QString("SYNTHETIC UNSENT"));
      QTest::mouseClick(tabs, Qt::LeftButton, Qt::NoModifier,
                        tabs->tabRect(1).center());
      QCOMPARE(window.section(), 1);
      QCOMPARE(window.winId(), wid);
      QCOMPARE(plans->currentRow(), 0);
      QCOMPARE(requests, count);
      QCOMPARE(page->window(), static_cast<QWidget *>(&window));
    }
    if (qEnvironmentVariableIsSet("LUMEN_VAULT_CAPTURE")) {
      QTest::qWait(100);
      window.grab().save("/tmp/lumen-vault-tabs.png");
    }
    window.showSection(0);
    window.findChild<QLineEdit *>("confirm")->setText(master->text());
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    auto *lockButton = window.findChild<QPushButton *>("lock");
    QVERIFY(lockButton->isEnabled());
    for (const auto size : {QSize(1510, 926), QSize(1080, 720)}) {
      window.resize(size);
      QTest::qWait(10);
      const auto position = tabs->mapTo(&window, QPoint());
      const auto lockPosition = lockButton->mapTo(&window, QPoint());
      const auto headerSize = window.findChild<QFrame *>("vaultHeader")->size();
      QCOMPARE(window.size(), size);
      for (auto *label : lockButton->findChildren<QLabel *>())
        QVERIFY(label->width() >= label->fontMetrics().horizontalAdvance(label->text()));
      for (int index : {1, 0, 1, 0}) {
        QTest::mouseClick(tabs, Qt::LeftButton, Qt::NoModifier,
                          tabs->tabRect(index).center());
        QTest::qWait(10);
        QCOMPARE(window.section(), index);
        QCOMPARE(tabs->mapTo(&window, QPoint()), position);
        QCOMPARE(lockButton->mapTo(&window, QPoint()), lockPosition);
        QCOMPARE(window.findChild<QFrame *>("vaultHeader")->size(), headerSize);
        QCOMPARE(window.size(), size);
        QVERIFY(lockButton->isVisible());
        QVERIFY(window.unlocked());
        if (qEnvironmentVariableIsSet("LUMEN_VAULT_CAPTURE"))
          window.grab().save(QString("/tmp/lumen-vault-switch-%1-%2.png").arg(size.width()).arg(index));
      }
    }
    window.showSection(1);
    window.lock();
    QVERIFY(!lockButton->isEnabled());
    QCOMPARE(window.section(), 1);
    QCOMPARE(page, window.findChild<BackupPage *>());
  }
  void backupReconnectKeepsFailureVisible() {
    QTemporaryDir root;
    const auto oldRuntime = qgetenv("XDG_RUNTIME_DIR");
    const auto oldTools = qgetenv("LUMEN_TOOLS_DATA");
    auto restore = qScopeGuard([=] {
      qputenv("XDG_RUNTIME_DIR", oldRuntime);
      qputenv("LUMEN_TOOLS_DATA", oldTools);
    });
    qputenv("XDG_RUNTIME_DIR", root.path().toUtf8());
    qputenv("LUMEN_TOOLS_DATA", root.path().toUtf8());
    const auto endpoint = root.path() + "/lumen-backups-" +
                          QCryptographicHash::hash(root.path().toUtf8(),
                                                   QCryptographicHash::Sha256)
                              .toHex()
                              .left(16);
    QLocalServer service;
    QVERIFY(service.listen(endpoint));
    connect(&service, &QLocalServer::newConnection, &service, [&] {
      auto *peer = service.nextPendingConnection();
      connect(peer, &QLocalSocket::readyRead, &service, [peer] {
        if (!peer->canReadLine())
          return;
        const auto request = QJsonDocument::fromJson(peer->readLine()).object();
        QJsonObject reply =
            request["command"] == "status"
                ? QJsonObject{{"state", "error"},
                              {"op", "backup"},
                              {"error", "SYNTHETIC missing disk"}}
                : QJsonObject{{"state", "done"},
                              {"op", "list"},
                              {"result", QJsonArray{}}};
        peer->write(QJsonDocument(reply).toJson(QJsonDocument::Compact) + '\n');
        peer->disconnectFromServer();
      });
      connect(peer, &QLocalSocket::disconnected, peer, &QObject::deleteLater);
    });
    BackupPage page(false);
    page.show();
    page.activate();
    QTRY_COMPARE(page.findChild<QLabel *>("backupStatus")->text(),
                 QString("SYNTHETIC missing disk"));
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
  void collectionsAndDetailLayout() {
    QTemporaryDir root;
    Channel seed(root.path());
    bool ready = false;
    seed.call({"create", "SYNTHETIC DESIGN MASTER"},
              [&](QStringList) { ready = true; });
    QTRY_VERIFY_WITH_TIMEOUT(ready, 10000);
    const QList<QStringList> samples{
        {"Mailkonto", "Privat", "login", "https://mail.example",
         "alex@example.test"},
        {"Git-Server", "Arbeit", "login", "https://git.example", "alex"},
        {"NAS", "Server", "login", "https://nas.example", "alex"},
        {"Cloud API", "Arbeit", "token", "https://cloud.example", ""},
        {"Sichere Notiz", "Privat", "note", "", ""}};
    for (const auto &sample : samples) {
      ready = false;
      seed.call({"put", "", "Title", sample[0], "LumenCollection", sample[1],
                 "LumenType", sample[2], "URL", sample[3], "UserName",
                 sample[4], "Password", "SYNTHETIC ONLY"},
                [&](QStringList) { ready = true; });
      QTRY_VERIFY_WITH_TIMEOUT(ready, 10000);
    }
    seed.stop();
    VaultWindow window(root.path());
    window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC DESIGN MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    auto *entries = window.findChild<QListWidget *>("entries");
    auto *navigation = window.findChild<QListWidget *>("navigation");
    QTRY_COMPARE(entries->count(), 5);
    int privateRow = -1;
    for (int i = 0; i < navigation->count(); ++i)
      if (navigation->item(i)->data(Qt::UserRole).toString() ==
          "collection:Privat")
        privateRow = i;
    QVERIFY(privateRow >= 0);
    navigation->setCurrentRow(privateRow);
    QCOMPARE(entries->count(), 2);
    for (int i = 0; i < entries->count(); ++i)
      if (entries->item(i)->data(Qt::UserRole + 1).toString() == "Mailkonto")
        entries->setCurrentRow(i);
    QTRY_COMPARE(window.findChild<QLineEdit *>("website")->text(),
                 QString("https://mail.example"));
    QCOMPARE(window.findChild<QLineEdit *>("secret")->echoMode(),
             QLineEdit::Password);
    navigation->setCurrentRow(0);
    QCOMPARE(entries->count(), 5);
    for (int i = 0; i < entries->count(); ++i)
      if (entries->item(i)->data(Qt::UserRole + 1).toString() == "Mailkonto")
        entries->setCurrentRow(i);
    QTRY_COMPARE(window.findChild<QLineEdit *>("website")->text(),
                 QString("https://mail.example"));
    if (qEnvironmentVariableIsSet("LUMEN_VAULT_CAPTURE")) {
      for (const auto &theme :
           QStringList{"glass", "graphite", "atelier", "midnight"}) {
        QSettings settings("Lumen", "Assistant");
        settings.setValue("appearance", theme);
        settings.sync();
        QTest::qWait(2100);
        window.grab().save("/tmp/lumen-vault-design-" + theme + ".png");
      }
      window.resize(1080, 720);
      QTest::qWait(100);
      window.grab().save("/tmp/lumen-vault-design-compact.png");
    }
    window.lock();
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
    QTRY_VERIFY(!window.findChild<Channel *>()->busy());
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
