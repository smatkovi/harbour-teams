#!/usr/bin/env python3
"""Laesst die App selbst gegen ein privates Konto laufen -- ohne Oberflaeche.

Nicht die Probe, sondern `teams_api.py`: damit misst dieser Lauf genau den
Code, der spaeter im Paket steckt, samt `netz.py` als HTTP-Schicht.

    tools/privat-probelauf.py ZUSTAND

ZUSTAND ist die Datei, die `tools/anmeldeprobe.py` geschrieben hat. Sie
enthaelt lebende Token -- sie gehoert nicht in den Baum und wird hier nur
gelesen, nie kopiert.

Ausgegeben werden Zahlen und abgeschnittene Kennungen, keine Inhalte:
wessen Nachrichten das sind, hat in einem Protokoll nichts zu suchen.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import teams_api
from teams_api import TeamsAuth, TeamsClient

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)

z = json.load(open(sys.argv[1]))

print("HTTP-Schicht:", teams_api.requests.__name__)

auth = TeamsAuth("privat")
auth.refresh_token = z["refresh_token"]

# 1) Erneuern -- der Weg, den die App bei jedem Start geht.
print("\n1) Token erneuern")
if not auth.refresh_access_token():
    print("   FEHLER: refresh_access_token() hat nein gesagt")
    sys.exit(1)
print("   ok, access_token da")

# 2) Skypetoken und die Grundadressen
print("\n2) authz")
if not auth.get_teams_authorization():
    print("   FEHLER: get_teams_authorization() hat nein gesagt")
    sys.exit(1)
print("   Skypetoken:", (auth.skype_token or "")[:24], "...")
print("   Skype-Kennung:", auth.skype_id)
print("   chatsvc:", auth.chatsvc_base)
print("   AMS:", auth.ams_base)
print("   middleTier offen:", auth.hat_middle_tier)

client = TeamsClient(auth)

# 3) Die Gespraechsliste -- mit der view-Angabe, die die App schickt
print("\n3) Gespraechsliste (view wie in der App)")
gespraeche = client.get_conversations(page_size=20)
if not isinstance(gespraeche, list):
    print("   FEHLER: keine Liste:", str(gespraeche)[:200])
    sys.exit(1)
print(f"   {len(gespraeche)} Gespraeche")
for g in gespraeche:
    kennung = g.get("id", "?")
    print(f"   - {kennung[:34]:34} Art {kennung.split(':')[0]}")

# 4) Nachrichten im letzten Gespraech
if gespraeche:
    kennung = gespraeche[-1].get("id")
    print(f"\n4) Nachrichten in {kennung[:34]}")
    nachrichten = client.get_conversation_messages(kennung, page_size=10)
    if not isinstance(nachrichten, list):
        print("   FEHLER: keine Liste:", str(nachrichten)[:200])
        sys.exit(1)
    print(f"   {len(nachrichten)} Nachrichten")
    arten = {}
    for n in nachrichten:
        arten[n.get("messagetype", "?")] = arten.get(n.get("messagetype", "?"), 0) + 1
    print("   Arten:", arten)

# 5) Kontakte -- der Ersatz fuer middleTier
print("\n5) Kontakte (statt middleTier)")
namen = client.kontakte()
print(f"   {len(namen)} Kontakte mit Namen")
print("   Kennungsarten:", sorted({m.split(':')[0] for m in namen}))

# 6) Die Wege, die privat zu sein haben, muessen leise nein sagen
print("\n6) Riegel vor den middleTier-Wegen")
for name, wert in (("get_teams()", client.get_teams()),
                   ("get_team_channels('x')", client.get_team_channels("x")),
                   ("get_user_avatar('8:x')", client.get_user_avatar("8:x"))):
    leer = wert in ([], None)
    print(f"   {'ok    ' if leer else 'FEHLER'} {name} -> {wert!r}")

print("\nDurch.")
