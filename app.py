import os
import json
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import urlsplit

from bson import json_util
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pymongo import MongoClient

APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
DB_NAME = os.environ.get("DB_NAME", "test")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "Clienti maro/rosu")
STATE_ID = os.environ.get("STATE_ID", "state")
MAX_TRANSFER_BATCHES = 100

if not MONGO_URI:
    raise RuntimeError("Lipsește MONGO_URI. Pune URI-ul MongoDB în Environment Variables pe Render.")

app = Flask(__name__)
# Fără SECRET_KEY configurat, folosim o cheie aleatoare la fiecare pornire în locul
# unei valori publice/predictibile. Pe Render este recomandat în continuare SECRET_KEY stabil.
app.secret_key = os.environ.get("SECRET_KEY", "").strip() or os.urandom(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[DB_NAME]
collection = mongo_db[COLLECTION_NAME]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def empty_state():
    return {
        "version": 12,
        "createdAt": utc_now(),
        "employees": [],
        "deletedEmployeeNames": {},
        "clients": [],
        "deletedRecords": [],
        "transfers": [],
        "backups": [],
        "archivedClients": [],
    }


def _parse_iso(dt):
    if not dt or not isinstance(dt, str):
        return None
    try:
        parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def purge_expired_archived_clients(items):
    now_utc = datetime.now(timezone.utc)
    kept = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue

        item = deepcopy(raw)
        archived_at = _parse_iso(item.get("archivedAt")) or now_utc
        delete_at = _parse_iso(item.get("deleteAt")) or (archived_at + timedelta(days=90))

        if delete_at <= now_utc:
            continue

        item["archivedAt"] = archived_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        item["deleteAt"] = delete_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        item.setdefault("history", [])
        item.setdefault("assignmentsSnapshot", [])
        item.setdefault("clientHistory", [])
        kept.append(item)
    return kept


def phone_key(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def trim_transfer_history(items):
    if not isinstance(items, list):
        return []

    indexed = []
    fallback = datetime.min.replace(tzinfo=timezone.utc)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        indexed.append((_parse_iso(item.get("createdAt")) or fallback, index, item))

    indexed.sort(key=lambda row: (row[0], row[1]))
    return [item for _, _, item in indexed[-MAX_TRANSFER_BATCHES:]]


def merge_unique_history(*lists):
    seen = set()
    merged = []
    for items in lists:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("date", "")), str(item.get("text", "")))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def merge_archived_clients(*lists):
    """
    Îmbină arhivele după telefon. Este intenționat server-side, ca un update vechi,
    un import vechi sau un restore fără `archivedClients` să nu poată goli arhiva.
    """
    merged = {}
    for items in lists:
        for raw in purge_expired_archived_clients(items or []):
            key = phone_key(raw.get("phone"))
            if not key:
                continue

            old = merged.get(key)
            if not old:
                merged[key] = raw
                continue

            old_date = _parse_iso(old.get("archivedAt")) or datetime.min.replace(tzinfo=timezone.utc)
            new_date = _parse_iso(raw.get("archivedAt")) or datetime.min.replace(tzinfo=timezone.utc)
            base, other = (raw, old) if new_date >= old_date else (old, raw)

            base["history"] = merge_unique_history(other.get("history"), base.get("history"))
            base["clientHistory"] = merge_unique_history(other.get("clientHistory"), base.get("clientHistory"))
            if not base.get("assignmentsSnapshot") and other.get("assignmentsSnapshot"):
                base["assignmentsSnapshot"] = other.get("assignmentsSnapshot")
            for field in ("note", "reason", "lastReappearedAt", "lastReappearedSource", "feedbackSummary"):
                if not base.get(field) and other.get(field):
                    base[field] = other.get(field)
            base["reappearCount"] = max(int(base.get("reappearCount") or 0), int(other.get("reappearCount") or 0))
            base["noAnswerTotal"] = max(int(base.get("noAnswerTotal") or 0), int(other.get("noAnswerTotal") or 0))
            merged[key] = base

    return list(merged.values())


def active_client_phones(state):
    phones = set()
    for client in (state or {}).get("clients", []) or []:
        if isinstance(client, dict):
            key = phone_key(client.get("phone"))
            if key:
                phones.add(key)
    return phones


def protect_archived_clients(incoming_state, current_doc, allow_archive_shrink=False):
    """
    Protecție anti-pierdere arhivă la salvare.

    Reguli:
    - dacă noua stare nu conține arhivă, se păstrează arhiva curentă din Mongo;
    - dacă noua stare are arhivă incompletă, se îmbină cu arhiva curentă;
    - dacă un telefon a fost reactivat în `clients`, nu este reintrodus în arhivă;
    - ștergerea definitivă din arhivă este permisă doar când frontendul trimite explicit
      `archiveGuard.allowArchiveShrink=true`;
    - intrările expirate rămân curățate automat de funcția de purge.
    """
    if not isinstance(incoming_state, dict):
        incoming_state = {}

    current_archive = purge_expired_archived_clients((current_doc or {}).get("archivedClients", []))
    incoming_archive = incoming_state.get("archivedClients") if isinstance(incoming_state.get("archivedClients"), list) else []
    reactivated_phones = active_client_phones(incoming_state)

    if allow_archive_shrink:
        protected_archive = purge_expired_archived_clients(incoming_archive)
    else:
        preserved_current = [
            a for a in current_archive
            if phone_key(a.get("phone")) not in reactivated_phones
        ]
        protected_archive = merge_archived_clients(incoming_archive, preserved_current)

    # Nu ținem același telefon simultan în baza activă și în arhivă.
    incoming_state["archivedClients"] = [
        a for a in protected_archive
        if phone_key(a.get("phone")) not in reactivated_phones
    ]
    return incoming_state


def sanitize_state(state):
    """Ține documentul Mongo mic, coerent și sub limita practică de dimensiune."""
    if not isinstance(state, dict):
        state = empty_state()

    state.setdefault("version", 12)
    state.setdefault("createdAt", utc_now())
    state["employees"] = state.get("employees") if isinstance(state.get("employees"), list) else []
    state["deletedEmployeeNames"] = state.get("deletedEmployeeNames") if isinstance(state.get("deletedEmployeeNames"), dict) else {}
    state["clients"] = state.get("clients") if isinstance(state.get("clients"), list) else []
    state["archivedClients"] = state.get("archivedClients") if isinstance(state.get("archivedClients"), list) else []

    # Nu păstrăm arhivă de ștergeri în Mongo. Ștergerile sunt definitive în UI.
    state["deletedRecords"] = []
    state["archivedClients"] = purge_expired_archived_clients(state["archivedClients"])

    # Istoricul transferurilor este folosit în UI, dar nu trebuie să crească nelimitat.
    state["transfers"] = trim_transfer_history(state.get("transfers", []))

    # Backup-urile automate sunt copii complete; păstrăm doar ultimele 3 ca să nu umfle baza.
    backups = state.get("backups", [])
    state["backups"] = backups[-3:] if isinstance(backups, list) else []

    return state


def clean_for_json(obj):
    return json.loads(json_util.dumps(obj))


def public_state(doc):
    if not doc:
        return empty_state(), 0

    state = deepcopy(doc)
    state.pop("_id", None)
    rev = int(state.pop("_rev", 0) or 0)

    state.setdefault("version", 12)
    state.setdefault("createdAt", utc_now())
    state.setdefault("employees", [])
    state.setdefault("deletedEmployeeNames", {})
    state.setdefault("clients", [])
    state.setdefault("deletedRecords", [])
    state.setdefault("transfers", [])
    state.setdefault("backups", [])
    state.setdefault("archivedClients", [])
    state["archivedClients"] = purge_expired_archived_clients(state.get("archivedClients", []))

    state = sanitize_state(state)
    return clean_for_json(state), rev


def get_or_create_doc():
    doc = collection.find_one({"_id": STATE_ID})
    if doc:
        return doc

    state = empty_state()
    state["_id"] = STATE_ID
    state["_rev"] = 1
    collection.insert_one(state)
    return collection.find_one({"_id": STATE_ID})


def safe_next_path(target):
    """Acceptă doar redirecturi interne, pentru a evita open redirect după login."""
    if not isinstance(target, str) or not target.startswith("/"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("//"):
        return None
    return target


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if APP_PASSWORD and not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.get("/login")
def login():
    if not APP_PASSWORD:
        return redirect(url_for("index"))

    return """
<!doctype html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Login - Verificare Clienți</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font-family:Arial,sans-serif;background:
radial-gradient(circle at top left,rgba(37,99,235,.22),transparent 34%),
linear-gradient(135deg,#f8fafc,#eef2ff);display:flex;align-items:center;justify-content:center;padding:22px;color:#172033}
.card{width:100%;max-width:410px;background:#fff;border:1px solid #d9dee7;border-radius:24px;padding:28px;box-shadow:0 24px 60px rgba(15,23,42,.14)}
.logo{font-size:17px;letter-spacing:.08em;font-weight:800;color:#1e3a8a;margin-bottom:3px}
h1{margin:0 0 18px;font-size:32px;letter-spacing:-.055em}
p{margin:0 0 22px;color:#667085;line-height:1.45}
label{display:block;font-size:13px;color:#667085;font-weight:800;margin-bottom:7px}
input{width:100%;height:48px;border:1px solid #d9dee7;border-radius:14px;padding:0 14px;font-size:16px;outline:none}
input:focus{border-color:#2563eb;box-shadow:0 0 0 4px rgba(37,99,235,.12)}
button{width:100%;height:48px;border:0;border-radius:14px;margin-top:14px;background:#2563eb;color:#fff;font-size:16px;font-weight:900;cursor:pointer}
button:hover{background:#1d4ed8}
.footer{margin-top:16px;font-size:12px;color:#98a2b3;text-align:center}
</style>
</head>
<body>
<form class="card" method="post">
  <div class="logo">VC</div>
  <h1>Verificare Clienți</h1>
  <p>Intră în aplicația de audit, verificare și transfer MARO.</p>
  <label>Parolă acces</label>
  <input type="password" name="password" placeholder="Introdu parola" autofocus>
  <button>Intră în aplicație</button>
  <div class="footer">Acces protejat prin parolă</div>
</form>
</body>
</html>
"""


@app.post("/login")
def login_post():
    if not APP_PASSWORD:
        return redirect(url_for("index"))

    if request.form.get("password") == APP_PASSWORD:
        session["logged_in"] = True
        return redirect(safe_next_path(request.args.get("next")) or url_for("index"))

    return "Parolă greșită", 401


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login") if APP_PASSWORD else url_for("index"))


@app.get("/")
@require_login
def index():
    doc = get_or_create_doc()
    state, rev = public_state(doc)
    return render_template(
        "index.html",
        initial_db=state,
        rev=rev,
        max_transfer_batches=MAX_TRANSFER_BATCHES,
    )


@app.get("/api/state")
@require_login
def api_get_state():
    doc = get_or_create_doc()
    state, rev = public_state(doc)
    return jsonify({"db": state, "rev": rev})


@app.post("/api/state")
@require_login
def api_save_state():
    payload = request.get_json(silent=True) or {}
    new_state = payload.get("db")
    try:
        client_rev = int(payload.get("rev", 0) or 0)
    except (TypeError, ValueError):
        return "Payload invalid: rev trebuie să fie număr întreg.", 400

    if not isinstance(new_state, dict):
        return "Payload invalid: db trebuie să fie obiect JSON.", 400

    current = get_or_create_doc()
    current_rev = int(current.get("_rev", 0) or 0)

    if client_rev != current_rev:
        return jsonify({"error": "conflict", "current_rev": current_rev}), 409

    allow_archive_shrink = bool(
        isinstance(payload.get("archiveGuard"), dict)
        and payload.get("archiveGuard", {}).get("allowArchiveShrink") is True
    )

    new_state = deepcopy(new_state)
    new_state.pop("_id", None)
    new_state.pop("_rev", None)
    new_state = protect_archived_clients(new_state, current, allow_archive_shrink=allow_archive_shrink)
    new_state = sanitize_state(new_state)
    new_state["updatedAt"] = utc_now()
    new_state["_rev"] = current_rev + 1

    result = collection.replace_one(
        {"_id": STATE_ID, "_rev": current_rev},
        {"_id": STATE_ID, **new_state}
    )

    if result.matched_count != 1:
        return jsonify({"error": "conflict"}), 409

    return jsonify({"ok": True, "rev": current_rev + 1})


@app.post("/api/reset")
@require_login
def api_reset():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirm") != "RESET":
        return "Confirmare lipsă. Pentru reset complet trebuie trimis confirm=RESET.", 400

    state = empty_state()
    state["_id"] = STATE_ID
    state["_rev"] = 1
    collection.replace_one({"_id": STATE_ID}, state, upsert=True)
    return jsonify({"ok": True, "rev": 1})


@app.get("/api/backup")
@require_login
def api_backup():
    doc = get_or_create_doc()
    state, rev = public_state(doc)
    return app.response_class(
        json.dumps({"rev": rev, "db": state}, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=backup_verificare_clienti_render.json"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
