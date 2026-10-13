#!/bin/sh
# Laedt jede QML-Seite ohne Fenster und meldet, was nicht laedt.
#
#   tools/qml-laden.sh [<qml-verzeichnis>]
#
# Silica-Seiten lassen sich unter QT_QPA_PLATFORM=minimal nicht erzeugen
# (Absturz), aber laden -- und schon das Laden findet Tippfehler und
# Eigenschaften, die es in der importierten QtQuick-Fassung nicht gibt
# ("Column.bottomPadding is not available in QtQuick 2.0"). Auf dem Geraet
# laufen lassen; der Quellbaum reicht, die Bauteile liegen daneben.
QML=$(cd "${1:-$(dirname "$0")/../qml}" && pwd)
TMP=$(mktemp /tmp/qml-laden.XXXXXX)
PROBE=$TMP.qml
trap 'rm -f "$TMP" "$PROBE"' EXIT
{
    echo 'import QtQuick 2.0'
    echo 'QtObject {'
    printf '    property var dateien: ['
    (cd "$QML" && find . -name '*.qml' | sed 's|^\./||' | sort) | sed 's/.*/"&",/' | tr -d '\n' | sed 's/,$//'
    echo ']'
    cat <<INNEN
    Component.onCompleted: {
        var wurzel = "file://$QML/";
        var schlecht = 0;
        for (var i = 0; i < dateien.length; i++) {
            var c = Qt.createComponent(wurzel + dateien[i], Component.PreferSynchronous);
            if (c.status === Component.Error) { schlecht++; console.log("FEHLER " + c.errorString()); }
            else if (c.status !== Component.Ready) { schlecht++; console.log("FEHLER " + dateien[i] + ": Status " + c.status); }
        }
        console.log(dateien.length + " QML-Dateien geladen, " + schlecht + " mit Fehler");
        Qt.quit();
    }
}
INNEN
} > "$PROBE"
QT_LOGGING_TO_CONSOLE=1 QT_QPA_PLATFORM=minimal qmlscene --quit "$PROBE" 2>&1 \
    | grep -v 'createPlatformOpenGLContext\|Suspicious DPI\|libselinux\|^$' \
    | sed 's/^\[D\] [^ ]* - //'
