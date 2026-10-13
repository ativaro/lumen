// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "vault_ssh.h"
#include <QtTest>
#include <libssh/libssh.h>
#include <libssh/server.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <thread>

static int fixtureKey(ssh_key *key) {
#if LIBSSH_VERSION_INT >= SSH_VERSION_INT(0, 12, 0)
  return ssh_pki_generate_key(SSH_KEYTYPE_ED25519, nullptr, key);
#else
  return ssh_pki_generate(SSH_KEYTYPE_ED25519, 0, key);
#endif
}
class Site {
public:
  ssh_bind listener = nullptr;
  std::thread thread;
  std::atomic_bool stop{false};
  std::atomic_int auths{0}, commands{0};
  int port = 0;
  Site(const QString &key) {
    listener = ssh_bind_new();
    int p = 0;
    ssh_bind_options_set(listener, SSH_BIND_OPTIONS_BINDADDR, "127.0.0.1");
    ssh_bind_options_set(listener, SSH_BIND_OPTIONS_BINDPORT, &p);
    const auto path = key.toUtf8();
    ssh_bind_options_set(listener, SSH_BIND_OPTIONS_HOSTKEY, path.constData());
    if (ssh_bind_listen(listener) != SSH_OK)
      return;
    sockaddr_in addr{};
    socklen_t size = sizeof(addr);
    getsockname(ssh_bind_get_fd(listener), reinterpret_cast<sockaddr *>(&addr),
                &size);
    port = ntohs(addr.sin_port);
    thread = std::thread([this] { serve(); });
  }
  ~Site() {
    stop = true;
    if (thread.joinable())
      thread.join();
    ssh_bind_free(listener);
  }
  QUrl url() const { return QUrl("ssh://127.0.0.1:" + QString::number(port)); }
  void serve() {
    while (!stop) {
      pollfd f{ssh_bind_get_fd(listener), POLLIN, 0};
      if (::poll(&f, 1, 100) <= 0)
        continue;
      auto s = ssh_new();
      long timeout = 2;
      ssh_options_set(s, SSH_OPTIONS_TIMEOUT, &timeout);
      if (ssh_bind_accept(listener, s) != SSH_OK ||
          ssh_handle_key_exchange(s) != SSH_OK) {
        ssh_free(s);
        continue;
      }
      ssh_channel channel = nullptr;
      bool authenticated = false;
      while (!stop && ssh_is_connected(s)) {
        auto m = ssh_message_get(s);
        if (!m)
          break;
        const int type = ssh_message_type(m), sub = ssh_message_subtype(m);
        if (type == SSH_REQUEST_AUTH && sub == SSH_AUTH_METHOD_PASSWORD) {
          ++auths;
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
          authenticated =
              QByteArray(ssh_message_auth_user(m)) == "synthetic_user_X42" &&
              QByteArray(ssh_message_auth_password(m)) ==
                  "synthetic_secret_X99";
#pragma GCC diagnostic pop
          if (authenticated)
            ssh_message_auth_reply_success(m, 0);
          else {
            ssh_message_auth_set_methods(m, SSH_AUTH_METHOD_PASSWORD);
            ssh_message_reply_default(m);
          }
        } else if (type == SSH_REQUEST_CHANNEL_OPEN &&
                   sub == SSH_CHANNEL_SESSION && authenticated) {
          channel = ssh_message_channel_request_open_reply_accept(m);
        } else if (type == SSH_REQUEST_CHANNEL &&
                   sub == SSH_CHANNEL_REQUEST_EXEC && authenticated) {
          ++commands;
          const QByteArray cmd = ssh_message_channel_request_command(m);
          ssh_message_channel_request_reply_success(m);
          if (cmd == "disconnect") {
            ssh_message_free(m);
            break;
          }
          QByteArray out =
              cmd == "reflect"
                  ? QByteArray("synthetic_user_X42 synthetic_secret_X99")
              : cmd == "overflow" ? QByteArray(70000, 'x')
                                  : QByteArray("fixture output\n");
          if (channel) {
            ssh_channel_write(channel, out.constData(), out.size());
            ssh_channel_write_stderr(channel, "fixture stderr\n", 15);
            ssh_channel_request_send_exit_status(channel,
                                                 cmd == "failure" ? 7 : 0);
            ssh_channel_send_eof(channel);
            ssh_channel_close(channel);
          }
          ssh_message_free(m);
          break;
        } else {
          if (type == SSH_REQUEST_AUTH)
            ssh_message_auth_set_methods(m, SSH_AUTH_METHOD_PASSWORD);
          ssh_message_reply_default(m);
        }
        ssh_message_free(m);
      }
      if (channel)
        ssh_channel_free(channel);
      ssh_disconnect(s);
      ssh_free(s);
    }
  }
};
class SshTest : public QObject {
  Q_OBJECT
  QTemporaryDir root;
  QString key;
  QJsonObject run(Site &site, const QString &hosts, const QString &command,
                  bool approve = true, bool execute = true,
                  QString password = "synthetic_secret_X99") {
    VaultSsh worker(site.url(), "synthetic_user_X42", password, command, hosts);
    QJsonObject result;
    connect(&worker, &VaultSsh::approvalNeeded, this,
            [&](QString fingerprint, bool) {
              if (!fingerprint.startsWith("SHA256:"))
                return;
              if (approve)
                worker.approve(1);
              else
                worker.cancel();
            });
    connect(&worker, &VaultSsh::executionReady, this, [&] {
      if (execute)
        worker.approve(2);
      else
        worker.cancel();
    });
    connect(&worker, &VaultSsh::resultReady, this,
            [&](QJsonObject r) { result = r; });
    QEventLoop loop;
    connect(&worker, &QThread::finished, &loop, &QEventLoop::quit);
    QTimer::singleShot(15000, &loop, &QEventLoop::quit);
    worker.start();
    loop.exec();
    worker.cancel();
    worker.wait(6000);
    return result;
  }
private slots:
  void initTestCase() {
    ssh_key k = nullptr;
    QCOMPARE(fixtureKey(&k), SSH_OK);
    key = root.path() + "/server-key";
    QCOMPARE(ssh_pki_export_privkey_file(k, nullptr, nullptr, nullptr,
                                         key.toUtf8().constData()),
             SSH_OK);
    ssh_key_free(k);
  }
  void validation() {
    QVERIFY(VaultSsh::validUrl(QUrl("ssh://example.test:2222")));
    QCOMPARE(VaultSsh::loginTarget(QUrl("https://example.test:8443/admin?next=x#login")), QUrl("ssh://example.test:22"));
    QCOMPARE(VaultSsh::loginTarget(QUrl("http://[::1]/admin"), 2222), QUrl("ssh://[::1]:2222"));
    QCOMPARE(VaultSsh::loginTarget(QUrl("ssh://example.test:2222")), QUrl("ssh://example.test:2222"));
    for (auto u : {"https://user:secret@example.test/", "file:///tmp/example", "https:///missing", "ssh://example.test/command"})
      QVERIFY(VaultSsh::loginTarget(QUrl(u)).isEmpty());
    QVERIFY(VaultSsh::loginTarget(QUrl("https://example.test"), 65536).isEmpty());
    VaultSsh source(QUrl("https://example.test/admin"), "user", "secret", "", root.path()+"/pins");
    QVERIFY(source.matches(QUrl("https://example.test/admin"), "user", "secret"));
    QVERIFY(!source.matches(QUrl("https://example.test/changed"), "user", "secret"));
    for (auto u : {"https://example.test", "ssh://name@example.test",
                   "ssh://example.test/a", "ssh://example.test?x=1",
                   "ssh://example.test:0"})
      QVERIFY(!VaultSsh::validUrl(QUrl(u)));
    QVERIFY(VaultSsh::validCommand("printf '%s' 'Grüße'"));
    QVERIFY(!VaultSsh::validCommand("a\nb"));
    QVERIFY(!VaultSsh::validCommand(QString(4097, 'x')));
    QVERIFY(!VaultSsh::validCommand(QString("a") + QChar(0x202e)));
    QFile file(root.path() + "/target");
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.close();
    QVERIFY(QFile::link(file.fileName(), root.path() + "/link"));
    QVERIFY(!VaultSsh::privateHostFile(root.path() + "/link"));
  }
  void authenticationAndCommands() {
    QTemporaryDir dir;
    Site site(key);
    QVERIFY(site.port > 0);
    const auto hosts = dir.path() + "/known_hosts";
    auto r = run(site, hosts, "");
    QVERIFY(r.value("authenticated").toBool());
    QCOMPARE(site.auths.load(), 1);
    QCOMPARE(site.commands.load(), 0);
    r = run(site, hosts, "success");
    QVERIFY(r.value("completed").toBool());
    QCOMPARE(r.value("exit_code").toInt(-1), 0);
    QCOMPARE(r.value("stdout").toString(), QString("fixture output\n"));
    r = run(site, hosts, "failure");
    QCOMPARE(r.value("exit_code").toInt(), 7);
    r = run(site, hosts, "reflect");
    QVERIFY(!QJsonDocument(r).toJson().contains("synthetic_secret_X99"));
    QVERIFY(!QJsonDocument(r).toJson().contains("synthetic_user_X42"));
    QVERIFY(r.value("completed").toBool());
    QCOMPARE(site.commands.load(), 3);
  }
  void denyRevokeAndChangedHost() {
    QTemporaryDir dir;
    Site site(key);
    QVERIFY(site.port > 0);
    const auto hosts = dir.path() + "/known_hosts";
    QCOMPARE(run(site, hosts, "success", false).value("error"),
             "access_revoked");
    QCOMPARE(site.auths.load(), 0);
    QCOMPARE(site.commands.load(), 0);
    QCOMPARE(run(site, hosts, "success", true, false).value("error"),
             "access_revoked");
    QCOMPARE(site.commands.load(), 0);
    auto r = run(site, hosts, "", true, true, "incorrect synthetic password");
    QCOMPARE(r.value("error"), "ssh_authentication_failed");
    ssh_key other = nullptr;
    QCOMPARE(fixtureKey(&other), SSH_OK);
    char *pub = nullptr;
    QCOMPARE(ssh_pki_export_pubkey_base64(other, &pub), SSH_OK);
    QFile pins(hosts);
    QVERIFY(pins.open(QIODevice::WriteOnly | QIODevice::Truncate));
    pins.write("[127.0.0.1]:" + QByteArray::number(site.port) +
               " ssh-ed25519 " + pub + "\n");
    pins.close();
    ssh_string_free_char(pub);
    ssh_key_free(other);
    const auto count = site.auths.load();
    QCOMPARE(run(site, hosts, "").value("error"), "ssh_host_key_changed");
    QCOMPARE(site.auths.load(), count);
  }
  void unknownOutcomes() {
    QTemporaryDir dir;
    Site site(key);
    QVERIFY(site.port > 0);
    const auto hosts = dir.path() + "/known_hosts";
    QCOMPARE(run(site, hosts, "disconnect").value("error"),
             "operation_outcome_unknown");
    QCOMPARE(site.commands.load(), 1);
    QCOMPARE(run(site, hosts, "overflow").value("error"),
             "operation_outcome_unknown");
    QCOMPARE(site.commands.load(), 2);
  }
  void nativeConfirmationAndRevalidation_data() {
    QTest::addColumn<bool>("web");
    QTest::newRow("explicit SSH target") << false;
    QTest::newRow("website preserved with explicit SSH consent") << true;
  }
  void nativeConfirmationAndRevalidation() {
    QFETCH(bool, web);
    QTemporaryDir dir;
    Site site(key);
    QVERIFY(site.port > 0);
    QWidget window;
    QUrl stored = site.url();
    if (web) {
      stored.setScheme("https");
      stored.setPort(8443);
      stored.setPath("/admin");
      stored.setQuery("page=login");
    }
    QStringList fields{"LumenType",
                       "login",
                       "LumenHidden",
                       "0",
                       "UserName",
                       "synthetic_user_X42",
                       "Password",
                       "synthetic_secret_X99",
                       "URL",
                       stored.toString()};
    VaultAccess access(
        &window,
        [&](QString, std::function<void(QStringList)> done) { done(fields); },
        true, dir.path() + "/known_hosts");
    access.setConnections({}, {{"example",
                                {{"kind", "login"},
                                 {"title", "SSH fixture"},
                                 {"login_scheme", web ? "https" : "ssh"}}}});
    QVERIFY(access.listen(dir.path()));
    QVERIFY(access.connection()["entries"]
                .toArray()[0]
                .toObject()["ssh_available"]
                .toBool());
    auto send = [&](QLocalSocket &c) {
      c.connectToServer(dir.path() + "/lumen-vault-access");
      QVERIFY(c.waitForConnected());
      QJsonObject request{{"operation", "ssh_exec"}, {"reference", "vault:example"},
                          {"command", "success"}};
      if (web) request["port"] = site.port;
      c.write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n');
      c.flush();
    };
    QLocalSocket denied;
    send(denied);
    QTRY_VERIFY(QApplication::activeModalWidget());
    auto *d = qobject_cast<QDialog *>(QApplication::activeModalWidget());
    QVERIFY(!d->findChild<QPushButton *>("sshAllow")->isEnabled());
    QCOMPARE(site.auths.load(), 0);
    d->reject();
    QTRY_VERIFY(denied.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(denied.readAll()).object().value("error"),
             "access_denied");
    QLocalSocket changed;
    send(changed);
    QTRY_VERIFY(QApplication::activeModalWidget());
    d = qobject_cast<QDialog *>(QApplication::activeModalWidget());
    d->findChild<QCheckBox *>("sshTrustHost")->setChecked(true);
    if (web) {
      QVERIFY(!d->findChild<QPushButton *>("sshAllow")->isEnabled());
      d->findChild<QCheckBox *>("sshUseWebLogin")->setChecked(true);
    }
    fields[3] = "1";
    d->accept();
    QTRY_VERIFY(changed.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(changed.readAll()).object().value("error"),
             "access_revoked_or_invalid_profile");
    QCOMPARE(site.auths.load(), 0);
    fields[3] = "0";
    QLocalSocket success;
    send(success);
    QTRY_VERIFY(QApplication::activeModalWidget());
    d = qobject_cast<QDialog *>(QApplication::activeModalWidget());
    d->findChild<QCheckBox *>("sshTrustHost")->setChecked(true);
    if (web) {
      QVERIFY(!d->findChild<QPushButton *>("sshAllow")->isEnabled());
      d->findChild<QCheckBox *>("sshUseWebLogin")->setChecked(true);
    }
    d->accept();
    QTRY_VERIFY_WITH_TIMEOUT(success.bytesAvailable(), 15000);
    auto r = QJsonDocument::fromJson(success.readAll()).object();
    QVERIFY(r.value("completed").toBool());
    QVERIFY(!r.contains("error"));
    QCOMPARE(site.commands.load(), 1);
    QCOMPARE(fields.last(), stored.toString());
    if (web) {
      QLocalSocket unconfirmed;
      send(unconfirmed);
      QTRY_VERIFY(QApplication::activeModalWidget());
      d = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      QVERIFY(!d->findChild<QPushButton *>("sshAllow")->isEnabled());
      // Even accepting the dialog directly cannot bypass cross-protocol consent.
      d->accept();
      QTRY_VERIFY(unconfirmed.bytesAvailable());
      QCOMPARE(QJsonDocument::fromJson(unconfirmed.readAll()).object().value("error"), "access_denied");
      QCOMPARE(site.commands.load(), 1);
    }
    QLocalSocket locked;
    send(locked);
    QTRY_VERIFY(QApplication::activeModalWidget());
    access.revoke();
    QTRY_VERIFY(locked.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(locked.readAll()).object().value("error"),
             "access_revoked");
    QCOMPARE(site.commands.load(), 1);
  }
};
QTEST_MAIN(SshTest)
#include "ssh_test.moc"
