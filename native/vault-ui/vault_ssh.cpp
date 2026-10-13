// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "vault_ssh.h"
#include "vault.h"
#include "web_login.h"
#include <fcntl.h>
#include <libssh/libssh.h>
#include <sys/stat.h>
#include <unistd.h>

VaultSsh::VaultSsh(QUrl target, QString user, QString password, QString command,
                   QString knownHosts, int port)
    : target(loginTarget(target, port)), storedTarget(target), user(std::move(user)),
      password(std::move(password)), command(std::move(command)),
      knownHosts(std::move(knownHosts)) {}
VaultSsh::~VaultSsh() {
  wipe(user);
  wipe(password);
}
QUrl VaultSsh::loginTarget(const QUrl &stored, int port) {
  if (port < 0 || port > 65535)
    return {};
  QUrl target;
  if (validUrl(stored))
    target = stored;
  else if (stored.isValid() && !stored.isRelative() &&
           (stored.scheme() == "http" || stored.scheme() == "https") &&
           !stored.host().isEmpty() && !stored.authority().contains('@')) {
    target.setScheme("ssh");
    target.setHost(stored.host());
    target.setPort(22);
  } else
    return {};
  if (port)
    target.setPort(port);
  return validUrl(target) ? target : QUrl();
}
bool VaultSsh::validUrl(const QUrl &u) {
  return u.isValid() && !u.isRelative() && u.scheme() == "ssh" &&
         !u.host().isEmpty() && !u.authority().contains('@') && !u.hasQuery() &&
         !u.hasFragment() && (u.path().isEmpty() || u.path() == "/") &&
         u.port(22) > 0;
}
bool VaultSsh::validCommand(const QString &c) {
  if (c.trimmed().isEmpty() || c.size() > 4096)
    return false;
  for (auto ch : c)
    if (ch.category() == QChar::Other_Control ||
        ch.category() == QChar::Other_Format || ch == QChar(0x2028) ||
        ch == QChar(0x2029))
      return false;
  return true;
}
bool VaultSsh::privateHostFile(const QString &path) {
  struct stat st{};
  const auto dir = QFileInfo(path).absolutePath().toUtf8(),
             file = path.toUtf8();
  if (lstat(dir.constData(), &st) || !S_ISDIR(st.st_mode) ||
      st.st_uid != geteuid() || (st.st_mode & 0077))
    return false;
  const int fd =
      ::open(file.constData(), O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0)
    return false;
  const bool ok = !fstat(fd, &st) && S_ISREG(st.st_mode) &&
                  st.st_uid == geteuid() && st.st_nlink == 1 &&
                  !(st.st_mode & 0077);
  ::close(fd);
  return ok;
}
bool VaultSsh::matches(const QUrl &u, const QString &name,
                       const QString &secret) const {
  return storedTarget == u && user == name && password == secret;
}
void VaultSsh::cancel() {
  cancelled = true;
  QMutexLocker lock(&mutex);
  wake.wakeAll();
}
void VaultSsh::approve(int stage) {
  QMutexLocker lock(&mutex);
  approved = stage;
  wake.wakeAll();
}
bool VaultSsh::waitForApproval(int stage) {
  QMutexLocker lock(&mutex);
  QDeadlineTimer deadline(65000);
  while (!cancelled && approved < stage && !deadline.hasExpired())
    wake.wait(&mutex, deadline);
  return !cancelled && approved >= stage;
}
void VaultSsh::run() {
  auto result = execute();
  if (result.contains("error") && sent)
    result = {{"error", "operation_outcome_unknown"}};
  emit resultReady(result);
}
QJsonObject VaultSsh::execute() {
  const auto fail = [](const char *code) {
    return QJsonObject{{"error", code}};
  };
  if (!validUrl(target) || user.isEmpty() || password.isEmpty() ||
      user.size() > 1024 || password.size() > 4096 || user.contains(QChar(0)) ||
      password.contains(QChar(0)) ||
      (!command.isEmpty() && !validCommand(command)))
    return fail("invalid_request");
  if (!privateHostFile(knownHosts))
    return fail("ssh_host_store_unavailable");
  auto session = ssh_new();
  if (!session)
    return fail("ssh_connection_failed");
  auto cleanup = qScopeGuard([&] {
    ssh_disconnect(session);
    ssh_free(session);
  });
  const auto host = target.host().toUtf8(), path = knownHosts.toUtf8();
  auto username = user.toUtf8(), secret = password.toUtf8();
  auto clear = qScopeGuard([&] {
    wipe(username);
    wipe(secret);
  });
  int port = target.port(22), no = 0;
  long timeout = 5;
  bool config = false;
  if (ssh_options_set(session, SSH_OPTIONS_PROCESS_CONFIG, &config) != SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_HOST, host.constData()) != SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_PORT, &port) != SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_USER, username.constData()) !=
          SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_KNOWNHOSTS, path.constData()) !=
          SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_GLOBAL_KNOWNHOSTS, "/dev/null") !=
          SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_LOG_VERBOSITY, &no) != SSH_OK ||
      ssh_options_set(session, SSH_OPTIONS_TIMEOUT, &timeout) != SSH_OK ||
      cancelled || ssh_connect(session) != SSH_OK)
    return fail("ssh_connection_failed");
  ssh_key key = nullptr;
  unsigned char *hash = nullptr;
  size_t size = 0;
  if (ssh_get_server_publickey(session, &key) != SSH_OK)
    return fail("ssh_connection_failed");
  const int hashed =
      ssh_get_publickey_hash(key, SSH_PUBLICKEY_HASH_SHA256, &hash, &size);
  ssh_key_free(key);
  if (hashed != SSH_OK)
    return fail("ssh_connection_failed");
  char *fp = ssh_get_fingerprint_hash(SSH_PUBLICKEY_HASH_SHA256, hash, size);
  const auto fingerprint = QString::fromUtf8(fp ? fp : "");
  ssh_string_free_char(fp);
  ssh_clean_pubkey_hash(&hash);
  if (fingerprint.isEmpty())
    return fail("ssh_connection_failed");
  const auto state = ssh_session_is_known_server(session);
  if (state == SSH_KNOWN_HOSTS_CHANGED || state == SSH_KNOWN_HOSTS_OTHER)
    return fail("ssh_host_key_changed");
  if (state != SSH_KNOWN_HOSTS_OK && state != SSH_KNOWN_HOSTS_UNKNOWN &&
      state != SSH_KNOWN_HOSTS_NOT_FOUND)
    return fail("ssh_host_store_unavailable");
  emit approvalNeeded(fingerprint, state == SSH_KNOWN_HOSTS_OK);
  if (!waitForApproval(1))
    return fail("access_revoked");
  // Recheck pins after the native prompt, on the same SSH handshake.
  const auto now = ssh_session_is_known_server(session);
  if (now == SSH_KNOWN_HOSTS_CHANGED || now == SSH_KNOWN_HOSTS_OTHER)
    return fail("ssh_host_key_changed");
  if (now != SSH_KNOWN_HOSTS_OK &&
      (now != state || !privateHostFile(knownHosts) ||
       ssh_session_update_known_hosts(session) != SSH_OK))
    return fail("ssh_host_store_unavailable");
  if (cancelled)
    return fail("access_revoked");
  if (ssh_userauth_password(session, username.constData(),
                            secret.constData()) != SSH_AUTH_SUCCESS)
    return fail("ssh_authentication_failed");
  if (cancelled)
    return fail("access_revoked");
  if (command.isEmpty())
    return {{"authenticated", true}, {"fingerprint", fingerprint}};
  emit executionReady();
  if (!waitForApproval(2))
    return fail("access_revoked");
  auto channel = ssh_channel_new(session);
  if (!channel)
    return fail("ssh_connection_failed");
  auto closeChannel = qScopeGuard([&] { ssh_channel_free(channel); });
  if (ssh_channel_open_session(channel) != SSH_OK)
    return fail("ssh_connection_failed");
  if (cancelled)
    return fail("access_revoked");
  auto cmd = command.toUtf8();
  sent = true;
  if (ssh_channel_request_exec(channel, cmd.constData()) != SSH_OK)
    return fail("operation_outcome_unknown");
  ssh_channel_send_eof(channel);
  QByteArray output[2];
  auto clearOutput = qScopeGuard([&] {
    wipe(output[0]);
    wipe(output[1]);
  });
  QElapsedTimer elapsed;
  elapsed.start();
  while (!ssh_channel_is_eof(channel) || ssh_channel_poll(channel, 0) > 0 ||
         ssh_channel_poll(channel, 1) > 0) {
    if (cancelled || !ssh_is_connected(session) || elapsed.elapsed() > 30000)
      return fail("operation_outcome_unknown");
    if (ssh_channel_is_closed(channel) && ssh_channel_poll(channel, 0) <= 0 &&
        ssh_channel_poll(channel, 1) <= 0)
      break;
    for (int stream = 0; stream < 2; ++stream) {
      char buffer[4096]{};
      const int count =
          ssh_channel_read_timeout(channel, buffer, sizeof(buffer), stream, 50);
      if (count > 0)
        output[stream].append(buffer, count);
      ::explicit_bzero(buffer, sizeof(buffer));
      if (count == SSH_ERROR || output[0].size() + output[1].size() > 65536)
        return fail("operation_outcome_unknown");
    }
  }
  uint32_t exitCode = 0;
  char *exitSignal = nullptr;
  int core = 0;
  ssh_set_blocking(session, 0);
  int exitResult;
  do {
    exitResult =
        ssh_channel_get_exit_state(channel, &exitCode, &exitSignal, &core);
    if (exitResult == SSH_AGAIN)
      QThread::msleep(10);
  } while (exitResult == SSH_AGAIN && !cancelled && ssh_is_connected(session) &&
           !ssh_channel_is_closed(channel) &&
           elapsed.elapsed() < 30000);
  const bool signalled = exitSignal && *exitSignal;
  ssh_string_free_char(exitSignal);
  if (exitResult != SSH_OK || signalled || cancelled)
    return fail("operation_outcome_unknown");
  QJsonObject result{{"completed", true},
                     {"exit_code", qint64(exitCode)},
                     {"untrusted", true}};
  for (int i = 0; i < 2; ++i) {
    QString text = QString::fromUtf8(output[i]);
    for (const auto &value : {user, password}) {
      const auto bytes = value.toUtf8();
      for (const auto &representation :
           {value, QString::fromLatin1(bytes.toBase64()),
            QString::fromLatin1(bytes.toHex()),
            QString::fromLatin1(bytes.toPercentEncoding())})
        text.replace(representation, QString::fromUtf8("[•••]"));
    }
    if (VaultWeb::containsSecret(text.toUtf8(), {user, password}))
      return {{"completed", true},
              {"exit_code", qint64(exitCode)},
              {"output_withheld", true}};
    // Remote terminal control characters are data, never terminal/UI
    // formatting.
    for (int j = 0; j < text.size(); ++j)
      if ((text[j].category() == QChar::Other_Control && text[j] != '\n' &&
           text[j] != '\t') ||
          text[j].category() == QChar::Other_Format)
        text[j] = QChar(0xfffd);
    result[i == 0 ? "stdout" : "stderr"] = text;
  }
  return result;
}
