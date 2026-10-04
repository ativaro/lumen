// SPDX-License-Identifier: MIT
#include "vault.h"
#include <fcntl.h>
#include <sys/file.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
int main(int argc, char **argv) {
  if (argc != 2 || QByteArray(argv[1]) != "--laboratory-only")
    return 2;
  struct rlimit core{0, 0};
  if (setrlimit(RLIMIT_CORE, &core) != 0 || prctl(PR_SET_DUMPABLE, 0) != 0 ||
      prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0)
    return 1;
  umask(0077);
  QApplication app(argc, argv);
  app.setOrganizationName("Lumen");
  app.setApplicationName("VaultLab");
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
  VaultWindow window(root);
  QObject::connect(&window, &VaultWindow::retire, &app, [&] {
    window.hide();
    QProcess::startDetached(QCoreApplication::applicationFilePath(),
                            {"--laboratory-only"});
    app.quit();
  });
  window.show();
  const int result = app.exec();
  close(lease);
  return result;
}
