#!/usr/bin/env bash
set -euo pipefail

# This is a package builder, not an installer. All writes are confined to the
# build directory and temporary staging tree. No maintainer scripts or autostart
# changes are added to either package.
component=${1:-native}
case "$component" in native|kde) ;; *) printf 'Usage: %s [native|kde]\n' "$0" >&2; exit 2 ;; esac
linux_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
repo_dir=$(dirname -- "$linux_dir")
version=${POMOCLI_VERSION:-$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$repo_dir/pyproject.toml" | head -n 1)}
architecture=$(dpkg --print-architecture)
jobs=${JOBS:-1}
output_dir=${POMOCLI_PACKAGE_DIR:-"$linux_dir/build/packages"}
for command in dpkg-deb dpkg-shlibdeps make; do
    command -v "$command" >/dev/null || { printf 'Missing build command: %s\n' "$command" >&2; exit 1; }
done
dpkg --validate-version "$version"
mkdir -p -- "$output_dir"
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/pomocli-deb.XXXXXXXX")
trap 'rm -rf -- "$work_dir"' EXIT
stage="$work_dir/stage"
mkdir -p -- "$stage/DEBIAN" "$work_dir/debian"

if [[ "$component" == native ]]; then
    package=pomocli-desktop
    description='Lightweight Linux desktop companion for PomoCLI'
    make -C "$linux_dir" install-native PREFIX=/usr DESTDIR="$stage" JOBS="$jobs" DIALOGS="${DIALOGS:-1}"
    executables=(-e "$stage/usr/bin/pomo-tray")
    if [[ -f "$stage/usr/bin/pomo-dialog" ]]; then
        executables+=(-e "$stage/usr/bin/pomo-dialog")
    fi
    extra_depends=''
else
    package=pomocli-plasma-widget
    description='Plasma 6 panel timer for PomoCLI'
    make -C "$linux_dir" install-widget PREFIX=/usr DESTDIR="$stage" JOBS="$jobs" BUILD_DIR="$linux_dir/build/deb-kde"
    executables=(-e "$stage/usr/share/plasma/plasmoids/org.pomocli.timer/contents/ui/bridge/libpomoclidesktopplugin.so")
    extra_depends=", pomocli-desktop (= $version), plasma-workspace (>= 4:6.0), qml6-module-org-kde-kirigami, qml6-module-org-kde-ksvg, qml6-module-qtquick-controls, qml6-module-qtquick-layouts"
fi

# dpkg-shlibdeps discovers distro-specific names (including t64 transitions)
# and required library symbol versions from the binaries that were just built.
cat > "$work_dir/debian/control" <<EOF
Source: $package
Section: utils
Priority: optional
Maintainer: PomoCLI contributors <noreply@pomocli.invalid>
Standards-Version: 4.7.0

Package: $package
Architecture: any
Description: $description
EOF
dependencies=$(cd -- "$work_dir" && dpkg-shlibdeps -O "${executables[@]}")
dependencies=${dependencies#shlibs:Depends=}
cat > "$stage/DEBIAN/control" <<EOF
Package: $package
Version: $version
Section: utils
Priority: optional
Architecture: $architecture
Maintainer: PomoCLI contributors <noreply@pomocli.invalid>
Depends: $dependencies$extra_depends
Description: $description
 Uses the existing Python PomoCLI installation without bundling a Python runtime.
 Install PomoCLI separately with uv tool install or pipx. Login autostart is opt-in.
EOF
find "$stage" -type d -exec chmod 755 {} +
chmod 644 "$stage/DEBIAN/control"
dpkg-deb --build --root-owner-group "$stage" "$output_dir/${package}_${version}_${architecture}.deb"
