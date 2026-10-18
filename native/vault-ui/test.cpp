#include "backup_wizard.h"
#include "backups.h"
#include "vault.h"
#include <QScopeGuard>
#include <QtTest>
class VaultTest : public QObject {
  Q_OBJECT
  QTemporaryDir config;
  QUrl passkeyUrl;
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
  void panoramaThemeMatchesSharedContract() {
    QTemporaryDir root;
    VaultWindow window(root.path()); window.show();
    const QList<QStringList> themes{
      {"glass", "#20343f", "#9be5d8", "#182b35"},
      {"graphite", "#222529", "#d7dce2", "#1a1c1f"},
      {"atelier", "#f2efe8", "#52634f", "#fcfaf5"},
      {"midnight", "#10151f", "#a7b6ff", "#141c29"}};
    for (const auto &theme : themes) {
      QSettings settings("Lumen", "Assistant");
      settings.setValue("appearance", theme[0]); settings.sync();
      QTRY_COMPARE_WITH_TIMEOUT(qApp->palette().color(QPalette::Window).name(), theme[1], 4000);
      QTest::qWait(50);
      QCOMPARE(qApp->palette().color(QPalette::Highlight).name(), theme[2]);
      QCOMPARE(qApp->palette().color(QPalette::Base).name(), theme[3]);
      QVERIFY(qApp->styleSheet().contains("font-size:14px"));
      for (auto *label : window.findChildren<QLabel *>())
        if (label->isVisible() && label->wordWrap() && !label->text().isEmpty()) {
          const auto textHeight = label->fontMetrics().boundingRect(
              QRect(0, 0, label->contentsRect().width(), 10000), Qt::TextWordWrap, label->text()).height();
          QVERIFY2(label->contentsRect().height() >= textHeight, qPrintable(label->text().left(40)));
        }
      if (qEnvironmentVariableIsSet("LUMEN_VAULT_PANORAMA_CAPTURE"))
        window.grab().save(qEnvironmentVariable("LUMEN_VAULT_PANORAMA_CAPTURE") + "/vault-" + theme[0] + ".png");
    }
    QSettings("Lumen", "Assistant").setValue("appearance", "glass");
  }
  void requestedUnlockIsSeparateFromUseAndCanBeCancelled() {
    QTemporaryDir root, runtime;
    VaultWindow window(root.path()); window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC REQUEST UNLOCK MASTER");
    window.findChild<QLineEdit *>("confirm")->setText(master->text());
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_VERIFY(!window.findChild<Channel *>()->busy());
    window.lock(); QVERIFY(!window.unlocked());
    QVERIFY(window.startAccessServer(runtime.path()));
    QLocalSocket socket;
    socket.connectToServer(runtime.path()+"/lumen-vault-access"); QVERIFY(socket.waitForConnected());
    socket.write("{\"operation\":\"unlock\"}\n"); socket.flush();
    QTRY_VERIFY(window.findChild<QDialog *>("vaultUnlockRequest"));
    window.findChild<QDialog *>("vaultUnlockRequest")->reject();
    QTRY_VERIFY(socket.bytesAvailable());
    QVERIFY(socket.readAll().contains("access_denied")); QVERIFY(!window.unlocked());
    socket.abort(); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    socket.connectToServer(runtime.path()+"/lumen-vault-access"); QVERIFY(socket.waitForConnected());
    socket.write("{\"operation\":\"unlock\"}\n"); socket.flush();
    QTRY_VERIFY(window.findChild<QLineEdit *>("requestMaster"));
    window.findChild<QLineEdit *>("requestMaster")->setText("WRONG SYNTHETIC PASSWORD");
    window.findChild<QPushButton *>("requestUnlock")->click();
    QTRY_VERIFY_WITH_TIMEOUT(!window.findChild<QLabel *>("requestUnlockError")->text().isEmpty(), 10000);
    QVERIFY(!window.unlocked()); QVERIFY(!socket.bytesAvailable());
    window.findChild<QLineEdit *>("requestMaster")->setText("SYNTHETIC REQUEST UNLOCK MASTER");
    window.findChild<QPushButton *>("requestUnlock")->click();
    QTRY_VERIFY_WITH_TIMEOUT(socket.bytesAvailable(), 10000);
    const auto result=QJsonDocument::fromJson(socket.readAll()).object();
    QCOMPARE(result["unlocked"].toBool(), true); QVERIFY(window.unlocked());
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    QVERIFY(!window.findChild<QDialog *>("vaultUnlockRequest"));
    // A separate credential action still sees no enabled connection in this vault.
    socket.abort(); socket.connectToServer(runtime.path()+"/lumen-vault-access"); QVERIFY(socket.waitForConnected());
    socket.write("{\"operation\":\"api_get\",\"path\":\"/status\"}\n"); socket.flush();
    QTRY_VERIFY(socket.bytesAvailable()); QVERIFY(socket.readAll().contains("open_vault_and_enable_connection"));
  }
  void capturePasskeyUrl(const QUrl &url) { passkeyUrl = url; }
  void passkeyNativeEnrollmentAndUnlock() {
    QTemporaryDir root;
    QDesktopServices::setUrlHandler("http", this, "capturePasskeyUrl");
    auto handler = qScopeGuard([] { QDesktopServices::unsetUrlHandler("http"); });
    VaultWindow window(root.path()); window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC PASSKEY UI MASTER");
    window.findChild<QLineEdit *>("confirm")->setText(master->text());
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_VERIFY(!window.findChild<Channel *>()->busy());
    QTimer::singleShot(0, &window, [] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu) return;
      for (auto *action : menu->actions())
        if (action->text() == "Proton Pass / Passkey einrichten…") { menu->close(); action->trigger(); return; }
    });
    window.findChild<QPushButton *>("settings")->click();
    auto *password = window.findChild<QLineEdit *>("passkeyMaster");
    QVERIFY(password); password->setText("SYNTHETIC PASSKEY UI MASTER");
    window.findChild<QPushButton *>("passkeyStart")->click();
    QVERIFY(!passkeyUrl.isEmpty());
    auto complete = [this](const QString &key) {
      const auto enc = [](const QByteArray &v) { return QString::fromLatin1(v.toBase64(QByteArray::Base64UrlEncoding | QByteArray::OmitTrailingEquals)); };
      QNetworkAccessManager network;
      const auto token = passkeyUrl.fragment().toLatin1();
      auto url = passkeyUrl; url.setFragment({}); url.setPath("/config");
      QNetworkRequest request(url); request.setRawHeader("X-Lumen-Token", token);
      auto *reply = network.get(request);
      QTRY_VERIFY(reply->isFinished());
      QCOMPARE(reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(), 200);
      auto config = QJsonDocument::fromJson(reply->readAll()).object(); delete reply;
      const auto origin = url.adjusted(QUrl::RemovePath).toString();
      QJsonObject client{{"type", "webauthn.get"}, {"challenge", config["challenge"]}, {"origin", origin}};
      auto auth = QCryptographicHash::hash("localhost", QCryptographicHash::Sha256) + QByteArray(1, char(5)) + QByteArray(4, 0);
      QJsonObject response{{"key",key},{"credential","synthetic-credential"},{"clientData",enc(QJsonDocument(client).toJson())},{"authData",enc(auth)}};
      url.setPath("/complete"); request.setUrl(url); request.setRawHeader("Origin",origin.toLatin1());
      request.setHeader(QNetworkRequest::ContentTypeHeader,"application/json");
      reply = network.post(request,QJsonDocument(response).toJson());
      QTRY_VERIFY(reply->isFinished());
      QCOMPARE(reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(),200); delete reply;
    };
    complete(QString(64,'a'));
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(root.path()+"/passkey/browser.json"),10000);
    QVERIFY(window.unlocked());
    window.lock();
    QTRY_VERIFY(!window.findChild<QLineEdit *>("passkeyMaster"));
    auto *quick = window.findChild<QPushButton *>("passkeyUnlock"); QVERIFY(quick); quick->click();
    window.findChild<QPushButton *>("passkeyStart")->click();
    complete(QString(64,'a'));
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(),10000);
    QTRY_VERIFY(!window.findChild<Channel *>()->busy());
    window.lock();
    QTRY_VERIFY(!window.findChild<QLineEdit *>("passkeyMaster"));
    quick = window.findChild<QPushButton *>("passkeyUnlock"); QVERIFY(quick); quick->click();
    window.findChild<QPushButton *>("passkeyStart")->click();
    complete(QString(64,'b'));
    QTRY_VERIFY_WITH_TIMEOUT(!window.findChild<QLineEdit *>("passkeyMaster"),10000);
    QVERIFY(!window.unlocked());
    QVERIFY(window.findChild<QLineEdit *>("master"));
  }
  void sessionComfortClosesWithoutLockingAndKeepsBrokerAlive() {
    QTemporaryDir root;
    QSettings("Lumen", "Vault").setValue("idleMinutes", -1);
    VaultWindow window(root.path()); window.show();
    auto *idle = window.findChild<QTimer *>("vaultIdleTimer");
    auto *keepalive = window.findChild<QTimer *>("vaultKeepaliveTimer");
    QVERIFY(idle && keepalive);
    QCOMPARE(idle->interval(), 900000);
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC COMFORT MASTER");
    window.findChild<QLineEdit *>("confirm")->setText(master->text());
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    auto *channel = window.findChild<Channel *>();
    QTRY_VERIFY(!channel->busy());
    auto *selector = window.findChild<QComboBox *>("vaultAutoLock");
    QVERIFY(selector); QCOMPARE(selector->currentData().toInt(), 15);
    selector->setCurrentIndex(selector->findData(30));
    QCOMPARE(idle->interval(), 1800000);
    QCOMPARE(QSettings("Lumen", "Vault").value("idleMinutes").toInt(), 30);
    window.copySecret("SYNTHETIC CLIPBOARD");
    window.close();
    QVERIFY(!window.isVisible()); QVERIFY(window.unlocked());
    QVERIFY(QApplication::clipboard()->text().isEmpty());
    window.show(); QVERIFY(window.unlocked());
    idle->start(1000);
    const auto remaining = idle->remainingTime();
    QTest::qWait(60);
    QVERIFY(QMetaObject::invokeMethod(keepalive, "timeout", Qt::DirectConnection));
    QTRY_VERIFY(!channel->busy());
    QVERIFY(window.unlocked());
    QVERIFY(idle->remainingTime() < remaining);
    // Programmatically sent input and background work must not prolong access.
    QKeyEvent injected(QEvent::KeyPress, Qt::Key_A, Qt::NoModifier);
    QApplication::sendEvent(&window, &injected);
    QVERIFY(idle->remainingTime() < remaining);
    window.close();
    QSignalSpy retired(&window, &VaultWindow::retire);
    QTRY_VERIFY_WITH_TIMEOUT(!window.unlocked(), 2500);
    QCOMPARE(retired.count(), 1);
    QVERIFY(!window.isVisible()); QVERIFY(!keepalive->isActive());
    QSignalSpy quit(&window, &VaultWindow::quitRequested);
    window.close(); QCOMPARE(quit.count(), 1);
    QSettings("Lumen", "Vault").remove("idleMinutes");
  }
  void vaultServerSyncStartsAsExplicitNativeDialog() {
    QTemporaryDir root, isolatedConfig, runtime;
    const auto oldConfig=qgetenv("XDG_CONFIG_HOME");
    const auto oldData=qgetenv("XDG_DATA_HOME");
    qputenv("XDG_CONFIG_HOME",isolatedConfig.path().toUtf8());
    qputenv("XDG_DATA_HOME",runtime.path().toUtf8());
    auto restoreData=qScopeGuard([&]{if(oldData.isNull())qunsetenv("XDG_DATA_HOME");else qputenv("XDG_DATA_HOME",oldData);});
    auto restore=qScopeGuard([&]{if(oldConfig.isNull())qunsetenv("XDG_CONFIG_HOME");else qputenv("XDG_CONFIG_HOME",oldConfig);});
    QVERIFY(QDir().mkpath(runtime.path()+"/lumen/files"));
    QVERIFY(QDir().mkpath(runtime.path()+"/lumen/bin"));
    QVERIFY(QFile::link("/usr/bin/python3",runtime.path()+"/lumen/bin/lumen-python"));
    QFile helper(runtime.path()+"/lumen/files/vault_sync.py");QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json,sys,hashlib
from pathlib import Path
r=json.load(sys.stdin)
p=Path(r['root'],'vault.kdbx')
h=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ''
stage=Path(r['root'],'sync-test-stage')
mode=stage.read_text() if stage.exists() else 'matching'
if r['op']=='info':
 versions=[] if mode=='empty' else [dict(id='11111111-1111-4111-8111-111111111111',current=True,sha256='a'*64 if mode=='different' else h or 'a'*64,size=8192,created='2026-10-06T12:00:00Z')]
 print(json.dumps(dict(scope='synthetic',server='https://lumen.example',user='Beispielkonto',local_hash=h,versions=versions)))
elif r['op']=='upload':
 assert mode=='empty' and r['expected']=='' and r['local_hash']==h
 stage.write_text('matching')
 print(json.dumps(dict(applied=True)))
else:
 assert r['op']=='download'
 print(json.dumps(dict(path=str(p),sha256=h)))
)PY");helper.close();
    VaultWindow window(root.path());window.show();
    QPushButton *open=nullptr;
    for(auto *button:window.findChildren<QPushButton*>())if(button->text()=="Tresor von Lumen Server übernehmen…")open=button;
    QVERIFY(open);open->click();
    auto *versions=window.findChild<QListWidget*>("syncVersions");
    QVERIFY(versions);QTRY_COMPARE(versions->count(),1);
    auto *password=window.findChild<QLineEdit*>("syncMaster");
    QVERIFY(password);QCOMPARE(password->echoMode(),QLineEdit::Password);
    QVERIFY(password->inputMethodHints()&Qt::ImhSensitiveData);
    QCOMPARE(password->text(),QString());
    QVERIFY(!QFileInfo::exists(root.path()+"/vault.kdbx"));
    QTest::qWait(100);
    if(qEnvironmentVariableIsSet("LUMEN_VAULT_SYNC_CAPTURE")){
      auto *dialog=qobject_cast<QDialog*>(versions->window());QVERIFY(dialog);
      QVERIFY(dialog->grab().save("/tmp/lumen-vault-sync-dialog.png"));
    }
    auto *merge = window.findChild<QPushButton *>("syncMerge");
    QVERIFY(merge); QVERIFY(!merge->isVisible());
    QPointer<QDialog> dialog = qobject_cast<QDialog *>(versions->window());
    dialog->close(); QTRY_VERIFY(!dialog);
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC SYNC UI MASTER");
    window.findChild<QLineEdit *>("confirm")->setText(master->text());
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    auto *channel = window.findChild<Channel *>();
    QVERIFY(channel);
    QTRY_VERIFY(!channel->busy());
    QTimer::singleShot(0, &window, [] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu) return;
      for (auto *action : menu->actions()) {
        if (action->text() == "Serverabgleich…") { menu->close(); action->trigger(); return; }
      }
    });
    window.findChild<QPushButton *>("settings")->click();
    QTRY_VERIFY(window.findChild<QPushButton *>("syncMerge"));
    merge = window.findChild<QPushButton *>("syncMerge");
    QTRY_COMPARE(window.findChild<QListWidget *>("syncVersions")->count(), 1);
    QTRY_VERIFY(merge->isEnabled()); QVERIFY(merge->isVisible());
    QFile active(root.path()+"/vault.kdbx"); QVERIFY(active.open(QIODevice::ReadOnly));
    const auto before = active.readAll(); active.close();
    auto *preview = window.findChild<QPushButton *>("syncPreview");
    QVERIFY(preview); QVERIFY(preview->isEnabled()); preview->click();
    QTRY_VERIFY_WITH_TIMEOUT(([&window] { for (auto *label : window.findChildren<QLabel *>())
      if (label->text().contains("0 neue Einträge · 0 abweichende Einträge")) return true;
      return false; })(), 10000);
    QVERIFY(active.open(QIODevice::ReadOnly)); QCOMPARE(active.readAll(), before); active.close();
    bool asked = false;
    QTimer::singleShot(0, &window, [&asked] {
      auto *question = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
      if (question) { asked = true; question->button(QMessageBox::Cancel)->click(); }
    });
    merge->click();
    QVERIFY(asked);
    QTest::qWait(100);
    QVERIFY(active.open(QIODevice::ReadOnly)); QCOMPARE(active.readAll(), before);
    active.close();
    if (qEnvironmentVariableIsSet("LUMEN_VAULT_SYNC_CAPTURE"))
      QVERIFY(merge->window()->grab().save("/tmp/lumen-vault-merge-dialog.png"));
    auto findButton = [&window](const QString &text) -> QPushButton * {
      for (auto *button : window.findChildren<QPushButton *>())
        if (button->text() == text) return button;
      return nullptr;
    };
    auto *refresh = findButton("Aktualisieren");
    auto *publish = findButton("Lokale Fassung veröffentlichen");
    auto *automatic = findButton("Automatik aktivieren");
    auto *take = findButton("Fassung übernehmen");
    auto *options = findButton("Weitere Optionen");
    QVERIFY(refresh && publish && automatic && take && options);
    QVERIFY(automatic->isEnabled());
    QFile stage(root.path()+"/sync-test-stage");
    QVERIFY(stage.open(QIODevice::WriteOnly)); stage.write("different"); stage.close();
    refresh->click(); QTRY_VERIFY(refresh->isEnabled());
    QVERIFY(!automatic->isEnabled());
    QVERIFY(preview->isEnabled() && merge->isEnabled() && take->isEnabled());
    QVERIFY(stage.open(QIODevice::WriteOnly|QIODevice::Truncate)); stage.write("empty"); stage.close();
    refresh->click(); QTRY_VERIFY(refresh->isEnabled());
    QCOMPARE(window.findChild<QListWidget *>("syncVersions")->count(), 0);
    QVERIFY(publish->isVisible() && publish->isEnabled());
    QCOMPARE(publish->text(), QString("Erste Serverfassung erstellen"));
    QVERIFY(!automatic->isEnabled());
    QVERIFY(!preview->isEnabled() && !merge->isEnabled() && !take->isEnabled());
    options->click(); options->click(); QVERIFY(publish->isVisible());
    if (qEnvironmentVariableIsSet("LUMEN_VAULT_SYNC_CAPTURE"))
      QVERIFY(publish->window()->grab().save("/tmp/lumen-vault-first-sync.png"));
    asked = false;
    QTimer::singleShot(0, &window, [&asked] {
      auto *question = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
      if (question) { asked = true; question->button(QMessageBox::Cancel)->click(); }
    });
    publish->click(); QVERIFY(asked);
    QVERIFY(stage.open(QIODevice::ReadOnly)); QCOMPARE(stage.readAll(), QByteArray("empty")); stage.close();
    QTimer::singleShot(0, &window, [] {
      auto *question = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
      if (question) question->button(QMessageBox::Yes)->click();
    });
    publish->click();
    QTRY_COMPARE(window.findChild<QListWidget *>("syncVersions")->count(), 1);
    QTRY_VERIFY(automatic->isEnabled());
    QVERIFY(!publish->isVisible());
    QVERIFY(active.open(QIODevice::ReadOnly)); QCOMPARE(active.readAll(), before);
    // Closing sync must release the editor guard before another native form opens.
    QPointer<QDialog> closing = qobject_cast<QDialog *>(publish->window());
    QVERIFY(closing); closing->close();
    QTRY_VERIFY(!closing);
    QTRY_VERIFY(!channel->busy());
    QVERIFY(window.findChild<QPushButton *>("new"));
    window.findChild<QPushButton *>("new")->click();
    QTRY_VERIFY(window.findChild<QPushButton *>("save"));
    window.lock();
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
    QFETCH(bool, server);
    QTemporaryDir root;
    VaultWindow parent(root.path());
    QStringList operations;
    QJsonObject prepared;
    const QJsonObject serverTarget{{"server", "https://server.test"},
                                   {"device_id", "12345678-1234-1234-1234-123456789abc"}};
    const QString serverRepo = "rest:https://server.test/backup/12345678-1234-1234-1234-123456789abc/";
    std::function<void(QJsonValue)> finish;
    std::function<void(QString)> fail;
    BackupWizard wizard(
        false,
        [&](QJsonObject args, auto done, auto failed) {
          fail = failed;
          operations << args["op"].toString();
          if (args["op"] == "setup_inventory")
            done(QJsonObject{
                {"servers", QJsonArray{QJsonObject{{"label", "Lumen Server · https://server.test"}, {"server_target", serverTarget}}}},
                {"files",
                 QJsonArray{QJsonObject{{"label", "Dokumente"},
                                        {"path", "/home/example/Documents"}}}},
                {"lumen",
                 QJsonArray{QJsonObject{{"label", "Wissen"},
                                        {"path", "/home/example/Wissen"}}}},
                {"vault",
                 QJsonArray{QJsonObject{{"label", "Passwort-Tresor"},
                                        {"path", "/home/example/Vault"}}}}});
          else if (args["op"] == "test_target") {
            if (server) {
              QCOMPARE(args["server_target"].toObject(), serverTarget);
              done(QJsonObject{{"path", serverRepo}, {"server_target", serverTarget}, {"existing", false}});
            } else done(QJsonObject{{"path", "/media/Backup"},
                             {"tested", true},
                             {"free", 1024.0 * 1024 * 1024 * 500}});
          }
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
    if (server) {
      auto *kind = wizard.findChild<QComboBox *>("backupTargetKind");
      kind->setCurrentIndex(kind->findData("server"));
      QCOMPARE(wizard.findChild<QComboBox *>("backupServer")->count(), 1);
      capture("server-destination");
      QVERIFY(backupKeyDestinationAllowed(root.path() + "/recovery.txt", serverRepo));
    }
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
    if (server) {
      QCOMPARE(prepared["server_target"].toObject(), serverTarget);
      QCOMPARE(prepared["repository"].toString(), serverRepo);
    }
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
  void guidedBackupCompletesOnlyAfterProbe_data() {
    QTest::addColumn<bool>("server");
    QTest::newRow("local") << false;
    QTest::newRow("server") << true;
  }
  void backupsRouteLeavesVaultPrivate() {
    QTemporaryDir root;
    VaultWindow window(root.path());
    QSignalSpy requests(&window, &VaultWindow::backupsRequested);
    window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    QVERIFY(master);
    master->setText("SYNTHETIC UNSENT");
    window.copySecret("SYNTHETIC CLIPBOARD");
    for (int i = 0; i < 3; ++i) {
      window.showSection(1);
      QCOMPARE(window.section(), 0);
      QCOMPARE(requests.size(), i + 1);
      QCOMPARE(requests.last().size(), 0); // No secret or backup key forwarded.
      QCOMPARE(master->text(), QString("SYNTHETIC UNSENT"));
      QVERIFY(QApplication::clipboard()->text().isEmpty());
      QVERIFY(window.findChildren<BackupPage *>().isEmpty());
      QVERIFY(window.findChildren<QTabBar *>("vaultSections").isEmpty());
      QVERIFY(!window.unlocked());
      window.showSection(0);
    }
    window.findChild<QLineEdit *>("confirm")->setText(master->text());
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    window.showSection(1);
    QVERIFY(window.unlocked());
    window.lock();
    QVERIFY(!window.unlocked());
  }
  void catalogueSurvivesLockWithoutGrantingSecretUse() {
    QTemporaryDir root;
    Channel seed(root.path());
    bool ready=false;
    seed.call({"create","SYNTHETIC CATALOGUE MASTER"},[&](QStringList){ready=true;});
    QTRY_VERIFY_WITH_TIMEOUT(ready,10000);
    ready=false;
    seed.call({"put","","Title","Example API","LumenType","token","URL","https://api.example/path?private=hidden",
      "UserName","PRIVATE USER","Password","PRIVATE SECRET","Notes","PRIVATE NOTE"},[&](QStringList){ready=true;});
    QTRY_VERIFY_WITH_TIMEOUT(ready,10000);
    ready=false;
    seed.call({"connections","0"},[&](QStringList fields){QCOMPARE(fields.size(),2);ready=true;});
    QTRY_VERIFY(ready);
    seed.stop();
    VaultWindow window(root.path());window.show();
    auto *master=window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC CATALOGUE MASTER");QTest::keyClick(master,Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(),10000);
    const auto path=root.path()+"/assistant-catalogue.json";
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(path),10000);
    QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));
    const auto bytes=file.readAll();file.close();
    for (const auto *hidden:{"PRIVATE USER","PRIVATE SECRET","PRIVATE NOTE","hidden","/path"}) QVERIFY(!bytes.contains(hidden));
    const auto entries=QJsonDocument::fromJson(bytes).object()["entries"].toArray();
    QCOMPARE(entries.size(),1);QCOMPARE(entries[0].toObject()["origin"].toString(),QString("https://api.example"));
    QVERIFY(!(QFileInfo(path).permissions() & (QFileDevice::ReadGroup | QFileDevice::ReadOther)));
    auto *toggle=window.findChild<QCheckBox *>("apiAccess");
    QVERIFY(toggle);
    QTRY_VERIFY(toggle->isEnabled());
    QVERIFY(!toggle->isChecked());
    auto publishedCount=[&] {
      QFile current(path);
      if (!current.open(QIODevice::ReadOnly)) return -1;
      return int(QJsonDocument::fromJson(current.readAll()).object()["entries"].toArray().size());
    };
    toggle->click();
    QTRY_COMPARE(publishedCount(),0);
    window.lock();QVERIFY(QFileInfo::exists(path));
    QCOMPARE(publishedCount(),0);
    master=window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC CATALOGUE MASTER");QTest::keyClick(master,Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(),10000);
    toggle=window.findChild<QCheckBox *>("apiAccess");
    QTRY_VERIFY(toggle->isEnabled());
    QVERIFY(toggle->isChecked());
    toggle->click();
    QTRY_COMPARE(publishedCount(),1);
    window.lock();
    QCOMPARE(publishedCount(),1);
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
      const auto bytes = f.readAll();
      if (file == "assistant-catalogue.json") {
        QVERIFY(!bytes.contains("SYNTHETIC SECRET"));
        QVERIFY(!bytes.contains("SYNTHETIC NOTE"));
        QVERIFY(!bytes.contains("SYNTHETIC TEST MASTER"));
      } else QVERIFY(!bytes.contains("SYNTHETIC"));
    }
  }
};
QTEST_MAIN(VaultTest)
#include "test.moc"
