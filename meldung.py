#!/usr/bin/env python3
"""Meldungen auf Sailfish -- mit Antwortzeile in der Meldung.

Was lipstick dazu braucht, ist nicht offensichtlich, und zwei Dinge daran
kosten sonst einen Abend:

* Die Argumente einer Fernaktion sind **kein Klartext**, sondern ein
  QDataStream-QVariant (Typ 10, UTF-16BE), base64 kodiert. `qvariant_b64`
  macht genau das.
* Erst `x-nemo-remote-action-type-<name> = "input"` macht aus dem Knopf
  eine Textzeile. Ohne `desktop_entry` sucht lipstick das Icon nach dem
  Prozessnamen und beschwert sich, dass der Dienst keinen Startereintrag
  hat.

Dieselbe Mechanik laeuft seit Monaten in harbour-briar; hier ist sie nach
Python uebersetzt, ohne Fremdpakete -- dbus-python ist auf Sailfish da
(python3-dbus), GLib ebenso.

Je Gespraech eine Meldung, nicht je Nachricht: fuenf Zeilen in einem
Gespraech sind ein Ereignis, keine fuenf. Dafuer wird die Kennung der
Meldung behalten und beim naechsten Mal ersetzt.
"""

import base64

import dbus

DIENST = "org.freedesktop.Notifications"
PFAD = "/org/freedesktop/Notifications"

# Wie die Meldung heisst und wonach lipstick sie gruppiert.
APP = "harbour-teams"
ICON = "harbour-teams"


def qvariant_b64(text):
    """Ein QString, wie nemos Meldungsmodul Aktionsargumente erwartet.

    QDataStream: 4 Byte Typ (10 = QVariant::String), 1 Byte "nicht null",
    4 Byte Laenge in Byte, dann UTF-16BE. Das Ganze base64.
    """
    einheiten = text.encode("utf-16-be")
    puffer = bytearray()
    puffer += (10).to_bytes(4, "big")      # QVariant::String
    puffer += b"\x00"                      # nicht null
    puffer += len(einheiten).to_bytes(4, "big")
    puffer += einheiten
    return base64.b64encode(bytes(puffer)).decode("ascii")


class Melder:
    """Haelt die Kennungen der offenen Meldungen, je Gespraech eine."""

    def __init__(self, dienstname, schnittstelle, gui_dienst=None, gui_schnittstelle=None):
        self.dienstname = dienstname
        self.schnittstelle = schnittstelle
        self.gui_dienst = gui_dienst
        self.gui_schnittstelle = gui_schnittstelle
        self.offen = {}
        self._bus = None

    @property
    def bus(self):
        if self._bus is None:
            self._bus = dbus.SessionBus()
        return self._bus

    def _schnittstelle(self):
        return dbus.Interface(self.bus.get_object(DIENST, PFAD), DIENST)

    def melden(self, schluessel, titel, text, argument, antwort_beschriftung="Antworten"):
        """Meldet eine neue Nachricht, oder ersetzt die bestehende Meldung.

        `argument` ist die Gespraechskennung, wie die Fernaktionen sie
        brauchen. `antwort_beschriftung` leer lassen heisst: keine
        Antwortzeile -- so soll die Meldung bei zugesperrter Oberflaeche
        aussehen, sie sagt dann nur, dass etwas kam.
        """
        kodiert = qvariant_b64(argument)
        antwort_aktion = (f"{self.dienstname} / {self.schnittstelle} "
                          f"Antworten {kodiert}")

        hinweise = {
            "category": "x-nemo.messaging.im",
            # Ohne das sucht lipstick das Icon nach dem Prozessnamen und
            # beschwert sich, dass der Dienst keinen Startereintrag hat.
            "desktop_entry": APP,
            "x-nemo-preview-summary": titel,
            "x-nemo-preview-body": text,
            "x-nemo-feedback": "chat_exists",
            "x-nemo-remote-action-reply": antwort_aktion,
            # Genau das macht aus dem Knopf eine Textzeile.
            "x-nemo-remote-action-type-reply": "input",
        }
        if self.gui_dienst:
            hinweise["x-nemo-remote-action-default"] = (
                f"{self.gui_dienst} / {self.gui_schnittstelle} openChat {kodiert}")

        aktionen = ["default", ""]
        if antwort_beschriftung:
            aktionen += ["reply", antwort_beschriftung]

        ersetzt = self.offen.get(schluessel, 0)
        try:
            kennung = self._schnittstelle().Notify(
                APP, dbus.UInt32(ersetzt), ICON, titel, text,
                dbus.Array(aktionen, signature="s"),
                dbus.Dictionary(hinweise, signature="sv"),
                dbus.Int32(-1))
            self.offen[schluessel] = int(kennung)
            return int(kennung)
        except dbus.DBusException as e:
            print(f"meldung: {e}")
            return 0

    def schliessen(self, schluessel):
        """Nimmt die Meldung weg, sobald das Gespraech gelesen ist."""
        kennung = self.offen.pop(schluessel, 0)
        if not kennung:
            return
        try:
            self._schnittstelle().CloseNotification(dbus.UInt32(kennung))
        except dbus.DBusException as e:
            print(f"meldung schliessen: {e}")


if __name__ == "__main__":
    import sys
    # Handprobe: eine Meldung mit Antwortzeile zeigen.
    m = Melder("harbour.teams.dienst", "harbour.teams.Dienst")
    kennung = m.melden("probe", "Teams-Probe",
                       sys.argv[1] if len(sys.argv) > 1 else "Antwortzeile da?",
                       "19:probe@thread.v2")
    print("Meldung", kennung, "-- qvariant_b64('x') =", qvariant_b64("x"))
