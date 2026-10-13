#!/usr/bin/env python3
"""Prueft, dass der Arbeitsweg sich nicht geaendert hat -- und der private stimmt.

Der Grund fuer diesen Test: es gibt kein Arbeitskonto mehr, an dem man
nachsehen koennte. Jede Adresse, die vorher als feste Zeichenkette im Code
stand, muss im Arbeitsmodus Zeichen fuer Zeichen wieder herauskommen. Das
laesst sich ohne Netz und ohne Konto pruefen, und genau das tut der Test.

    tools/wege-test.py

Keine Fremdpakete, kein Netz: die Antwort des Anmeldedienstes wird
eingespielt, nicht geholt. Die eingespielten Formen sind die echten --
die private ist am 13.10.2026 gemessen (BEFUND-privatkonto.md), die
geschaeftliche ist die, auf die der alte Code gebaut hat.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import teams_api
from teams_api import TeamsAuth

# ---------------------------------------------------------------- Attrappe

class Antwort:
    def __init__(self, nutzlast, status=200):
        self.status_code = status
        self._nutzlast = nutzlast
        self.text = json.dumps(nutzlast)

    def json(self):
        return self._nutzlast

    def raise_for_status(self):
        pass


class Netz:
    """Merkt sich, wohin gerufen wurde, und antwortet mit Vorgegebenem."""

    def __init__(self, antwort):
        self.antwort = antwort
        self.rufe = []

    def post(self, url, **k):
        self.rufe.append(("POST", url, k))
        return Antwort(self.antwort)

    def get(self, url, **k):
        self.rufe.append(("GET", url, k))
        return Antwort(self.antwort)


# Die Antwort, die ein Arbeitskonto schickt: Token unter "tokens", mit
# region und regionGtms.
AUTHZ_ARBEIT = {
    "tokens": {"skypeToken": "ST-arbeit", "expiresIn": 3600},
    "region": "emea",
    "regionGtms": {
        "chatService": "https://emea.ng.msg.teams.microsoft.com",
        "middleTier": "https://teams.microsoft.com/api/mt/emea",
        "ams": "https://eu-api.asm.skype.com",
    },
}

# Die Antwort eines privaten Kontos, gemessen: Token unter "skypeToken",
# das Feld klein geschrieben, *kein* region, AMS in den USA.
AUTHZ_PRIVAT = {
    "skypeToken": {
        "skypetoken": "ST-privat",
        "expiresIn": "86363",
        "skypeid": "grinsgesicht",
        "isBusinessTenant": "False",
    },
    "regionGtms": {
        "chatServiceAfd": "https://teams.live.com/api/chatsvc/consumer",
        "chatService": "https://msgapi.teams.live.com",
        "middleTier": "https://teams.live.com/api/mt",
        "ams": "https://us-api.asm.skype.com",
    },
}

fehler = []


def gleich(was, ist, soll):
    if ist != soll:
        fehler.append(f"{was}\n      ist:  {ist!r}\n      soll: {soll!r}")
        print(f"  FEHLER {was}")
    else:
        print(f"  ok     {was}")


def anmelden(modus, authz):
    """Einen angemeldeten Zustand herstellen, ohne Netz."""
    echt = teams_api.requests
    netz = Netz(authz)
    teams_api.requests = netz
    try:
        auth = TeamsAuth(modus)
        auth.access_token = "AT"
        assert auth.get_teams_authorization(), "authz wurde nicht angenommen"
    finally:
        teams_api.requests = echt
    return auth, netz


# ------------------------------------------------------- Arbeit: unveraendert

print("Arbeitsweg -- muss genau sein wie vor der Aenderung:")
auth, netz = anmelden("arbeit", AUTHZ_ARBEIT)

gleich("authz-Adresse", netz.rufe[0][1],
       "https://teams.microsoft.com/api/authsvc/v1.0/authz")
gleich("Skypetoken gelesen", auth.skype_token, "ST-arbeit")
gleich("region", auth.region, "emea")
gleich("chatsvc-Basis", auth.chatsvc_base,
       "https://teams.microsoft.com/api/chatsvc/emea")
gleich("AMS", auth.ams_base, "https://eu-api.asm.skype.com")
gleich("asyncgw", auth.asyncgw_base,
       "https://eu-prod.asyncgw.teams.microsoft.com")
gleich("chat_service wie bisher", auth.chat_service,
       "https://emea.ng.msg.teams.microsoft.com")
gleich("middle_tier wie bisher", auth.middle_tier,
       "https://teams.microsoft.com/api/mt/emea")
gleich("middleTier offen", auth.hat_middle_tier, True)

weg = auth.weg
gleich("Kennung", weg["client_id"], "04b07795-8ddb-461a-bbee-02f9e1bf7b46")
gleich("devicecode-Adresse", weg["devicecode"],
       "https://login.microsoftonline.com/common/oauth2/devicecode")
gleich("token-Adresse", weg["token"],
       "https://login.microsoftonline.com/common/oauth2/token")
gleich("Bereichsfeld", weg["bereich"], ("resource", "https://api.spaces.skype.com"))
gleich("Codefeld beim Abholen", weg["codefeld"], "code")

# Die fuenf Aufrufe, die vorher die Adresse selbst zusammenbauten.
gleich("Gespraechsliste", f"{auth.chatsvc_base}/v1/users/ME/conversations",
       "https://teams.microsoft.com/api/chatsvc/emea/v1/users/ME/conversations")
gleich("Nachrichten", f"{auth.chatsvc_base}/v1/users/ME/conversations/X/messages",
       "https://teams.microsoft.com/api/chatsvc/emea/v1/users/ME/conversations/X/messages")
gleich("AMS-Vorschau", f"{auth.ams_base}/v1/objects/Y/views/imgo",
       "https://eu-api.asm.skype.com/v1/objects/Y/views/imgo")

# ------------------------------------------------------------- Privat: neu

print("\nPrivater Weg -- gemessen am 13.10.2026:")
auth2, netz2 = anmelden("privat", AUTHZ_PRIVAT)

gleich("authz-Adresse", netz2.rufe[0][1],
       "https://teams.live.com/api/auth/v1.0/authz/consumer")
gleich("Accept-Kopf gesetzt", netz2.rufe[0][2]["headers"].get("Accept"),
       "application/json; ver=1.0")
gleich("Skypetoken (klein geschrieben) gelesen", auth2.skype_token, "ST-privat")
gleich("Skype-Kennung", auth2.skype_id, "grinsgesicht")
gleich("chatsvc-Basis", auth2.chatsvc_base,
       "https://teams.live.com/api/chatsvc/consumer")
gleich("AMS", auth2.ams_base, "https://us-api.asm.skype.com")
gleich("asyncgw", auth2.asyncgw_base,
       "https://us-prod.asyncgw.teams.microsoft.com")
gleich("middleTier zu", auth2.hat_middle_tier, False)

weg2 = auth2.weg
gleich("Kennung", weg2["client_id"], "8ec6bc83-69c8-4392-8f08-b3c986009232")
gleich("devicecode-Adresse", weg2["devicecode"],
       "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode")
gleich("Bereich ist der MBI_SSL-Dienstname", weg2["bereich"][1],
       "service::api.fl.spaces.skype.com::MBI_SSL openid profile offline_access")
gleich("Codefeld beim Abholen", weg2["codefeld"], "device_code")

# ---------------------------------------------- Altes Lager ohne Modusangabe

print("\nAltes Token-Lager (kennt kein 'modus') -- muss Arbeit bleiben:")
auth3 = TeamsAuth("privat")          # absichtlich falsch vorbelegt
alt = {"access_token": "AT", "refresh_token": "RT", "skype_token": "ST",
       "region": "emea", "chat_service": "https://emea.ng.msg.teams.microsoft.com",
       "middle_tier": "https://teams.microsoft.com/api/mt/emea"}
# load_tokens einspielen, ohne Dateien anzufassen
for feld in ("access_token", "refresh_token", "skype_token"):
    setattr(auth3, feld, alt[feld])
auth3.region = alt["region"]
auth3.modus = "arbeit"               # genau das macht load_tokens bei fehlendem Feld
auth3._wege_setzen({})
gleich("chatsvc-Basis aus dem Nichts abgeleitet", auth3.chatsvc_base,
       "https://teams.microsoft.com/api/chatsvc/emea")
gleich("AMS", auth3.ams_base, "https://eu-api.asm.skype.com")

# ------------------------------------------------------------------ Ergebnis

print()
if fehler:
    print(f"{len(fehler)} Abweichung(en):")
    for f in fehler:
        print("  - " + f)
    sys.exit(1)
print("Alle Wege stimmen.")
