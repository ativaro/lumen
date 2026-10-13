// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "vault.h"
#include <QtNetwork>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>

static void activateWindow(QWidget *window) {
  window->setWindowState(window->windowState() & ~Qt::WindowMinimized);
  window->show();
  auto *target = QApplication::activeModalWidget();
  if (!target) target = window;
  target->raise();
  target->activateWindow();
  if (target->windowHandle()) target->windowHandle()->requestActivate();
  const auto data = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
  const QStringList directories{
      QCoreApplication::applicationDirPath() + "/../../files",
      data + "/lumen/files", "/usr/share/lumen/files",
      QCoreApplication::applicationDirPath() + "/../../../files"};
  for (const auto &directory : directories) {
    const auto script = QDir(directory).absoluteFilePath("lumen_activation.py");
    const auto python = directory == "/usr/share/lumen/files"
        ? QString("/usr/bin/lumen-python") : QDir(directory).absoluteFilePath("../bin/lumen-python");
    if (QFileInfo::exists(script) && QFileInfo(python).isExecutable()) {
      QProcess::startDetached(python, {script, QString::number(QCoreApplication::applicationPid()), "lumen-vault"});
      break;
    }
  }
}

static bool openSystemBackups() {
  const QStringList candidates{
      QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) +
          "/lumen/bin/lumen-system",
      "/usr/bin/lumen-system"};
  for (const auto &program : candidates)
    if (QFileInfo(program).isExecutable())
      return QProcess::startDetached(program, {"--page", "backups"});
  return false;
}

int main(int argc, char **argv) {
  if (argc < 2 || argc > 4 || QByteArray(argv[1]) != "--laboratory-only") return 2;
  bool background = false, backups = false;
  for (int i = 2; i < argc; ++i) {
    if (QByteArray(argv[i]) == "--background") background = true;
    else if (QByteArray(argv[i]) == "--backups") backups = true;
    else return 2;
  }
  // Route backups before creating a restricted secret-vault process. System has
  // its own update/diagnostic policy and must not inherit the vault sandbox.
  if (backups) {
    QCoreApplication routing(argc, argv);
    return openSystemBackups() ? 0 : 1;
  }
  struct rlimit core{0, 0};
  if (setrlimit(RLIMIT_CORE, &core) != 0 || prctl(PR_SET_DUMPABLE, 0) != 0 ||
      prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0)
    return 1;
  umask(0077);
  // Vault web sessions never expose a debugging port or accept sandbox bypass flags.
  qunsetenv("QTWEBENGINE_REMOTE_DEBUGGING");
  qunsetenv("QTWEBENGINE_CHROMIUM_FLAGS");
  qunsetenv("QTWEBENGINE_DISABLE_SANDBOX");
  QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
  QApplication app(argc, argv);
  app.setQuitOnLastWindowClosed(false);
  app.setOrganizationName("Lumen");
  app.setApplicationName("lumen-vault");
  app.setApplicationDisplayName("Lumen Vault");
  app.setDesktopFileName("lumen-vault");
  const auto root =
      QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) +
      "/lumen-vault-lab";
  if (!QDir().mkpath(root))
    return 1;
  struct stat st{};
  auto path = root.toUtf8();
  if (lstat(path.constData(), &st) != 0 || !S_ISDIR(st.st_mode) ||
      st.st_uid != geteuid() || (st.st_mode & 0077) != 0)
    return 1;
  const auto runtime = qgetenv("XDG_RUNTIME_DIR");
  if (runtime.isEmpty() || !runtime.startsWith('/'))
    return 1;
  const int directory = ::open(runtime.constData(),
                               O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (directory < 0)
    return 1;
  struct stat privacy{};
  if (fstat(directory, &privacy) != 0 || privacy.st_uid != geteuid() ||
      (privacy.st_mode & 0077) != 0) {
    close(directory);
    return 1;
  }
  const int lease = openat(directory, "lumen-vault-privacy.lock",
                           O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
  close(directory);
  if (lease < 0)
    return 1;
  if (fstat(lease, &privacy) != 0 || !S_ISREG(privacy.st_mode) ||
      privacy.st_uid != geteuid() || privacy.st_nlink != 1 ||
      (privacy.st_mode & 0077) != 0 || flock(lease, LOCK_SH | LOCK_NB) != 0) {
    close(lease);
    QMessageBox::information(
        nullptr, "Lumen Vault",
        "Screen capture is running. Open Vault when it has finished.");
    return 1;
  }
  const auto endpoint = QString::fromUtf8(runtime) + "/lumen-vault-window";
  const int requestedSection = backups ? 1 : 0;
  QLockFile owner(endpoint + ".lock");
  if (!owner.tryLock(0)) {
    QLocalSocket client;
    client.connectToServer(endpoint);
    if (!client.waitForConnected(2000))
      return 1;
    client.write(requestedSection == 1 ? "backups\n" : "activate\n");
    if (!client.waitForBytesWritten(2000))
      return 1;
    close(lease);
    return 0;
  }
  QLocalServer::removeServer(endpoint);
  QLocalServer server;
  server.setSocketOptions(QLocalServer::UserAccessOption);
  if (!server.listen(endpoint))
    return 1;
  VaultWindow window(root);
  QObject::connect(&window, &VaultWindow::backupsRequested, &window, [&] {
    if (!openSystemBackups())
      QMessageBox::warning(&window, "Lumen System", window.tx(
          "Sicherungen konnten nicht geöffnet werden.", "Could not open backups."));
  });
  if (!window.startAccessServer(QString::fromUtf8(runtime)))
    return 1;
  QObject::connect(&server, &QLocalServer::newConnection, &window, [&] {
    while (server.hasPendingConnections()) {
      auto *peer = server.nextPendingConnection();
      peer->setReadBufferSize(32);
      QTimer::singleShot(2000, peer, &QLocalSocket::abort);
      QObject::connect(peer, &QLocalSocket::readyRead, &window, [&, peer] {
        if (!peer->canReadLine())
          return;
        const auto message = peer->readLine(32);
        if (message == "backups\n" || message == "vault\n" || message == "activate\n") {
          if (message != "activate\n" && !QApplication::activeModalWidget())
            window.showSection(message == "backups\n" ? 1 : 0);
          if (message != "backups\n") activateWindow(&window);
        }
        peer->disconnectFromServer();
      });
      QObject::connect(peer, &QLocalSocket::disconnected, peer,
                       &QObject::deleteLater);
    }
  });
  QObject::connect(&window, &VaultWindow::quitRequested, &app, &QApplication::quit);
  QObject::connect(&window, &VaultWindow::retire, &app, [&] {
    const bool visible = window.isVisible();
    window.hide();
    QStringList arguments{"--laboratory-only"};
    if (!visible) arguments << "--background";
    window.stopAccessServer();
    server.close();
    owner.unlock();
    QProcess::startDetached(QCoreApplication::applicationFilePath(), arguments);
    app.quit();
  });
  window.showSection(requestedSection);
  if (!background) window.show();
  const int result = app.exec();
  close(lease);
  return result;
}
