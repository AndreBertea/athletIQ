#!/usr/bin/env python3
"""garmin_relay.py — Relais Garmin maison.

Pourquoi ce worker existe
-------------------------
Le login Garmin de l'app (reimplementation de garth dans les Edge Functions)
echoue en HTTP 429 : l'oauth-service de Garmin throttle l'IP datacenter de
Supabase. Ce worker tourne sur une machine a IP RESIDENTIELLE (ton Mac H24) et
fait le login a la place de l'Edge. Garmin ne throttle pas une IP residentielle.

Comment ca marche
-----------------
- Aucune ouverture de port : le worker fait uniquement des appels SORTANTS vers
  Supabase (polling). Il fonctionne donc derriere ta box, sans IP fixe ni tunnel.
- L'Edge `garmin-login` depose une demande dans la table `garmin_relay_jobs`
  (identifiants chiffres AES-GCM via ENCRYPTION_KEY) et cree un `sync_jobs` suivi
  par la PWA.
- Ce worker recupere la demande, fait `garth` login depuis ton IP, gere le MFA via
  un aller-retour, chiffre le token (format identique a crypto.ts cote Edge) et
  l'ecrit dans `external_auth_tokens`. La PWA voit le `sync_jobs` passer a
  "succeeded".
- Une boucle separee rafraichit les tokens AVANT expiration, pour que la sync cote
  Edge n'ait jamais a appeler l'oauth-service (qui re-429erait).

Dependances : voir requirements.txt (garth, requests, cryptography).
Config : voir .env.example (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ENCRYPTION_KEY).
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

try:
    import requests
    import garth
    from garth import sso
    from garth.auth_tokens import OAuth1Token, OAuth2Token
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError as exc:  # pragma: no cover
    sys.exit(f"Dependance manquante ({exc}). Fais : pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
POLL_INTERVAL = float(os.environ.get("RELAY_POLL_INTERVAL", "3"))
REFRESH_INTERVAL = float(os.environ.get("RELAY_REFRESH_INTERVAL", "300"))  # 5 min
REFRESH_MARGIN_SECONDS = int(os.environ.get("RELAY_REFRESH_MARGIN", "1800"))  # 30 min

if not (SUPABASE_URL and SERVICE_ROLE_KEY and ENCRYPTION_KEY):
    sys.exit(
        "Config manquante. Renseigne SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY et "
        "ENCRYPTION_KEY (cf. .env.example)."
    )

REST = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

# Sessions garth en attente de code MFA : { relay_job_id: client_state }.
# On les garde en memoire car client_state contient l'objet client garth
# (cookies + CSRF) necessaire a resume_login. Si le worker redemarre pendant une
# attente MFA, le job concerne est marque en echec (l'athlete relance).
PENDING_MFA: dict[str, dict] = {}


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Chiffrement — identique a supabase/functions/_shared/crypto.ts
#   cle = SHA-256(ENCRYPTION_KEY) ; AES-GCM ; sortie = base64(iv[12] || ct||tag)
# ---------------------------------------------------------------------------
def _aes_key() -> bytes:
    return hashlib.sha256(ENCRYPTION_KEY.encode("utf-8")).digest()


def encrypt_secret(value) -> str:
    iv = os.urandom(12)
    plaintext = json.dumps(value, separators=(",", ":")).encode("utf-8")
    ct = AESGCM(_aes_key()).encrypt(iv, plaintext, None)  # ct inclut le tag (16o)
    return base64.b64encode(iv + ct).decode("ascii")


def decrypt_secret(blob: str):
    raw = base64.b64decode(blob)
    iv, payload = raw[:12], raw[12:]
    plaintext = AESGCM(_aes_key()).decrypt(iv, payload, None)
    return json.loads(plaintext.decode("utf-8"))


# ---------------------------------------------------------------------------
# Helpers PostgREST (service-role)
# ---------------------------------------------------------------------------
def sb_get(table: str, params: dict) -> list[dict]:
    resp = requests.get(f"{REST}/{table}", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def sb_patch(table: str, params: dict, payload: dict, *, want_return=False) -> list[dict]:
    headers = dict(HEADERS)
    headers["Prefer"] = "return=representation" if want_return else "return=minimal"
    resp = requests.patch(
        f"{REST}/{table}", headers=headers, params=params, json=payload, timeout=30
    )
    resp.raise_for_status()
    return resp.json() if want_return else []


def sb_upsert(table: str, payload: dict, on_conflict: str) -> None:
    headers = dict(HEADERS)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    resp = requests.post(
        f"{REST}/{table}?on_conflict={on_conflict}",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def sb_insert_ignore(table: str, rows: list[dict], on_conflict: str) -> None:
    if not rows:
        return
    headers = dict(HEADERS)
    headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
    resp = requests.post(
        f"{REST}/{table}?on_conflict={on_conflict}",
        headers=headers,
        json=rows,
        timeout=30,
    )
    resp.raise_for_status()


def set_sync_job(sync_job_id: str | None, **fields) -> None:
    if not sync_job_id:
        return
    try:
        sb_patch("sync_jobs", {"id": f"eq.{sync_job_id}"}, fields)
    except Exception as exc:  # ne jamais planter le worker pour un suivi
        log(f"  ! maj sync_jobs {sync_job_id} echouee: {exc}")


# ---------------------------------------------------------------------------
# Conversion tokens garth -> forme attendue par garmin.ts (GarminToken)
# ---------------------------------------------------------------------------
def _jsonable(value):
    return value.isoformat() if isinstance(value, datetime) else value


def token_to_dict(o1: OAuth1Token, o2: OAuth2Token) -> dict:
    d1 = {k: _jsonable(v) for k, v in dataclasses.asdict(o1).items()}
    d2 = {k: _jsonable(v) for k, v in dataclasses.asdict(o2).items()}
    d1.setdefault("domain", "garmin.com")
    return {"oauth1": d1, "oauth2": d2, "domain": "garmin.com"}


def dict_to_tokens(token: dict) -> tuple[OAuth1Token, OAuth2Token]:
    o1_fields = {f.name for f in dataclasses.fields(OAuth1Token)}
    o2_fields = {f.name for f in dataclasses.fields(OAuth2Token)}
    o1 = OAuth1Token(**{k: v for k, v in token["oauth1"].items() if k in o1_fields})
    o2 = OAuth2Token(**{k: v for k, v in token["oauth2"].items() if k in o2_fields})
    return o1, o2


def iso_from_unix(seconds) -> str | None:
    if seconds is None:
        return None
    return datetime.fromtimestamp(float(seconds), tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Stockage du token (equivaut a storeGarminToken cote Edge)
# ---------------------------------------------------------------------------
def store_token(user_id: str, token: dict, profile: dict | None, email: str | None) -> str | None:
    profile = profile or {}
    provider_user_id = str(
        profile.get("profileId")
        or profile.get("userProfileId")
        or profile.get("userName")
        or ""
    )
    display_name = str(
        profile.get("displayName")
        or profile.get("fullName")
        or profile.get("userName")
        or "Garmin"
    )
    sb_upsert(
        "external_auth_tokens",
        {
            "user_id": user_id,
            "provider": "garmin",
            "provider_user_id": provider_user_id,
            "display_name": display_name,
            "email": email,
            "access_token_encrypted": encrypt_secret(token),
            "refresh_token_encrypted": None,
            "expires_at": iso_from_unix(token["oauth2"].get("expires_at")),
            "token_payload": {
                "token_type": "garth_ts",
                "refresh_token_expires_at": token["oauth2"].get("refresh_token_expires_at"),
            },
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    )
    return display_name


def fetch_profile(o1: OAuth1Token, o2: OAuth2Token) -> dict | None:
    try:
        client = garth.Client()
        client.oauth1_token = o1
        client.oauth2_token = o2
        return client.connectapi("/userprofile-service/socialProfile")
    except Exception as exc:
        log(f"  profil non recupere ({exc}) — on continue sans.")
        return None


# ---------------------------------------------------------------------------
# Traitement d'une demande de login
# ---------------------------------------------------------------------------
def process_login(job: dict) -> None:
    job_id = job["id"]
    sync_job_id = job.get("sync_job_id")
    creds = decrypt_secret(job["credentials_encrypted"])
    email = creds.get("email")
    password = creds.get("password")
    log(f"login job {job_id} (user {job['user_id']}, {email})")

    sb_patch("garmin_relay_jobs", {"id": f"eq.{job_id}"}, {"status": "processing"})
    set_sync_job(sync_job_id, stage="logging_in", message="Connexion a Garmin Connect...", progress=20)

    client = garth.Client()
    result = sso.login(email, password, client=client, return_on_mfa=True)

    if isinstance(result, tuple) and result and result[0] == "needs_mfa":
        client_state = result[1]
        PENDING_MFA[job_id] = client_state
        sb_patch("garmin_relay_jobs", {"id": f"eq.{job_id}"}, {"status": "awaiting_mfa"})
        set_sync_job(
            sync_job_id,
            stage="mfa_required",
            message="Code de verification Garmin (MFA) requis.",
            progress=50,
        )
        log(f"  job {job_id} : MFA requis, en attente du code.")
        return

    o1, o2 = result
    _finalize_login(job_id, sync_job_id, job["user_id"], email, o1, o2)


def process_mfa(job: dict) -> None:
    job_id = job["id"]
    sync_job_id = job.get("sync_job_id")
    client_state = PENDING_MFA.get(job_id)
    if client_state is None:
        msg = "Session MFA perdue (relais redemarre). Relance la connexion Garmin."
        fail_job(job_id, sync_job_id, msg)
        return

    mfa_code = decrypt_secret(job["mfa_code_encrypted"])
    if isinstance(mfa_code, dict):  # securite : on a chiffre une string
        mfa_code = mfa_code.get("code", "")
    log(f"mfa job {job_id} : reprise avec code")
    sb_patch("garmin_relay_jobs", {"id": f"eq.{job_id}"}, {"status": "processing"})
    set_sync_job(sync_job_id, stage="mfa_verifying", message="Verification du code...", progress=70)

    o1, o2 = sso.resume_login(client_state, str(mfa_code).strip())
    PENDING_MFA.pop(job_id, None)
    _finalize_login(job_id, sync_job_id, job["user_id"], None, o1, o2)


def _finalize_login(job_id, sync_job_id, user_id, email, o1, o2) -> None:
    token = token_to_dict(o1, o2)
    profile = fetch_profile(o1, o2)
    if email is None and profile:
        email = profile.get("email") or None
    display_name = store_token(user_id, token, profile, email)
    sb_patch(
        "garmin_relay_jobs",
        {"id": f"eq.{job_id}"},
        {"status": "done", "display_name": display_name, "error": None},
    )
    set_sync_job(
        sync_job_id,
        status="succeeded",
        stage="connected",
        progress=100,
        message="Garmin Connect connecte.",
        result={"connected": True, "display_name": display_name},
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    log(f"  job {job_id} : connecte ({display_name}).")


def fail_job(job_id, sync_job_id, message: str) -> None:
    PENDING_MFA.pop(job_id, None)
    sb_patch("garmin_relay_jobs", {"id": f"eq.{job_id}"}, {"status": "failed", "error": message})
    set_sync_job(
        sync_job_id,
        status="failed",
        stage="failed",
        error=message,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    log(f"  job {job_id} ECHEC : {message}")


# ---------------------------------------------------------------------------
# Refresh proactif des tokens (evite que l'Edge appelle l'oauth-service -> 429)
# ---------------------------------------------------------------------------
def refresh_expiring_tokens() -> None:
    now = datetime.now(timezone.utc)
    cutoff = datetime.fromtimestamp(now.timestamp() + REFRESH_MARGIN_SECONDS, tz=timezone.utc)
    rows = sb_get(
        "external_auth_tokens",
        {
            "select": "id,user_id,access_token_encrypted,expires_at",
            "provider": "eq.garmin",
            "expires_at": f"lt.{cutoff.isoformat()}",
        },
    )
    for row in rows:
        try:
            token = decrypt_secret(row["access_token_encrypted"])
            o1, o2 = dict_to_tokens(token)
            client = garth.Client()
            client.oauth1_token = o1
            client.oauth2_token = o2
            client.refresh_oauth2()  # appelle l'oauth-service depuis l'IP residentielle
            new_token = token_to_dict(client.oauth1_token, client.oauth2_token)
            sb_patch(
                "external_auth_tokens",
                {"id": f"eq.{row['id']}"},
                {
                    "access_token_encrypted": encrypt_secret(new_token),
                    "expires_at": iso_from_unix(new_token["oauth2"].get("expires_at")),
                    "token_payload": {
                        "token_type": "garth_ts",
                        "refresh_token_expires_at": new_token["oauth2"].get("refresh_token_expires_at"),
                    },
                },
            )
            log(f"token refresh ok (user {row['user_id']})")
        except Exception as exc:
            log(f"! refresh echoue (user {row.get('user_id')}): {exc}")


# ---------------------------------------------------------------------------
# LiveTrack — scrape la page publique livetrack.garmin.com et insere les
# trackpoints dans Supabase (la PWA les lit via Realtime). Port de
# backend/app/domain/services/livetrack_worker.py. Aucune auth Garmin requise
# (session_id + token sont dans l'URL partagee publique).
# ---------------------------------------------------------------------------
LIVETRACK_PAGE_BASE = "https://livetrack.garmin.com/session"
LIVE_POLL_INTERVAL = float(os.environ.get("LIVE_POLL_INTERVAL", "4"))
LIVE_INACTIVITY_TIMEOUT = float(os.environ.get("LIVE_INACTIVITY_TIMEOUT", "60"))
LIVE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_NEXT_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*?)"\]\)', re.DOTALL)
_LIVE_POINT_KEYS = ("ts", "lat", "lng", "hr", "speed", "cadence", "power", "distance", "altitude")


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _extract_ts(raw: dict):
    dt = raw.get("dateTime") or raw.get("date") or raw.get("ts")
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        v = float(dt)
        return int(v / 1000) if v > 10 ** 12 else int(v)
    if isinstance(dt, str):
        try:
            return int(datetime.fromisoformat(dt.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def parse_garmin_trackpoint(raw: dict):
    if not isinstance(raw, dict):
        return None
    ts = _extract_ts(raw)
    if ts is None:
        return None
    fpd = raw.get("fitnessPointData") or {}
    pos = raw.get("position") or {}
    lat = pos.get("lat") if isinstance(pos, dict) else None
    lng = pos.get("lon") if isinstance(pos, dict) else None
    if lat is None:
        lat = raw.get("lat") or raw.get("latitude")
    if lng is None:
        lng = raw.get("lng") or raw.get("lon") or raw.get("longitude")

    def pick(*keys):
        for k in keys:
            if k in raw and raw[k] not in ("$undefined", None):
                return raw[k]
            if k in fpd and fpd[k] not in ("$undefined", None):
                return fpd[k]
        return None

    return {
        "ts": ts,
        "lat": _as_float(lat),
        "lng": _as_float(lng),
        "hr": _as_int(pick("heartRateBeatsPerMin", "heartRate", "hr")),
        "speed": _as_float(pick("speedMetersPerSec", "speed")),
        "cadence": _as_int(pick("cadenceCyclesPerMin", "cadence")),
        "power": _as_int(pick("powerWatts", "power")),
        "distance": _as_float(pick("totalDistanceMeters", "distanceMeters", "distance")),
        "altitude": _as_float(pick("altitude", "elevationMeters")),
    }


def _decode_next_push_chunks(html: str) -> str:
    out = []
    for chunk in _NEXT_PUSH_RE.findall(html):
        try:
            out.append(chunk.encode("utf-8").decode("unicode_escape", errors="replace"))
        except Exception:
            continue
    return "".join(out)


def _find_matching_bracket(s: str, start: int) -> int:
    if start >= len(s) or s[start] != "[":
        return -1
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _extract_trackpoints_array(combined: str) -> list:
    idx = combined.find('"trackPoints":[')
    if idx < 0:
        return []
    start = idx + len('"trackPoints":')
    end = _find_matching_bracket(combined, start)
    if end <= start:
        return []
    try:
        result = json.loads(combined[start:end])
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []


def fetch_livetrack(garmin_session_id: str, token: str):
    url = f"{LIVETRACK_PAGE_BASE}/{garmin_session_id}/token/{token}"
    r = requests.get(
        url,
        headers={
            "User-Agent": LIVE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=15,
    )
    if r.status_code == 404:
        return "Expired", []
    r.raise_for_status()
    return "InProgress", _extract_trackpoints_array(_decode_next_push_chunks(r.text))


def livetrack_loop() -> None:
    """Thread : poll les sessions LiveTrack actives et insere les points."""
    log("LiveTrack poller demarre.")
    state: dict[str, dict] = {}  # session_id -> {last_ts, last_rx}
    while True:
        try:
            sessions = sb_get("live_sessions", {
                "select": "id,garmin_session_id,garmin_token,started_at",
                "source": "eq.livetrack",
                "status": "eq.active",
            })
            active = set()
            for s in sessions:
                sid = s["id"]
                active.add(sid)
                st = state.setdefault(sid, {"last_ts": 0, "last_rx": time.monotonic()})
                gsid, tok = s.get("garmin_session_id"), s.get("garmin_token")
                if not gsid or not tok:
                    continue
                try:
                    status, raw_points = fetch_livetrack(gsid, tok)
                except Exception as exc:
                    log(f"  livetrack {sid} fetch error: {exc}")
                    continue

                pts = [p for p in (parse_garmin_trackpoint(rp) for rp in raw_points)
                       if p is not None and p["ts"] > st["last_ts"]]
                if pts:
                    rows = [{"session_id": sid, **{k: p.get(k) for k in _LIVE_POINT_KEYS}} for p in pts]
                    sb_insert_ignore("live_trackpoints", rows, "session_id,ts")
                    st["last_ts"] = max(p["ts"] for p in pts)
                    st["last_rx"] = time.monotonic()
                    patch = {"last_point_at": iso_from_unix(st["last_ts"])}
                    if not s.get("started_at"):
                        patch["started_at"] = iso_from_unix(min(p["ts"] for p in pts))
                    sb_patch("live_sessions", {"id": f"eq.{sid}"}, patch)
                    log(f"  livetrack {sid}: +{len(pts)} pts")

                if status == "Expired":
                    sb_patch("live_sessions", {"id": f"eq.{sid}"},
                             {"status": "finished", "ended_at": datetime.now(timezone.utc).isoformat()})
                    state.pop(sid, None)
                elif time.monotonic() - st["last_rx"] > LIVE_INACTIVITY_TIMEOUT:
                    sb_patch("live_sessions", {"id": f"eq.{sid}"},
                             {"status": "stopped", "ended_at": datetime.now(timezone.utc).isoformat()})
                    state.pop(sid, None)

            for sid in list(state.keys()):
                if sid not in active:
                    state.pop(sid, None)
        except Exception as exc:
            log(f"!! livetrack loop error: {exc}")
        time.sleep(LIVE_POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------
def claim_next(status: str) -> dict | None:
    rows = sb_get(
        "garmin_relay_jobs",
        {
            "select": "id,user_id,sync_job_id,credentials_encrypted,mfa_code_encrypted",
            "status": f"eq.{status}",
            "order": "created_at.asc",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def main() -> None:
    log("Relais Garmin demarre. Polling...")
    # LiveTrack tourne dans son propre thread (cadence ~4s) pour ne pas ralentir
    # le traitement des logins.
    threading.Thread(target=livetrack_loop, name="livetrack", daemon=True).start()
    last_refresh = 0.0
    while True:
        try:
            # 1) Demandes MFA prioritaires (un athlete attend devant son ecran).
            mfa_job = claim_next("mfa_submitted")
            if mfa_job:
                try:
                    process_mfa(mfa_job)
                except Exception as exc:
                    fail_job(mfa_job["id"], mfa_job.get("sync_job_id"),
                             f"Code MFA refuse ou expire ({exc}).")
                continue

            # 2) Nouvelles connexions.
            login_job = claim_next("pending")
            if login_job:
                try:
                    process_login(login_job)
                except Exception as exc:
                    detail = str(exc)
                    if "429" in detail:
                        detail = ("Garmin a temporairement bloque la connexion. "
                                  "Patiente quelques minutes et reessaie.")
                    fail_job(login_job["id"], login_job.get("sync_job_id"),
                             f"Connexion Garmin impossible : {detail}")
                continue

            # 3) Refresh proactif a intervalle regulier.
            if time.time() - last_refresh > REFRESH_INTERVAL:
                refresh_expiring_tokens()
                last_refresh = time.time()

        except Exception as exc:  # pragma: no cover — robustesse boucle
            log(f"!! erreur boucle : {exc}\n{traceback.format_exc()}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Arret demande. Bye.")
