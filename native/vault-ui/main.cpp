// SPDX-License-Identifier: MIT
#include "vault.h"
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
  VaultWindow window(root);
  window.show();
  return app.exec();
}
