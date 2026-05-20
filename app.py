import os
import json
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps

from bson import json_util
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pymongo import MongoClient

APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
DB_NAME = os.environ.get("DB_NAME", "test")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "Clienti maro/rosu")
STATE_ID = os.environ.get("STATE_ID", "state")

if not MONGO_URI:
    raise RuntimeError("Lipsește MONGO_URI. Pune URI-ul MongoDB în Environment Variables pe Render.")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "schimba-asta-in-render")

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
    }


def sanitize_state(state):
    """Ține documentul Mongo mic și curat."""
    if not isinstance(state, dict):
        state = empty_state()

    state.setdefault("version", 12)
    state.setdefault("createdAt", utc_now())
    state.setdefault("employees", [])
    state.setdefault("deletedEmployeeNames", {})
    state.setdefault("clients", [])
    state.setdefault("transfers", [])

    # Nu păstrăm arhivă de ștergeri în Mongo. Ștergerile sunt definitive în UI.
    state["deletedRecords"] = []

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
        return redirect(request.args.get("next") or url_for("index"))

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
    return render_template("index.html", initial_db=state, rev=rev)


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
    client_rev = int(payload.get("rev", 0) or 0)

    if not isinstance(new_state, dict):
        return "Payload invalid: db trebuie să fie obiect JSON.", 400

    current = get_or_create_doc()
    current_rev = int(current.get("_rev", 0) or 0)

    if client_rev != current_rev:
        return jsonify({"error": "conflict", "current_rev": current_rev}), 409

    new_state = deepcopy(new_state)
    new_state.pop("_id", None)
    new_state.pop("_rev", None)
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
