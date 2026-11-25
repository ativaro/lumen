# CI image for the desktop gate scripts/test-desktop.sh; PUBLISHING.md ("Verify locally") lists what it
# needs. The Arch base and a dated Arch Linux Archive snapshot keep a rebuild on the same packages.
#   docker build -t forge.example.invalid/lumen/desktop-ci:<date> packaging/ci
#   docker push forge.example.invalid/lumen/desktop-ci:<date>      # then pin the digest in .forgejo/workflows
FROM docker.io/library/archlinux:base-devel@sha256:fa2d4ce3310ddd90a4208e5168be8ad367da5129af1245f38fd2d803bcbe3239

# The image leaves out locale data; the tests run with de_DE.UTF-8, so glibc is reinstalled with it.
# at-spi2-core: the Atspi typelib; breeze-icons: the icon theme the desktop sets; Liberation: the PDF
# engine's metric-compatible substitutes, DejaVu its next fallback (also named by tests); nodejs: the
# runner's JavaScript actions; cargo-audit, npm: the dependency audit. The job runs as root (the runner copies the checkout in as root); the
# gate itself runs as the unprivileged user lumen.
RUN echo 'Server = https://archive.archlinux.org/repos/2026/11/17/$repo/os/$arch' > /etc/pacman.d/mirrorlist \
 && sed -i '/^NoExtract.*locale/d' /etc/pacman.conf \
 && pacman -Syyuu --noconfirm glibc \
      python python-pytest pyside6 qt6-webengine qt6-declarative qt6-svg qt6-imageformats qt6-translations \
      python-gobject gobject-introspection-runtime python-pillow python-numpy python-dbus python-markdown-it-py \
      dbus git openssl ffmpeg desktop-file-utils tesseract tesseract-data-deu tesseract-data-eng \
      at-spi2-core breeze-icons ttf-liberation ttf-dejavu rust rclone nodejs cargo-audit npm \
 && printf 'de_DE.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\n' > /etc/locale.gen && locale-gen \
 && pacman -Scc --noconfirm && rm -rf /var/lib/pacman/sync/* \
 && useradd -m -u 1000 lumen

ENV LANG=de_DE.UTF-8
