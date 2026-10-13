#!/usr/bin/env python3
"""teamsd -- der Dienst, der meldet, wenn eine Nachricht kommt.

Warum ueberhaupt ein Dienst: lipstick ruft die Antwortmethode auf einem
**laufenden** D-Bus-Namen auf, und die App laeuft nicht, wenn die Meldung
erscheint. Ohne bleibenden Prozess gibt es keine Antwortzeile.

    teamsd --anmelden [arbeit|privat]   einmalig: Geraetecode, Token holen
    teamsd                              laufen
    teamsd --probe                      eine Meldung zeigen und beenden
    teamsd --laut                       auch eigene Nachrichten melden

--laut ist zum Pruefen: normalerweise fallen eigene Nachrichten weg, denn
der Dienst schickt sie an alle Endpunkte des Kontos und eine Meldung
ueber die eigene Zeile waere Unsinn. Mit nur einem Konto in der Hand
laesst sich die Kette aber sonst nicht ganz durchmessen.

**Eigene Anmeldung, eigene Token.** Der Dienst laeuft ausserhalb von
Sailjail und kommt an den Schluesselbund der App nicht heran. Er meldet
sich deshalb selbst an und fuehrt seine Token in einer eigenen Datei mit
0600. Das ist nicht nur der kuerzeste Weg, sondern auch der richtige:
zwei Prozesse, die denselben rotierenden Refresh-Token erneuern, melden
sich gegenseitig ab.

Auf dem Bus:

    harbour.teams.dienst  /  harbour.teams.Dienst
        Antworten(faden, text) -> bool      ruft lipstick bei der Antwort
        Gelesen(faden)                      Meldung wegnehmen
        Zustand() -> dict                   fuer die Fehlersuche
"""

import json
import os
import stat
import sys
import threading
import time
import uuid

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

HIER = os.path.dirname(os.path.abspath(__file__))
for pfad in (HIER, "/usr/share/harbour-teams"):
    if pfad not in sys.path and os.path.isdir(pfad):
        sys.path.insert(0, pfad)

from teams_api import TeamsAuth, TeamsClient          # noqa: E402
from trouter import Trouter, nachricht_aus            # noqa: E402
import meldung                                        # noqa: E402

DIENSTNAME = "harbour.teams.dienst"
SCHNITTSTELLE = "harbour.teams.Dienst"
# Die App darf unter Sailjail nur ihren eigenen Namen besitzen; so heisst er.
GUI_DIENST = "harbour-teams.harbour-teams"
GUI_SCHNITTSTELLE = "harbour.teams.Gui"

LAGER = os.path.expanduser("~/.local/share/harbour-teams-dienst")
TOKENDATEI = os.path.join(LAGER, "tokens.json")


def sage(*teile):
    print(time.strftime("%H:%M:%S"), *teile, flush=True)


# --------------------------------------------------------------- Token

def token_speichern(auth):
    os.makedirs(LAGER, exist_ok=True)
    zeitweise = TOKENDATEI + ".neu"
    with open(zeitweise, "w") as f:
        json.dump({
            "modus": auth.modus,
            "refresh_token": auth.refresh_token,
            "skype_id": auth.skype_id,
            "epid": endpunkt_kennung(),
        }, f)
    os.chmod(zeitweise, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(zeitweise, TOKENDATEI)


_EPID = None


def endpunkt_kennung():
    """Die bleibende Endpunktkennung dieses Geraets.

    Sie gehoert nicht zur Sitzung, sondern zum Geraet: der Registrar
    schluesselt die Zustellwege danach. Mit einer neuen je Verbindung
    sammeln sich tote Eintraege, und der Dienst liefert an einen davon.
    """
    global _EPID
    if _EPID:
        return _EPID
    lager = token_laden() or {}
    _EPID = lager.get("epid") or str(uuid.uuid4())
    return _EPID


def token_laden():
    try:
        with open(TOKENDATEI) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def anmelden(modus):
    """Geraetecode-Anmeldung, einmalig. Gibt True bei Erfolg."""
    auth = TeamsAuth(modus)
    antwort = auth.start_device_code_flow()
    print()
    print("  Seite oeffnen:", antwort.get("verification_url"))
    print("  Code eingeben:", antwort.get("user_code"))
    print()
    print("  (warte, bis die Anmeldung durch ist)")
    if not auth.poll_for_token(antwort["device_code"]):
        print("Anmeldung nicht zustande gekommen")
        return False
    if not auth.get_teams_authorization():
        print("Teams-Freischaltung nicht zustande gekommen")
        return False
    token_speichern(auth)
    print("angemeldet als", auth.skype_id, "-- Token in", TOKENDATEI)
    return True


# --------------------------------------------------------------- Dienst

class Dienst(dbus.service.Object):
    """Was lipstick und die App vom Dienst wollen koennen."""

    def __init__(self, bus_name, kern):
        super().__init__(bus_name, "/")
        self.kern = kern

    @dbus.service.method(SCHNITTSTELLE, in_signature="ss", out_signature="b")
    def Antworten(self, faden, text):
        return self.kern.antworten(str(faden), str(text))

    @dbus.service.method(SCHNITTSTELLE, in_signature="s")
    def Gelesen(self, faden):
        self.kern.gelesen(str(faden))

    @dbus.service.method(SCHNITTSTELLE, out_signature="a{sv}")
    def Zustand(self):
        return self.kern.zustand()


class Kern:
    """Anmeldung halten, Trouter hoeren, melden, antworten."""

    def __init__(self, laut=False):
        self.laut = laut
        self.auth = None
        self.client = None
        self.melder = meldung.Melder(DIENSTNAME, SCHNITTSTELLE,
                                     GUI_DIENST, GUI_SCHNITTSTELLE)
        self.namen = {}            # faden -> Anzeigename
        self.laeuft = True
        self.verbunden = False
        self.seit = time.time()
        self.gemeldet = 0
        self.gesendet = 0
        self._schloss = threading.Lock()

    # ---------------------------------------------------------- Anmeldung

    def anmeldung_herstellen(self):
        """Token laden, erneuern, freischalten. Bei Misserfolg False."""
        lager = token_laden()
        if not lager or not lager.get("refresh_token"):
            sage("kein Token -- erst 'teamsd --anmelden' laufen lassen")
            return False
        auth = TeamsAuth(lager.get("modus", "privat"))
        auth.refresh_token = lager["refresh_token"]
        if not auth.refresh_access_token():
            sage("Erneuern gescheitert -- Anmeldung noetig")
            return False
        if not auth.get_teams_authorization():
            sage("Freischaltung gescheitert")
            return False
        with self._schloss:
            self.auth = auth
            self.client = TeamsClient(auth)
        token_speichern(auth)          # der Refresh-Token rotiert
        sage(f"angemeldet als {auth.skype_id} ({auth.modus}), chatsvc {auth.chatsvc_base}")
        return True

    @property
    def eigene_kennung(self):
        return f"8:{self.auth.skype_id}" if self.auth and self.auth.skype_id else None

    # ------------------------------------------------------------- Namen

    def name_fuer(self, faden, absender, mitgeschickt):
        """Was in der Ueberschrift der Meldung stehen soll.

        Reihenfolge: was das Ereignis selbst mitbringt, dann der Name des
        Gespraechs, dann der Kontakt, dann die nackte Kennung. Lieber eine
        Kennung als "Unbekannt" -- sie sagt mehr.
        """
        if mitgeschickt:
            return mitgeschickt
        if faden in self.namen:
            return self.namen[faden]
        name = ""
        try:
            name = (self.client.kontakte() or {}).get(absender, "")
        except Exception:
            pass
        if not name:
            name = absender or faden
        self.namen[faden] = name
        return name

    # ---------------------------------------------------------- Melden

    def auf_nachricht(self, faden, absender, mitgeschickt, text):
        titel = self.name_fuer(faden, absender, mitgeschickt)
        # Eine Meldung je Gespraech: fuenf Zeilen sind ein Ereignis.
        self.melder.melden(faden, titel, text, faden)
        self.gemeldet += 1
        sage(f"gemeldet: {titel} ({len(text)} Zeichen) in …{faden[-20:]}")

    # --------------------------------------------------------- Antworten

    def antworten(self, faden, text):
        if not text.strip():
            return False
        with self._schloss:
            client = self.client
        if client is None:
            sage("Antwort ohne Anmeldung verworfen")
            return False
        try:
            gut = client.send_message(faden, text)
        except Exception as e:
            sage(f"Antwort gescheitert: {e}")
            gut = False
        if gut:
            self.gesendet += 1
            # Beantwortet heisst gelesen: Meldung weg.
            self.melder.schliessen(faden)
            sage(f"geantwortet in …{faden[-20:]}")
        else:
            sage(f"Antwort nicht angekommen in …{faden[-20:]}")
        return bool(gut)

    def gelesen(self, faden):
        self.melder.schliessen(faden)

    def zustand(self):
        return dbus.Dictionary({
            "angemeldet": dbus.Boolean(self.auth is not None),
            "verbunden": dbus.Boolean(self.verbunden),
            "modus": dbus.String(self.auth.modus if self.auth else ""),
            "kennung": dbus.String(self.eigene_kennung or ""),
            "gemeldet": dbus.Int32(self.gemeldet),
            "gesendet": dbus.Int32(self.gesendet),
            "laeuft_seit": dbus.Int32(int(time.time() - self.seit)),
        }, signature="sv")

    # ----------------------------------------------------------- Schleife

    def schleife(self):
        """Hoert Trouter, und baut die Sitzung wieder auf, wenn sie abreisst.

        Der Skypetoken gilt 24 h, der Zugangstoken eine Stunde; die
        Sitzung selbst hat ihre eigene Lebensdauer. Statt das einzeln
        auszurechnen wird bei jedem Abriss neu angemeldet -- das kostet
        zwei Aufrufe und spart eine Fehlerquelle.
        """
        wartezeit = 5
        while self.laeuft:
            if not self.anmeldung_herstellen():
                time.sleep(min(300, wartezeit))
                wartezeit = min(300, wartezeit * 2)
                continue
            tr = Trouter(self.auth, melder=sage, epid=endpunkt_kennung())
            if not tr.verbinden():
                self.verbunden = False
                time.sleep(min(300, wartezeit))
                wartezeit = min(300, wartezeit * 2)
                continue
            self.verbunden = True
            wartezeit = 5
            try:
                for ereignis in tr.lies():
                    if not self.laeuft:
                        break
                    n = nachricht_aus(ereignis,
                                      None if self.laut else self.eigene_kennung)
                    if n:
                        self.auf_nachricht(*n)
            except Exception as e:
                sage(f"Schleife gestolpert: {e}")
            self.verbunden = False
            sage("Sitzung zu Ende -- neu aufbauen")
            time.sleep(2)


def main():
    rest = sys.argv[1:]
    if rest and rest[0] == "--anmelden":
        modus = rest[1] if len(rest) > 1 else "privat"
        return 0 if anmelden(modus) else 1

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    kern = Kern(laut="--laut" in rest)
    if kern.laut:
        sage("--laut: eigene Nachrichten werden mitgemeldet")

    if rest and rest[0] == "--probe":
        kern.melder.melden("probe", "Teams", "Probemeldung vom Dienst",
                           "19:probe@thread.v2")
        sage("Probemeldung abgesetzt")
        return 0

    try:
        bus_name = dbus.service.BusName(DIENSTNAME, dbus.SessionBus(),
                                        do_not_queue=True)
    except dbus.exceptions.NameExistsException:
        sage(f"{DIENSTNAME} ist schon belegt -- laeuft der Dienst zweimal?")
        return 1
    Dienst(bus_name, kern)
    sage(f"auf dem Bus als {DIENSTNAME}")

    faden = threading.Thread(target=kern.schleife, daemon=True)
    faden.start()

    schleife = GLib.MainLoop()
    try:
        schleife.run()
    except KeyboardInterrupt:
        kern.laeuft = False
    return 0


if __name__ == "__main__":
    sys.exit(main())
