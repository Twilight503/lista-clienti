import os
import json
from copy import deepcopy
from datetime import datetime
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
    raise RuntimeError("Lipsește MONGO_URI. Pune URI-ul MongoDB în Environment Variables.")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-render-env")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[DB_NAME]
collection = mongo_db[COLLECTION_NAME]


def empty_state():
    return {
        "version": 12,
        "createdAt": datetime.utcnow().isoformat(),
        "employees": [],
        "clients": [],
        "deletedRecords": [],
        "transfers": [],
        "backups": [],
    }


def public_state(doc):
    if not doc:
        return empty_state(), 0

    state = deepcopy(doc)
    state.pop("_id", None)
    rev = int(state.pop("_rev", 0) or 0)

    state.setdefault("version", 12)
    state.setdefault("createdAt", datetime.utcnow().isoformat())
    state.setdefault("employees", [])
    state.setdefault("clients", [])
    state.setdefault("deletedRecords", [])
    state.setdefault("transfers", [])
    state.setdefault("backups", [])

    return json.loads(json_util.dumps(state)), rev


def get_or_create_doc():
    doc = collection.find_one({"_id": STATE_ID})
    if doc:
        return doc

    initial = empty_state()
    initial["_id"] = STATE_ID
    initial["_rev"] = 1
    collection.insert_one(initial)
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
:root{--blue:#2563eb;--dark:#0f172a;--border:#d9dee7;--muted:#667085}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font-family:Arial,sans-serif;background:
radial-gradient(circle at top left,rgba(37,99,235,.22),transparent 34%),
linear-gradient(135deg,#f8fafc,#eef2ff);display:flex;align-items:center;justify-content:center;padding:22px;color:#172033}
.card{width:100%;max-width:410px;background:#fff;border:1px solid var(--border);border-radius:24px;padding:28px;box-shadow:0 24px 60px rgba(15,23,42,.14)}
.logo{width:64px;height:64px;border-radius:20px;background:linear-gradient(135deg,#2563eb,#22c55e);display:flex;align-items:center;justify-content:center;color:#fff;font-size:24px;font-weight:1000;margin-bottom:16px}
h1{margin:0 0 6px;font-size:28px;letter-spacing:-.05em}
p{margin:0 0 22px;color:var(--muted);line-height:1.45}
label{display:block;font-size:13px;color:var(--muted);font-weight:800;margin-bottom:7px}
input{width:100%;height:48px;border:1px solid var(--border);border-radius:14px;padding:0 14px;font-size:16px;outline:none}
input:focus{border-color:var(--blue);box-shadow:0 0 0 4px rgba(37,99,235,.12)}
button{width:100%;height:48px;border:0;border-radius:14px;margin-top:14px;background:var(--blue);color:#fff;font-size:16px;font-weight:900;cursor:pointer}
button:hover{background:#1d4ed8}
.footer{margin-top:16px;font-size:12px;color:#98a2b3;text-align:center}
</style>
</head>
<body>
<form class="card" method="post">
  <div class="logo">VC</div>
  <h1>Verificare Clienți</h1>
  <p>Intră în aplicația de audit, verificare și transfer pentru clienți.</p>
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
    new_state["updatedAt"] = datetime.utcnow().isoformat()

    next_rev = current_rev + 1
    new_state["_rev"] = next_rev

    result = collection.replace_one(
        {"_id": STATE_ID, "_rev": current_rev},
        {"_id": STATE_ID, **new_state}
    )
    if result.matched_count != 1:
        return jsonify({"error": "conflict"}), 409

    return jsonify({"ok": True, "rev": next_rev})


@app.post("/api/reset")
@require_login
def api_reset():
    fresh = empty_state()
    fresh["_id"] = STATE_ID
    fresh["_rev"] = 1
    collection.replace_one({"_id": STATE_ID}, fresh, upsert=True)
    return jsonify({"ok": True, "rev": 1})


@app.get("/api/backup")
@require_login
def api_backup():
    doc = get_or_create_doc()
    state, rev = public_state(doc)
    return app.response_class(
        json.dumps({"rev": rev, "db": state}, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=verificare_clienti_backup.json"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
