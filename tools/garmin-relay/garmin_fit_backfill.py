#!/usr/bin/env python3
"""garmin_fit_backfill.py — Telecharge et traite les fichiers FIT Garmin depuis
une IP RESIDENTIELLE (le second Mac), car le endpoint de download FIT de Garmin
rate-limite (HTTP 429) les appels depuis l'IP datacenter de Supabase.

Pour chaque activite Garmin sans metriques FIT :
  1. telecharge le .fit via garth (IP residentielle) — 1 seule requete Garmin
  2. dezippe + parse le FIT en local (fitparse)
  3. calcule les memes metriques que l'Edge garmin-fit-enrich (records + session)
  4. ecrit le .fit brut + les streams dans Supabase Storage
  5. upsert dans fit_metrics + met has_fit_metrics=true sur l'activite

Reutilise le meme .env que le relais (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
ENCRYPTION_KEY). Traite tous les athletes ayant un token Garmin.

  pip install garth requests cryptography fitparse
  python garmin_fit_backfill.py
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone

try:
    import requests
    import garth
    from garth.auth_tokens import OAuth1Token, OAuth2Token
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from fitparse import FitFile
except ImportError as exc:  # pragma: no cover
    sys.exit(f"Dependance manquante ({exc}). Fais : pip install garth requests cryptography fitparse")


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
# Pacing : delai entre deux telechargements FIT pour menager le rate-limit Garmin.
DOWNLOAD_DELAY = float(os.environ.get("FIT_DOWNLOAD_DELAY", "2.5"))
SEMICIRCLE_TO_DEG = 180.0 / (2 ** 31)

if not (SUPABASE_URL and SERVICE_ROLE_KEY and ENCRYPTION_KEY):
    sys.exit("Config manquante (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ENCRYPTION_KEY). cf .env")

REST = f"{SUPABASE_URL}/rest/v1"
STORAGE = f"{SUPABASE_URL}/storage/v1/object"
HEADERS = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


# --- Chiffrement (identique a crypto.ts) -----------------------------------
def _aes_key() -> bytes:
    return hashlib.sha256(ENCRYPTION_KEY.encode("utf-8")).digest()


def decrypt_secret(blob: str):
    raw = base64.b64decode(blob)
    iv, payload = raw[:12], raw[12:]
    return json.loads(AESGCM(_aes_key()).decrypt(iv, payload, None).decode("utf-8"))


# --- PostgREST + Storage ---------------------------------------------------
def sb_get(table: str, params: dict) -> list[dict]:
    r = requests.get(f"{REST}/{table}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def sb_patch(table: str, params: dict, payload: dict) -> None:
    h = dict(HEADERS); h["Prefer"] = "return=minimal"
    r = requests.patch(f"{REST}/{table}", headers=h, params=params, json=payload, timeout=30)
    r.raise_for_status()


def sb_upsert(table: str, payload: dict, on_conflict: str) -> None:
    h = dict(HEADERS); h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    r = requests.post(f"{REST}/{table}?on_conflict={on_conflict}", headers=h, json=payload, timeout=30)
    r.raise_for_status()


def storage_upload(path: str, data: bytes, content_type: str) -> None:
    h = {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
         "Content-Type": content_type, "x-upsert": "true"}
    r = requests.post(f"{STORAGE}/activity-raw/{path}", headers=h, data=data, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"storage upload {r.status_code}: {r.text[:200]}")


# --- Token Garmin ----------------------------------------------------------
def build_client(token: dict) -> garth.Client:
    o1f = {f.name for f in dataclasses.fields(OAuth1Token)}
    o2f = {f.name for f in dataclasses.fields(OAuth2Token)}
    client = garth.Client()
    client.oauth1_token = OAuth1Token(**{k: v for k, v in token["oauth1"].items() if k in o1f})
    client.oauth2_token = OAuth2Token(**{k: v for k, v in token["oauth2"].items() if k in o2f})
    return client


# --- Metriques (port fidele de garmin-fit-enrich/index.ts) -----------------
def first_number(*values):
    for v in values:
        try:
            n = float(v)
            if n == n and n not in (float("inf"), float("-inf")):
                return n
        except (TypeError, ValueError):
            continue
    return None


def avg(records, *keys):
    vals = [first_number(*[r.get(k) for k in keys]) for r in records]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return round((sum(vals) / len(vals)) * 10) / 10


def compact(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def metrics_from_records(records: list[dict]) -> dict:
    return compact({
        "ground_contact_time_avg": avg(records, "stance_time"),
        "vertical_oscillation_avg": avg(records, "vertical_oscillation"),
        "stance_time_balance_avg": avg(records, "stance_time_balance"),
        "stance_time_percent_avg": avg(records, "stance_time_percent"),
        "step_length_avg": avg(records, "step_length"),
        "vertical_ratio_avg": avg(records, "vertical_ratio"),
        "power_avg": avg(records, "power"),
        "record_count": len(records),
    })


def metrics_from_session(s: dict) -> dict:
    return compact({
        "aerobic_training_effect": first_number(s.get("total_training_effect")),
        "anaerobic_training_effect": first_number(s.get("total_anaerobic_training_effect")),
        "heart_rate_avg": first_number(s.get("avg_heart_rate")),
        "heart_rate_max": first_number(s.get("max_heart_rate")),
        "speed_avg": first_number(s.get("enhanced_avg_speed"), s.get("avg_speed")),
        "speed_max": first_number(s.get("enhanced_max_speed"), s.get("max_speed")),
        "power_avg": first_number(s.get("avg_power")),
        "power_max": first_number(s.get("max_power")),
        "normalized_power": first_number(s.get("normalized_power")),
        "cadence_avg": first_number(s.get("avg_running_cadence")),
        "cadence_max": first_number(s.get("max_running_cadence")),
        "temperature_avg": first_number(s.get("avg_temperature")),
        "temperature_max": first_number(s.get("max_temperature")),
        "total_calories": first_number(s.get("total_calories")),
        "total_strides": first_number(s.get("total_strides")),
        "total_ascent": first_number(s.get("total_ascent")),
        "total_descent": first_number(s.get("total_descent")),
        "total_distance": first_number(s.get("total_distance")),
        "total_timer_time": first_number(s.get("total_timer_time")),
        "total_elapsed_time": first_number(s.get("total_elapsed_time")),
    })


def semicircle_or_degree(v):
    if v is None:
        return None
    return v * SEMICIRCLE_TO_DEG if abs(v) > 1000 else v


def build_streams(records: list[dict]) -> dict:
    if not records:
        return {}
    def ts(r):
        t = r.get("timestamp")
        return t.timestamp() if isinstance(t, datetime) else None
    start = ts(records[0])
    streams: dict[str, list] = {}
    def push(key, value):
        streams.setdefault(key, []).append(value)
    for r in records:
        t = ts(r)
        push("time", max(0.0, t - start) if (start is not None and t is not None) else None)
        push("distance", first_number(r.get("distance")))
        push("altitude", first_number(r.get("enhanced_altitude"), r.get("altitude")))
        push("heartrate", first_number(r.get("heart_rate")))
        push("cadence", first_number(r.get("cadence"), r.get("running_cadence")))
        push("velocity_smooth", first_number(r.get("enhanced_speed"), r.get("speed")))
        push("grade_smooth", first_number(r.get("grade")))
        push("watts", first_number(r.get("power")))
        push("temp", first_number(r.get("temperature")))
        push("stance_time", first_number(r.get("stance_time")))
        push("vertical_oscillation", first_number(r.get("vertical_oscillation")))
        push("step_length", first_number(r.get("step_length")))
        push("vertical_ratio", first_number(r.get("vertical_ratio")))
        lat = semicircle_or_degree(first_number(r.get("position_lat")))
        lon = semicircle_or_degree(first_number(r.get("position_long")))
        push("latlng", [lat, lon] if (lat is not None and lon is not None) else None)
    return {k: {"data": v} for k, v in streams.items() if any(x is not None for x in v)}


# --- Parsing FIT -----------------------------------------------------------
def extract_fit_bytes(raw: bytes) -> bytes:
    # Garmin renvoie un .zip (signature PK) contenant le .fit.
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            fit_name = next((n for n in zf.namelist() if n.lower().endswith(".fit")), None)
            return zf.read(fit_name) if fit_name else b""
    return raw


def parse_fit(fit_bytes: bytes):
    ff = FitFile(io.BytesIO(fit_bytes))
    records = [{d.name: d.value for d in m} for m in ff.get_messages("record")]
    sessions = [{d.name: d.value for d in m} for m in ff.get_messages("session")]
    return records, sessions


# --- Traitement d'une activite --------------------------------------------
def process_activity(client: garth.Client, user_id: str, activity: dict) -> bool:
    activity_id = str(activity["id"])
    garmin_id = activity.get("garmin_activity_id")
    if not garmin_id:
        return False

    raw = client.download(f"/download-service/files/activity/{int(garmin_id)}")
    fit_bytes = extract_fit_bytes(raw)
    if not fit_bytes:
        log(f"  {activity_id}: pas de .fit dans l'archive")
        return False

    raw_fit_path = f"{user_id}/fit/{activity_id}.fit"
    storage_upload(raw_fit_path, fit_bytes, "application/octet-stream")

    records, sessions = parse_fit(fit_bytes)
    metrics = {**metrics_from_records(records),
               **(metrics_from_session(sessions[0]) if sessions else {}),
               "raw_fit_path": raw_fit_path,
               "fit_downloaded_at": datetime.now(timezone.utc).isoformat()}

    streams = build_streams(records)
    raw_streams_path = None
    if streams:
        raw_streams_path = f"{user_id}/activities/{activity_id}/streams.json"
        storage_upload(raw_streams_path, json.dumps(streams).encode("utf-8"), "application/json")

    sb_upsert("fit_metrics", {
        "user_id": user_id, "activity_id": activity_id, **metrics,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="activity_id")

    patch = {"has_fit_metrics": True, "updated_at": datetime.now(timezone.utc).isoformat()}
    if raw_streams_path:
        patch["has_streams"] = True
        patch["raw_streams_path"] = raw_streams_path
    sb_patch("activities", {"id": f"eq.{activity_id}", "user_id": f"eq.{user_id}"}, patch)
    return True


def process_user(token_row: dict) -> None:
    user_id = token_row["user_id"]
    token = decrypt_secret(token_row["access_token_encrypted"])
    client = build_client(token)

    pending = sb_get("activities", {
        "select": "id,garmin_activity_id,name,start_date_utc",
        "user_id": f"eq.{user_id}",
        "garmin_activity_id": "not.is.null",
        "has_fit_metrics": "eq.false",
        "order": "start_date_utc.desc",
    })
    log(f"User {user_id}: {len(pending)} activite(s) FIT a traiter")

    ok = fail = 0
    for i, activity in enumerate(pending, 1):
        try:
            if process_activity(client, user_id, activity):
                ok += 1
                log(f"  [{i}/{len(pending)}] {activity.get('name') or activity['id']} OK")
            else:
                fail += 1
        except Exception as exc:
            fail += 1
            detail = str(exc)
            if "429" in detail:
                log(f"  [{i}/{len(pending)}] 429 rate-limit Garmin -> pause 60s")
                time.sleep(60)
            else:
                log(f"  [{i}/{len(pending)}] ECHEC: {detail[:160]}")
        time.sleep(DOWNLOAD_DELAY)
    log(f"User {user_id}: termine. {ok} OK, {fail} echec(s).")


def main() -> None:
    log("Backfill FIT Garmin demarre.")
    tokens = sb_get("external_auth_tokens", {
        "select": "user_id,access_token_encrypted",
        "provider": "eq.garmin",
    })
    if not tokens:
        log("Aucun token Garmin en base. Connecte d'abord Garmin depuis l'app.")
        return
    for token_row in tokens:
        try:
            process_user(token_row)
        except Exception as exc:
            log(f"User {token_row.get('user_id')}: erreur globale {exc}")
    log("Backfill FIT termine.")


if __name__ == "__main__":
    main()
