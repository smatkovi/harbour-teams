Name:       harbour-teams
Version:    0.1.0
Release:    73
Summary:    Microsoft Teams client for Sailfish OS
License:    MIT
Group:      Applications/Communications
BuildArch:  noarch

%define __provides_exclude_from ^%{_datadir}/.*$
%define __requires_exclude ^.*$
%define debug_package %{nil}
%define _build_id_links none
%define __strip /bin/true
# Ohne das laeuft brp-strip ueber das Paket und bricht ab: in einem noarch-
# Paket gibt es nichts zu strippen, und busybox' xargs stolpert ueber die
# leere Eingabe. Nachgemessen, nicht vorsorglich abgeschrieben.
%define __spec_install_post %{nil}

# Silica zeichnet die Oberflaeche.
Requires:   sailfishsilica-qt5
# Stellt /usr/bin/sailfish-qml bereit, also genau das Programm aus der
# Exec-Zeile der .desktop-Datei. Auf offiziell unterstuetzten Geraeten ist es
# immer da, auf einem frisch geflashten Community-Port nicht zwingend.
Requires:   libsailfishapp-launcher
# Die ganze Anwendungslogik liegt in Python und wird per PyOtherSide
# aufgerufen (teams_bridge.py). Ohne das Modul laedt harbour-teams.qml nicht
# und die App reagiert auf das Antippen mit gar nichts.
Requires:   pyotherside-qml-plugin-python3-qt5
# Nemo.Notifications: bisher nur das Fehlerbanner beim Hochladen.
Requires:   nemo-qml-plugin-notifications-qt5
# Sailfish.Pickers: der Dateiwaehler fuer Anhaenge.
Requires:   sailfish-components-pickers-qt5

%description
Unofficial Microsoft Teams client for Sailfish OS.
View and send messages in Teams chats and channels.

Features:
- Device code authentication
- View chats and teams/channels
- Send and receive messages
- File attachments (view/download)
- Image upload support
- User avatars

%install
rm -rf %{buildroot}

mkdir -p %{buildroot}%{_datadir}/%{name}
install -m 644 %{_sourcedir}/teams_api.py       %{buildroot}%{_datadir}/%{name}/
install -m 644 %{_sourcedir}/teams_bridge.py    %{buildroot}%{_datadir}/%{name}/
install -m 644 %{_sourcedir}/sailfish_secrets.py %{buildroot}%{_datadir}/%{name}/

mkdir -p %{buildroot}%{_datadir}/%{name}/qml/pages %{buildroot}%{_datadir}/%{name}/qml/cover
install -m 644 %{_sourcedir}/qml/harbour-teams.qml   %{buildroot}%{_datadir}/%{name}/qml/
install -m 644 %{_sourcedir}/qml/cover/CoverPage.qml %{buildroot}%{_datadir}/%{name}/qml/cover/
install -m 644 %{_sourcedir}/qml/pages/*.qml         %{buildroot}%{_datadir}/%{name}/qml/pages/

# Der Starter wechselt erst ins Datenverzeichnis: teams_bridge.py importiert
# teams_api.py als Nachbarmodul, und PyOtherSide sucht es im Arbeitsordner.
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/%{name} <<'EOF'
#!/bin/sh
cd /usr/share/harbour-teams
exec sailfish-qml harbour-teams
EOF
chmod 755 %{buildroot}%{_bindir}/%{name}

mkdir -p %{buildroot}%{_datadir}/applications
install -m 644 %{_sourcedir}/harbour-teams.desktop %{buildroot}%{_datadir}/applications/

for s in 86 108 128 172 256; do
    mkdir -p %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps
    install -m 644 %{_sourcedir}/icons/${s}x${s}/%{name}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps/
done

%files
%defattr(-,root,root,-)
%{_bindir}/%{name}
%{_datadir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png
