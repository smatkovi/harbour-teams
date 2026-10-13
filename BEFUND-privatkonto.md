# Befund: privates Konto (Skype) an Teams — gemessen 13.10.2026

Der Weg trägt. Anmeldung, Gesprächsliste und Nachrichten laufen; was nicht
läuft, läuft aus einem nachvollziehbaren Grund nicht. Alles unten ist
gemessen, nicht abgeschrieben. Kennungen und Pfade stammen aus
`purple-teams` (EionRobb), die Messung aus `tools/anmeldeprobe.py`.

## Zwei getrennte Welten

| | Arbeit/Schule (was die App heute macht) | privat (Skype-Konto) |
|---|---|---|
| Kennung | `04b07795-8ddb-461a-bbee-02f9e1bf7b46` (Azure CLI) | `8ec6bc83-69c8-4392-8f08-b3c986009232` |
| Tor | `/common/oauth2` (AAD v1, `resource=`) | `/consumers/oauth2/v2.0` (`scope=`) |
| Bereich | `https://api.spaces.skype.com` | `service::api.fl.spaces.skype.com::MBI_SSL openid profile offline_access` |
| Skypetoken | `teams.microsoft.com/api/authsvc/v1.0/authz` | `teams.live.com/api/auth/v1.0/authz/consumer` |
| Antwortform | `tokens.skypeToken` | `skypeToken.skypetoken` (klein) |

Zwei Fallen, beide bezahlt:

* `scope=https://api.spaces.skype.com/.default` wird abgewiesen —
  **`AADSTS70011: The scope … does not exist`**. Es muss der
  MBI_SSL-Dienstname sein.
* purple-teams übergibt beim `authz/consumer` das `id_token`. Das ist
  falsch, jedenfalls heute: **`id_token` → 401 `{"status":{"code":40110,
  "text":"Invalid access token."}}`**, `access_token` → 200.

## Was die Antwort liefert

`skypeToken`: `skypetoken`, `expiresIn` 86363 (also 24 h, nicht eine),
`skypeid`, `signinname`, `isBusinessTenant: False`.
`region` fehlt — aber `regionGtms` ist da und nennt alles:

```
chatServiceAfd    https://teams.live.com/api/chatsvc/consumer
chatService       https://msgapi.teams.live.com
middleTier        https://teams.live.com/api/mt
ams               https://us-api.asm.skype.com
groupsServiceV2   https://teams.live.com/api/groups
unifiedPresence   https://presence.teams.live.com
```

## Was läuft

| Weg | Kopf | Ergebnis |
|---|---|---|
| `{chatsvc}/v1/users/ME/conversations` | `Authentication: skypetoken=…` | **200**, Gespräche |
| `{chatsvc}/v1/users/ME/conversations/{id}/messages` | dito | **200**, Nachrichten mit `content`, `from`, `composetime`, `messagetype` |
| `contacts.skype.com/contacts/v2/users/SELF/contacts` | `X-Skypetoken: …` | **200**, Kontakte mit `mri` und `display_name` |

## Was nicht läuft, und warum

* **middleTier ist für private Konten zu.** `teams.live.com/api/mt/beta/users/ME`
  gibt 401 — mit dem Spaces-Token, mit einem frisch für
  `service::api.fl.teams.microsoft.com::MBI_SSL` geholten Token (das Azure
  anstandslos ausstellt), mit `Authentication: skypetoken=`, mit beidem
  zusammen, und auch unter `/api/mt/amer/`. Damit fallen alle Wege weg, die
  die App über middleTier geht: `fetchShortProfile`, `profilepicturev2`,
  `beta/users/searchV2`, `beta/teams/usergroups`, `beta/teams/{id}/channels`.
  **Ersatz für Namen und Bilder ist `contacts.skype.com`.**
* **Teams und Kanäle gibt es in einem privaten Konto nicht.** Das Gegenstück
  heißt Communities und liegt unter `groupsServiceV2`
  (`teams.live.com/api/groups`) — `…/v1/groups` gibt dort 404, der richtige
  Pfad ist noch zu finden. In der Oberfläche gehört der Reiter bei einem
  privaten Konto ausgeblendet, nicht leer gezeigt.
* **Graph fällt weg.** Die App holt `resource=https://graph.microsoft.com`
  über AAD v1 und sucht Benutzer per `/v1.0/users?$filter=…`. Ein
  Verzeichnis hat ein privates Konto nicht; Kontakte kommen aus
  `contacts.skype.com`.
* **SharePoint fällt weg.** `get_sharepoint_token` und die
  `_api/v2.0/shares/…`-Wege haben bei einem privaten Konto kein Gegenüber.
  Dateien liegen in AMS (`us-api.asm.skype.com`, nicht `eu-api…`).

## Was im Code hart verdrahtet ist und wandern muss

`teams_api.py` legt `chat_service` und `middle_tier` ab, **benutzt sie aber
kaum**: die Aufrufe bauen `https://teams.microsoft.com/api/chatsvc/{region}`
selbst zusammen (Zeilen 332, 360, 393, 409, 1143). Bei einem privaten Konto
ist `region` leer, und damit zeigt jeder dieser Aufrufe ins Nichts. Ebenso
hart: `eu-prod.asyncgw.teams.microsoft.com` (915) und
`eu-api.asm.skype.com` (1054/1056) — beide gehören aus `regionGtms`.
