#!/bin/sh
# Baut teams als architekturunabhaengiges .deb fuer Harmattan.
#
#   meego/build-deb.sh            # Version aus control.in
#   meego/build-deb.sh 0.9.23
#
# Das Paket 0.9.22 wurde ohne Quellbaum gebaut; das hier haelt den Ablauf
# fest, damit eine neue Fassung nicht wieder zusammengesucht werden muss.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
VERSION=${1:-$(sed -n 's/^Version: *//p' control.in | head -1)}
[ "$VERSION" = "@VERSION@" ] && { echo "Version angeben" >&2; exit 1; }
STAGE=$HERE/stage

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/teams/qml" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/80x80/apps"

cp teams teams_api.py "$STAGE/opt/teams/"
chmod 755 "$STAGE/opt/teams/teams"
chmod 644 "$STAGE/opt/teams/teams_api.py"
cp qml/main.qml "$STAGE/opt/teams/qml/"
cp teams.desktop "$STAGE/usr/share/applications/"
# Das Icon traegt die exakte Squircle-Silhouette der Standard-Apps
# (~/ps/meego-icon-tool). Der Pfad heisst 80x80, das Bild ist 86x86 --
# so lag es im Paket 0.9.22, und Harmattan skaliert es ohnehin.
cp icons/80x80/teams.png "$STAGE/usr/share/icons/hicolor/80x80/apps/"

# control samt Icon fuer den Programm-Manager. Die base64-Zeilen brauchen je
# ein fuehrendes Leerzeichen, sonst zeigt der Manager kein Bild.
VERSION="$VERSION" python3 - <<'PY'
import base64, os, textwrap
vorlage = open("control.in").read().rstrip("\n")
b64 = base64.b64encode(open("icons/64x64/teams.png", "rb").read()).decode("ascii")
icon = "\n".join(" " + z for z in textwrap.wrap(b64, 76))
text = vorlage.replace("@VERSION@", os.environ["VERSION"]).replace("@ICON@", icon)
open("stage/DEBIAN/control", "w").write(text + "\n")
PY

OUT="$HERE/teams_${VERSION}_all.deb"
python3 mkdeb.py "$STAGE" "$OUT"
echo "== $OUT"
