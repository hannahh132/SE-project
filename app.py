"""Disaster Relief System — Victim / Volunteer / NGO, Flask + SQLite."""
import os, sqlite3, secrets
from functools import wraps
from markupsafe import Markup
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "relief-secret-dev-key")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relief.db")

HELP_TYPES = ["Food", "Water", "Rescue", "Medical", "Shelter"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  name     TEXT    NOT NULL,
  email    TEXT    UNIQUE NOT NULL,
  phone    TEXT,
  password TEXT    NOT NULL,
  role     TEXT    NOT NULL CHECK(role IN ('volunteer','ngo')),
  location TEXT,
  skills   TEXT,
  available INTEGER DEFAULT 1,
  created  TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  victim_name   TEXT    NOT NULL,
  victim_phone  TEXT,
  type          TEXT    NOT NULL,
  description   TEXT,
  location      TEXT    NOT NULL,
  people        INTEGER DEFAULT 1,
  status        TEXT    NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending','Accepted','In Progress','Completed','Rejected')),
  volunteer_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  tracking_code TEXT    NOT NULL,
  created       TEXT    DEFAULT CURRENT_TIMESTAMP,
  updated       TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resources (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT NOT NULL,
  category  TEXT NOT NULL,
  quantity  INTEGER NOT NULL DEFAULT 0,
  unit      TEXT DEFAULT 'units',
  location  TEXT,
  added_by  INTEGER REFERENCES users(id) ON DELETE SET NULL
);
"""

# ── DB helpers ──────────────────────────────────────────────────────────────
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def q(sql, args=()):   return db().execute(sql, args).fetchall()
def q1(sql, args=()):  return db().execute(sql, args).fetchone()
def run(sql, args=()):
    c = db().execute(sql, args); db().commit(); return c

def init_db():
    with app.app_context():
        db().executescript(SCHEMA)

# ── Auth helpers ─────────────────────────────────────────────────────────────
def cur():
    if "user" not in g:
        g.user = q1("SELECT * FROM users WHERE id=?", (session["uid"],)) \
                 if "uid" in session else None
    return g.user

def csrf():
    session.setdefault("_t", secrets.token_hex(16))
    return Markup(f'<input type="hidden" name="_t" value="{session["_t"]}">')

@app.before_request
def csrf_check():
    session.setdefault("_t", secrets.token_hex(16))
    if request.method == "POST" and request.form.get("_t") != session["_t"]:
        return "Invalid form token", 400

@app.context_processor
def inject():
    return dict(user=cur(), csrf=csrf, HELP_TYPES=HELP_TYPES)

def auth(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            u = cur()
            if not u:
                flash("Please sign in first.", "error")
                return redirect(url_for("login"))
            if roles and u["role"] not in roles:
                return "Access denied", 403
            return f(*a, **kw)
        return wrapper
    return deco

# ── Public / Index ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    u = cur()
    if u:
        return redirect(url_for("dashboard"))
    stats = {
        "pending": q1("SELECT COUNT(*) c FROM requests WHERE status='Pending'")["c"],
        "done":    q1("SELECT COUNT(*) c FROM requests WHERE status='Completed'")["c"],
        "vols":    q1("SELECT COUNT(*) c FROM users WHERE role='volunteer'")["c"],
    }
    return render_template("index.html", stats=stats)

# ── Victim (no login) ────────────────────────────────────────────────────────
@app.route("/sos", methods=["GET", "POST"])
def sos():
    """Victim submits an emergency request — no account required."""
    if request.method == "POST":
        f = request.form
        name    = f.get("victim_name", "").strip()
        phone   = f.get("victim_phone", "").strip()
        htype   = f.get("type", "")
        loc     = f.get("location", "").strip()
        desc    = f.get("description", "").strip()
        try: people = max(1, int(f.get("people", 1)))
        except ValueError: people = 1

        if not name or htype not in HELP_TYPES or not loc:
            flash("Please fill in your name, location, and type of help.", "error")
            return render_template("sos.html")

        code = secrets.token_hex(5).upper()   # 10-char tracking code
        run("""INSERT INTO requests
               (victim_name, victim_phone, type, description, location, people, tracking_code)
               VALUES (?,?,?,?,?,?,?)""",
            (name, phone, htype, desc, loc, people, code))
        return redirect(url_for("track", code=code))

    return render_template("sos.html")

@app.route("/track", methods=["GET", "POST"])
def track_form():
    """Form for victim to enter tracking code manually."""
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        if code:
            return redirect(url_for("track", code=code))
        flash("Please enter a tracking code.", "error")
    return render_template("track_form.html")

@app.route("/track/<code>")
def track(code):
    """Victim tracks their request by tracking code."""
    req = q1("""SELECT r.*, u.name vol_name, u.phone vol_phone
                FROM requests r
                LEFT JOIN users u ON u.id = r.volunteer_id
                WHERE r.tracking_code = ?""", (code,))
    if not req:
        flash("Tracking code not found.", "error")
        return redirect(url_for("index"))
    return render_template("track.html", req=req)

@app.route("/api/track/<code>")
def api_track(code):
    """JSON endpoint for live auto-refresh of tracking status."""
    req = q1("""SELECT r.status, r.updated, u.name vol_name, u.phone vol_phone
                FROM requests r
                LEFT JOIN users u ON u.id = r.volunteer_id
                WHERE r.tracking_code = ?""", (code,))
    if not req:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(req))

# ── Auth ─────────────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name  = f.get("name", "").strip()
        email = f.get("email", "").strip().lower()
        phone = f.get("phone", "").strip()
        pw    = f.get("password", "")
        role  = f.get("role", "")
        loc   = f.get("location", "").strip()
        skills= f.get("skills", "").strip()

        if role not in ("volunteer", "ngo"):
            flash("Please select a valid role.", "error")
        elif not name or "@" not in email or len(pw) < 6:
            flash("Fill all required fields (password min 6 chars).", "error")
        elif q1("SELECT 1 FROM users WHERE email=?", (email,)):
            flash("That email is already registered.", "error")
        else:
            uid = run("""INSERT INTO users (name,email,phone,password,role,location,skills)
                         VALUES (?,?,?,?,?,?,?)""",
                      (name, email, phone, generate_password_hash(pw), role, loc, skills)).lastrowid
            session.clear()
            session["uid"] = uid
            flash(f"Welcome, {name}! Your {role} account is ready.", "ok")
            return redirect(url_for("dashboard"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q1("SELECT * FROM users WHERE email=?",
               (request.form.get("email","").strip().lower(),))
        if u and check_password_hash(u["password"], request.form.get("password","")):
            session.clear()
            session["uid"] = u["id"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ── Dashboard (role-aware) ────────────────────────────────────────────────────
@app.route("/dashboard")
@auth()
def dashboard():
    u = cur()

    if u["role"] == "volunteer":
        open_reqs = q("""
            SELECT r.*, u2.name vol_name
            FROM requests r
            LEFT JOIN users u2 ON u2.id = r.volunteer_id
            WHERE r.status IN ('Pending', 'Accepted', 'In Progress')
            ORDER BY CASE r.status
              WHEN 'Pending'     THEN 0
              WHEN 'Accepted'    THEN 1
              WHEN 'In Progress' THEN 2
              ELSE 3 END, r.created DESC
        """)
        my_tasks = q("""
            SELECT * FROM requests
            WHERE volunteer_id = ?
            ORDER BY CASE status
              WHEN 'Accepted'    THEN 0
              WHEN 'In Progress' THEN 1
              WHEN 'Completed'   THEN 2
              ELSE 3 END, created DESC
        """, (u["id"],))
        stats = {
            "pending": q1("SELECT COUNT(*) c FROM requests WHERE status='Pending'")["c"],
            "mine":    q1("SELECT COUNT(*) c FROM requests WHERE volunteer_id=? AND status!='Completed'", (u["id"],))["c"],
            "done":    q1("SELECT COUNT(*) c FROM requests WHERE volunteer_id=? AND status='Completed'", (u["id"],))["c"],
        }
        return render_template("vol_dashboard.html",
                               open_reqs=open_reqs, my_tasks=my_tasks, stats=stats)

    # NGO — full overview
    all_reqs = q("""
        SELECT r.*, u.name vol_name, u.phone vol_phone
        FROM requests r
        LEFT JOIN users u ON u.id = r.volunteer_id
        ORDER BY r.id DESC
    """)
    volunteers = q("SELECT * FROM users WHERE role='volunteer' ORDER BY name")
    resources  = q("SELECT * FROM resources ORDER BY category, name")
    stats = {
        "total":      q1("SELECT COUNT(*) c FROM requests")["c"],
        "pending":    q1("SELECT COUNT(*) c FROM requests WHERE status='Pending'")["c"],
        "active":     q1("SELECT COUNT(*) c FROM requests WHERE status IN ('Accepted','In Progress')")["c"],
        "completed":  q1("SELECT COUNT(*) c FROM requests WHERE status='Completed'")["c"],
        "volunteers": q1("SELECT COUNT(*) c FROM users WHERE role='volunteer'")["c"],
        "available":  q1("SELECT COUNT(*) c FROM users WHERE role='volunteer' AND available=1")["c"],
    }
    return render_template("ngo_dashboard.html",
                           all_reqs=all_reqs, volunteers=volunteers,
                           resources=resources, stats=stats)

# ── Volunteer actions ─────────────────────────────────────────────────────────
@app.route("/request/<int:rid>/accept", methods=["POST"])
@auth("volunteer")
def accept_request(rid):
    r = q1("SELECT * FROM requests WHERE id=?", (rid,))
    if not r or r["status"] != "Pending":
        flash("Request is no longer available.", "error")
        return redirect(url_for("dashboard"))
    u = cur()
    run("""UPDATE requests SET volunteer_id=?, status='Accepted', updated=CURRENT_TIMESTAMP
           WHERE id=?""", (u["id"], rid))
    run("UPDATE users SET available=0 WHERE id=?", (u["id"],))
    flash(f"You have accepted request #{rid}. Head to: {r['location']}", "ok")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:rid>/reject", methods=["POST"])
@auth("volunteer")
def reject_request(rid):
    r = q1("SELECT * FROM requests WHERE id=? AND volunteer_id=?", (rid, cur()["id"]))
    if not r:
        flash("Not your assigned request.", "error")
        return redirect(url_for("dashboard"))
    run("""UPDATE requests SET volunteer_id=NULL, status='Pending', updated=CURRENT_TIMESTAMP
           WHERE id=?""", (rid,))
    run("UPDATE users SET available=1 WHERE id=?", (cur()["id"],))
    flash(f"Request #{rid} released back to pending pool.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:rid>/progress", methods=["POST"])
@auth("volunteer")
def progress_request(rid):
    r = q1("SELECT * FROM requests WHERE id=? AND volunteer_id=?", (rid, cur()["id"]))
    if not r: return "Not found", 404
    new_status = {"Accepted": "In Progress", "In Progress": "Completed"}.get(r["status"])
    if not new_status:
        flash("Cannot update status.", "error")
        return redirect(url_for("dashboard"))
    run("UPDATE requests SET status=?, updated=CURRENT_TIMESTAMP WHERE id=?", (new_status, rid))
    if new_status == "Completed":
        run("UPDATE users SET available=1 WHERE id=?", (cur()["id"],))
        flash(f"✅ Request #{rid} marked as Completed. Thank you!", "ok")
    else:
        flash(f"Request #{rid} is now In Progress.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/volunteer/toggle-availability", methods=["POST"])
@auth("volunteer")
def toggle_availability():
    u = cur()
    new_val = 0 if u["available"] else 1
    run("UPDATE users SET available=? WHERE id=?", (new_val, u["id"]))
    flash("Availability updated.", "ok")
    return redirect(url_for("dashboard"))

# ── NGO-only actions ──────────────────────────────────────────────────────────
@app.route("/ngo/request/<int:rid>/status", methods=["POST"])
@auth("ngo")
def ngo_set_status(rid):
    status = request.form.get("status", "")
    if status not in ("Pending", "Accepted", "In Progress", "Completed", "Rejected"):
        flash("Invalid status.", "error")
        return redirect(url_for("dashboard"))
    run("UPDATE requests SET status=?, updated=CURRENT_TIMESTAMP WHERE id=?", (status, rid))
    if status == "Completed":
        r = q1("SELECT volunteer_id FROM requests WHERE id=?", (rid,))
        if r and r["volunteer_id"]:
            run("UPDATE users SET available=1 WHERE id=?", (r["volunteer_id"],))
    flash(f"Request #{rid} status set to {status}.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/ngo/request/<int:rid>/assign", methods=["POST"])
@auth("ngo")
def ngo_assign(rid):
    vol_id = request.form.get("volunteer_id")
    v = q1("SELECT * FROM users WHERE id=? AND role='volunteer'", (vol_id,))
    r = q1("SELECT * FROM requests WHERE id=?", (rid,))
    if not v or not r:
        flash("Invalid assignment.", "error")
        return redirect(url_for("dashboard"))
    run("""UPDATE requests SET volunteer_id=?, status='Accepted', updated=CURRENT_TIMESTAMP
           WHERE id=?""", (vol_id, rid))
    run("UPDATE users SET available=0 WHERE id=?", (vol_id,))
    flash(f"Request #{rid} assigned to {v['name']}.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/ngo/resources/add", methods=["POST"])
@auth("ngo")
def ngo_add_resource():
    f = request.form
    name = f.get("name","").strip(); qty = f.get("quantity","")
    cat  = f.get("category","").strip()
    try: qty = int(qty); assert qty > 0
    except: flash("Enter a valid quantity.", "error"); return redirect(url_for("dashboard"))
    if not name or not cat:
        flash("Name and category are required.", "error"); return redirect(url_for("dashboard"))
    run("INSERT INTO resources(name,category,quantity,unit,location,added_by) VALUES(?,?,?,?,?,?)",
        (name, cat, qty, f.get("unit","units").strip(), f.get("location","").strip(), cur()["id"]))
    flash("Resource added.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/ngo/resources/<int:rid>/restock", methods=["POST"])
@auth("ngo")
def ngo_restock(rid):
    try: qty = int(request.form.get("qty", 0)); assert qty > 0
    except: flash("Enter a valid quantity.", "error"); return redirect(url_for("dashboard"))
    run("UPDATE resources SET quantity=quantity+? WHERE id=?", (qty, rid))
    flash("Stock updated.", "ok")
    return redirect(url_for("dashboard"))

# ── API: new request count (for auto-refresh notification badge) ───────────────
@app.route("/api/pending-count")
@auth("volunteer")
def pending_count():
    c = q1("SELECT COUNT(*) c FROM requests WHERE status='Pending'")["c"]
    return jsonify({"count": c})

init_db()
if __name__ == "__main__":
    app.run(debug=True)
