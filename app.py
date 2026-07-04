"""
فنّي (Fanni) — Pilot Backend
Flask + SQLite. Single-file API powering the customer booking flow,
technician onboarding, job lifecycle, parts approval, and ratings.

Run:      python3 app.py                 (dev, port 8000)
Prod:     gunicorn -w 2 -b 0.0.0.0:8000 app:app
Env:      FANNI_ADMIN_TOKEN  (default: change-me-admin)
          FANNI_DB           (default: fanni.db)
"""

import base64
import json
import os
import re
import secrets
import sqlite3
import string
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory

DB_PATH = os.environ.get("FANNI_DB", "fanni.db")
ADMIN_TOKEN = os.environ.get("FANNI_ADMIN_TOKEN", "change-me-admin")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)) if os.path.dirname(DB_PATH) else ".", "fanni_docs")
os.makedirs(DOCS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # document uploads

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name_en TEXT NOT NULL,
    name_ar TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs_catalog (
    id INTEGER PRIMARY KEY,
    service_id INTEGER NOT NULL REFERENCES services(id),
    title TEXT NOT NULL,
    detail TEXT,
    price_egp INTEGER NOT NULL,          -- fixed labor price
    is_inspection INTEGER DEFAULT 0      -- 1 = inspection fee deducted from repair
);

CREATE TABLE IF NOT EXISTS technicians (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    mobile TEXT UNIQUE NOT NULL,
    national_id_last4 TEXT,
    governorate TEXT,
    district TEXT,
    dob TEXT,
    documents TEXT,                       -- JSON {doc_key: filename}
    trades TEXT,                          -- comma-separated service slugs
    experience TEXT,
    transport TEXT,
    setup TEXT,
    status TEXT DEFAULT 'applied',        -- applied|assessment_booked|approved|suspended
    assessment_hub TEXT,
    assessment_slot TEXT,
    api_token TEXT UNIQUE,                -- issued on approval
    rating_avg REAL DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    jobs_done INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,            -- FN-XXXXX
    service_slug TEXT NOT NULL,
    job_catalog_id INTEGER NOT NULL REFERENCES jobs_catalog(id),
    customer_name TEXT,
    customer_mobile TEXT NOT NULL,
    area TEXT NOT NULL,
    address TEXT NOT NULL,
    notes TEXT,
    day TEXT NOT NULL,
    time_window TEXT NOT NULL,
    labor_egp INTEGER NOT NULL,
    service_fee_egp INTEGER NOT NULL DEFAULT 25,
    parts_egp INTEGER NOT NULL DEFAULT 0,
    total_egp INTEGER NOT NULL,
    payment_method TEXT DEFAULT 'cash',
    status TEXT DEFAULT 'new',            -- new|assigned|en_route|arrived|working|done|cancelled
    technician_id INTEGER REFERENCES technicians(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parts_quotes (
    id INTEGER PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    part_name TEXT NOT NULL,
    price_egp INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',        -- pending|approved|rejected
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY,
    booking_id INTEGER UNIQUE NOT NULL REFERENCES bookings(id),
    stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
    tags TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_quotes (
    id INTEGER PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    technician_id INTEGER NOT NULL REFERENCES technicians(id),
    extras_json TEXT,                     -- [{"name":..,"price_egp":..}] equipment/extra services
    extras_egp INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    status TEXT DEFAULT 'pending',        -- pending|accepted|rejected
    created_at TEXT NOT NULL,
    UNIQUE(booking_id, technician_id)
);

CREATE TABLE IF NOT EXISTS status_log (
    id INTEGER PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    status TEXT NOT NULL,
    at TEXT NOT NULL
);
"""

SEED_SERVICES = [
    ("ac", "Air Conditioning", "تكييف"),
    ("satellite", "Satellite & TV", "دش وتلفزيون"),
    ("cctv", "CCTV & Security", "كاميرات مراقبة"),
    ("wifi", "WiFi & Networking", "شبكات وإنترنت"),
    ("intercom", "Video Intercom", "إنتركم"),
    ("smart-home", "Smart Home", "منزل ذكي"),
]

SEED_JOBS = {
    "ac": [
        ("Deep cleaning & maintenance", "1.5 HP split, indoor + outdoor", 350, 0),
        ("Not cooling — diagnosis & repair", "Inspection deducted from repair", 150, 1),
        ("Freon refill (R410)", "Includes leak check", 600, 0),
        ("New AC installation", "Split unit, up to 4m piping", 900, 0),
    ],
    "satellite": [
        ("Dish install & alignment", "Single receiver, incl. 10m cable", 400, 0),
        ("Signal loss — realignment", "Existing dish", 250, 0),
        ("Receiver setup & channels", "Any receiver brand", 200, 0),
        ("TV wall mounting", "Up to 65\", bracket not included", 300, 0),
    ],
    "cctv": [
        ("4-camera package install", "Labor only, equipment quoted separately", 1200, 0),
        ("Camera not working — repair", "Inspection deducted from repair", 200, 1),
        ("Remote viewing setup", "Phone app + router config", 300, 0),
        ("NVR replacement / upgrade", "Reuse existing cabling", 500, 0),
    ],
    "wifi": [
        ("Mesh WiFi setup", "Up to 3 nodes + full-home survey", 500, 0),
        ("Weak signal — dead-zone fix", "Survey + repositioning or extender", 300, 0),
        ("New router install & config", "Any ISP", 250, 0),
        ("Network cabling", "Per point, in-wall or trunking", 350, 0),
    ],
    "intercom": [
        ("Video intercom install (apartment)", "Single unit", 400, 0),
        ("Villa / multi-unit intercom", "Site survey included", 900, 0),
        ("Intercom repair", "Inspection deducted from repair", 150, 1),
    ],
    "smart-home": [
        ("Smart lighting setup", "Up to 6 switches / bulbs + app", 600, 0),
        ("Smart lock install", "Includes door assessment", 450, 0),
        ("Smart camera & sensors", "Up to 3 devices + hub config", 550, 0),
        ("Full smart-home consultation", "On-site, deducted from project", 300, 1),
    ],
}

SERVICE_FEE = 25
COMMISSION_RATE = 0.20  # platform keeps 20% of labor


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    for col in ("dob TEXT", "documents TEXT"):
        try:
            db.execute(f"ALTER TABLE technicians ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass  # column already exists
    cur = db.execute("SELECT COUNT(*) FROM services")
    if cur.fetchone()[0] == 0:
        for slug, en, ar in SEED_SERVICES:
            db.execute(
                "INSERT INTO services (slug, name_en, name_ar) VALUES (?,?,?)",
                (slug, en, ar),
            )
        for slug, jobs in SEED_JOBS.items():
            sid = db.execute(
                "SELECT id FROM services WHERE slug=?", (slug,)
            ).fetchone()[0]
            for title, detail, price, insp in jobs:
                db.execute(
                    "INSERT INTO jobs_catalog (service_id,title,detail,price_egp,is_inspection)"
                    " VALUES (?,?,?,?,?)",
                    (sid, title, detail, price, insp),
                )
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gen_code(prefix="FN"):
    return f"{prefix}-{''.join(secrets.choice(string.digits) for _ in range(5))}"


def err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def valid_mobile(m):
    return bool(re.fullmatch(r"01[0-9]{9}", re.sub(r"\D", "", m or "")))


def log_status(db, booking_id, status):
    db.execute(
        "INSERT INTO status_log (booking_id,status,at) VALUES (?,?,?)",
        (booking_id, status, now()),
    )


def require_admin(f):
    @wraps(f)
    def wrapper(*a, **k):
        if request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
            return err("Admin token required", 401)
        return f(*a, **k)
    return wrapper


def require_technician(f):
    @wraps(f)
    def wrapper(*a, **k):
        token = request.headers.get("X-Tech-Token", "")
        tech = get_db().execute(
            "SELECT * FROM technicians WHERE api_token=? AND status='approved'",
            (token,),
        ).fetchone()
        if not tech:
            return err("Valid technician token required", 401)
        g.tech = tech
        return f(*a, **k)
    return wrapper


def booking_public(db, b):
    """Serialize a booking for customer-facing endpoints."""
    tech = None
    if b["technician_id"]:
        t = db.execute(
            "SELECT full_name, rating_avg, rating_count, jobs_done FROM technicians WHERE id=?",
            (b["technician_id"],),
        ).fetchone()
        if t:
            tech = {
                "name": t["full_name"],
                "rating": round(t["rating_avg"], 1),
                "jobs_done": t["jobs_done"],
            }
    parts = [
        dict(p)
        for p in db.execute(
            "SELECT id, part_name, price_egp, status FROM parts_quotes WHERE booking_id=?",
            (b["id"],),
        ).fetchall()
    ]
    history = [
        dict(h)
        for h in db.execute(
            "SELECT status, at FROM status_log WHERE booking_id=? ORDER BY id",
            (b["id"],),
        ).fetchall()
    ]
    return {
        "code": b["code"],
        "status": b["status"],
        "service": b["service_slug"],
        "day": b["day"],
        "time_window": b["time_window"],
        "area": b["area"],
        "labor_egp": b["labor_egp"],
        "service_fee_egp": b["service_fee_egp"],
        "parts_egp": b["parts_egp"],
        "total_egp": b["total_egp"],
        "payment_method": b["payment_method"],
        "technician": tech,
        "parts_quotes": parts,
        "history": history,
    }


# --------------------------------------------------------------------------
# Static frontend
# --------------------------------------------------------------------------

@app.get("/")
def home():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:page>")
def static_page(page):
    safe = os.path.basename(page)
    if safe.endswith(".html") and os.path.isfile(os.path.join(STATIC_DIR, safe)):
        return send_from_directory(STATIC_DIR, safe)
    return err("Not found", 404)


# --------------------------------------------------------------------------
# Public API — catalog
# --------------------------------------------------------------------------

@app.get("/api/services")
def list_services():
    db = get_db()
    out = []
    for s in db.execute("SELECT * FROM services ORDER BY id").fetchall():
        jobs = db.execute(
            "SELECT id, title, detail, price_egp, is_inspection"
            " FROM jobs_catalog WHERE service_id=? ORDER BY id",
            (s["id"],),
        ).fetchall()
        out.append(
            {
                "slug": s["slug"],
                "name_en": s["name_en"],
                "name_ar": s["name_ar"],
                "jobs": [dict(j) for j in jobs],
            }
        )
    return jsonify({"ok": True, "services": out, "service_fee_egp": SERVICE_FEE})


# --------------------------------------------------------------------------
# Public API — bookings
# --------------------------------------------------------------------------

@app.post("/api/bookings")
def create_booking():
    d = request.get_json(silent=True) or {}
    required = ["job_catalog_id", "customer_mobile", "area", "address", "day", "time_window"]
    missing = [k for k in required if not d.get(k)]
    if missing:
        return err(f"Missing fields: {', '.join(missing)}")
    if not valid_mobile(d["customer_mobile"]):
        return err("Mobile must be a valid Egyptian number (01XXXXXXXXX)")

    db = get_db()
    job = db.execute(
        "SELECT j.*, s.slug AS service_slug FROM jobs_catalog j"
        " JOIN services s ON s.id=j.service_id WHERE j.id=?",
        (d["job_catalog_id"],),
    ).fetchone()
    if not job:
        return err("Unknown job_catalog_id", 404)

    code = gen_code()
    total = job["price_egp"] + SERVICE_FEE
    cur = db.execute(
        """INSERT INTO bookings
           (code, service_slug, job_catalog_id, customer_name, customer_mobile,
            area, address, notes, day, time_window, labor_egp, service_fee_egp,
            total_egp, payment_method, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            code, job["service_slug"], job["id"], d.get("customer_name"),
            re.sub(r"\D", "", d["customer_mobile"]), d["area"], d["address"],
            d.get("notes"), d["day"], d["time_window"], job["price_egp"],
            SERVICE_FEE, total, d.get("payment_method", "cash"), now(), now(),
        ),
    )
    log_status(db, cur.lastrowid, "new")
    db.commit()
    return jsonify({"ok": True, "code": code, "total_egp": total,
                    "fixed_price": True, "warranty_days": 30}), 201


@app.get("/api/bookings/<code>")
def track_booking(code):
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    return jsonify({"ok": True, "booking": booking_public(db, b)})


@app.post("/api/bookings/<code>/parts/<int:part_id>/decision")
def decide_part(code, part_id):
    """Customer approves or rejects a quoted part."""
    d = request.get_json(silent=True) or {}
    decision = d.get("decision")
    if decision not in ("approved", "rejected"):
        return err("decision must be 'approved' or 'rejected'")
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    p = db.execute(
        "SELECT * FROM parts_quotes WHERE id=? AND booking_id=? AND status='pending'",
        (part_id, b["id"]),
    ).fetchone()
    if not p:
        return err("Pending part quote not found", 404)
    db.execute("UPDATE parts_quotes SET status=? WHERE id=?", (decision, part_id))
    if decision == "approved":
        db.execute(
            "UPDATE bookings SET parts_egp=parts_egp+?, total_egp=total_egp+?, updated_at=? WHERE id=?",
            (p["price_egp"], p["price_egp"], now(), b["id"]),
        )
    db.commit()
    b = db.execute("SELECT * FROM bookings WHERE id=?", (b["id"],)).fetchone()
    return jsonify({"ok": True, "booking": booking_public(db, b)})


@app.post("/api/bookings/<code>/rating")
def rate_booking(code):
    d = request.get_json(silent=True) or {}
    stars = d.get("stars")
    if not isinstance(stars, int) or not 1 <= stars <= 5:
        return err("stars must be an integer 1–5")
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    if b["status"] != "done":
        return err("Booking must be completed before rating", 409)
    try:
        db.execute(
            "INSERT INTO ratings (booking_id, stars, tags, comment, created_at) VALUES (?,?,?,?,?)",
            (b["id"], stars, ",".join(d.get("tags", [])), d.get("comment"), now()),
        )
    except sqlite3.IntegrityError:
        return err("Booking already rated", 409)
    if b["technician_id"]:
        t = db.execute("SELECT * FROM technicians WHERE id=?", (b["technician_id"],)).fetchone()
        new_count = t["rating_count"] + 1
        new_avg = (t["rating_avg"] * t["rating_count"] + stars) / new_count
        db.execute(
            "UPDATE technicians SET rating_avg=?, rating_count=? WHERE id=?",
            (new_avg, new_count, t["id"]),
        )
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Public API — technician application
# --------------------------------------------------------------------------

@app.post("/api/technicians/apply")
def technician_apply():
    d = request.get_json(silent=True) or {}
    required = ["full_name", "mobile", "national_id", "governorate", "district",
                "trades", "experience"]
    missing = [k for k in required if not d.get(k)]
    if missing:
        return err(f"Missing fields: {', '.join(missing)}")
    if not valid_mobile(d["mobile"]):
        return err("Mobile must be a valid Egyptian number (01XXXXXXXXX)")
    nid = re.sub(r"\D", "", d["national_id"])
    if len(nid) != 14:
        return err("National ID must be 14 digits")
    if not isinstance(d["trades"], list) or not d["trades"]:
        return err("trades must be a non-empty list")

    db = get_db()
    try:
        cur = db.execute(
            """INSERT INTO technicians
               (full_name, mobile, national_id_last4, dob, governorate, district,
                trades, experience, transport, setup, assessment_hub,
                assessment_slot, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d["full_name"], re.sub(r"\D", "", d["mobile"]), nid[-4:],
                d.get("dob"), d["governorate"], d["district"], ",".join(d["trades"]),
                d["experience"], d.get("transport"), ",".join(d.get("setup", [])),
                d.get("assessment_hub"), d.get("assessment_slot"),
                "assessment_booked" if d.get("assessment_slot") else "applied",
                now(),
            ),
        )
    except sqlite3.IntegrityError:
        return err("An application with this mobile already exists", 409)
    tech_id = cur.lastrowid
    # persist uploaded documents (base64 data URLs)
    docs_in = d.get("documents") or {}
    saved = {}
    for key in ("id_front", "id_back", "photo", "certificate"):
        data_url = docs_in.get(key)
        if not data_url or not isinstance(data_url, str):
            continue
        m = re.match(r"data:image/(png|jpe?g);base64,(.+)", data_url, re.I | re.S)
        if not m:
            continue
        ext = "png" if m.group(1).lower() == "png" else "jpg"
        try:
            blob = base64.b64decode(m.group(2), validate=True)
        except Exception:
            continue
        if len(blob) > 5 * 1024 * 1024:
            continue
        fname = f"tech{tech_id}_{key}.{ext}"
        with open(os.path.join(DOCS_DIR, fname), "wb") as f:
            f.write(blob)
        saved[key] = fname
    if saved:
        db.execute("UPDATE technicians SET documents=? WHERE id=?", (json.dumps(saved), tech_id))
    db.commit()
    ref = f"FN-2026-{tech_id:04d}"
    return jsonify({"ok": True, "reference": ref,
                    "next": "Documents review within 48h, then practical assessment."}), 201


# --------------------------------------------------------------------------
# Technician API (X-Tech-Token)
# --------------------------------------------------------------------------

@app.get("/api/tech/jobs")
@require_technician
def tech_open_jobs():
    db = get_db()
    trades = g.tech["trades"].split(",")
    q = ",".join("?" for _ in trades)
    rows = db.execute(
        f"""SELECT b.*, j.title FROM bookings b
            JOIN jobs_catalog j ON j.id=b.job_catalog_id
            WHERE b.status='new' AND b.service_slug IN ({q})
            ORDER BY b.created_at""",
        trades,
    ).fetchall()
    jobs = []
    for b in rows:
        mine = db.execute(
            "SELECT extras_egp, extras_json, status FROM job_quotes"
            " WHERE booking_id=? AND technician_id=?",
            (b["id"], g.tech["id"]),
        ).fetchone()
        jobs.append({
            "code": b["code"], "title": b["title"], "service": b["service_slug"],
            "area": b["area"], "day": b["day"], "time_window": b["time_window"],
            "notes": b["notes"], "listed_price_egp": b["labor_egp"],
            "you_earn_at_listed": round(b["labor_egp"] * (1 - COMMISSION_RATE)),
            "offer_count": db.execute(
                "SELECT COUNT(*) c FROM job_quotes WHERE booking_id=?", (b["id"],)
            ).fetchone()["c"],
            "my_offer": ({"extras_egp": mine["extras_egp"],
                          "extras": json.loads(mine["extras_json"] or "[]"),
                          "status": mine["status"]} if mine else None),
        })
    return jsonify({"ok": True, "jobs": jobs, "commission_rate": COMMISSION_RATE})


@app.post("/api/tech/jobs/<code>/offer")
@require_technician
def tech_offer_job(code):
    """Offer = take the job at the fixed labor price, plus optional
    equipment / extra-service line items quoted upfront."""
    d = request.get_json(silent=True) or {}
    items = d.get("items") or []
    if not isinstance(items, list) or len(items) > 15:
        return err("items must be a list (max 15)")
    clean = []
    for it in items:
        name = (it.get("name") or "").strip()[:120] if isinstance(it, dict) else ""
        price = it.get("price_egp") if isinstance(it, dict) else None
        if not name or not isinstance(price, int) or not 10 <= price <= 100000:
            return err("Each item needs a name and integer price_egp (10–100000)")
        clean.append({"name": name, "price_egp": price})
    extras = sum(i["price_egp"] for i in clean)
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=? AND status='new'", (code.upper(),)).fetchone()
    if not b:
        return err("Request not open for offers", 409)
    if b["service_slug"] not in g.tech["trades"].split(","):
        return err("This request is outside your trades", 403)
    db.execute(
        "INSERT INTO job_quotes (booking_id, technician_id, extras_json, extras_egp, note, created_at)"
        " VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(booking_id, technician_id)"
        " DO UPDATE SET extras_json=excluded.extras_json, extras_egp=excluded.extras_egp,"
        " note=excluded.note, created_at=excluded.created_at, status='pending'",
        (b["id"], g.tech["id"], json.dumps(clean, ensure_ascii=False), extras,
         (d.get("note") or "")[:300], now()),
    )
    db.commit()
    return jsonify({"ok": True, "code": b["code"], "labor_egp": b["labor_egp"],
                    "extras_egp": extras, "customer_total_add": extras,
                    "you_earn_egp": round(b["labor_egp"] * (1 - COMMISSION_RATE)) + extras,
                    "status": "pending"}), 201


@app.get("/api/tech/my")
@require_technician
def tech_my():
    db = get_db()
    t = g.tech
    jobs = db.execute(
        "SELECT b.code, b.status, b.day, b.time_window, b.area, b.address, b.notes,"
        " b.labor_egp, b.parts_egp, b.total_egp, b.customer_mobile, j.title"
        " FROM bookings b JOIN jobs_catalog j ON j.id=b.job_catalog_id"
        " WHERE b.technician_id=? AND b.status!='cancelled'"
        " ORDER BY CASE WHEN b.status='done' THEN 1 ELSE 0 END, b.updated_at DESC LIMIT 50",
        (t["id"],),
    ).fetchall()
    active, done = [], []
    for j in jobs:
        rec = dict(j)
        rec["you_earn_egp"] = round(j["labor_egp"] * (1 - COMMISSION_RATE))
        # customer contact only once the job is truly his and underway
        if j["status"] not in ("assigned", "en_route", "arrived", "working"):
            rec.pop("customer_mobile", None)
            rec.pop("address", None)
        (done if j["status"] == "done" else active).append(rec)
    earnings = round(sum(j["labor_egp"] for j in jobs if j["status"] == "done") * (1 - COMMISSION_RATE))
    return jsonify({"ok": True, "profile": {
        "name": t["full_name"], "trades": t["trades"].split(","),
        "district": t["district"], "rating_avg": round(t["rating_avg"], 1),
        "rating_count": t["rating_count"], "jobs_done": t["jobs_done"],
    }, "active_jobs": active, "done_jobs": done, "earnings_egp": earnings})


@app.post("/api/tech/jobs/<code>/accept")
@require_technician
def tech_accept(code):
    db = get_db()
    cur = db.execute(
        "UPDATE bookings SET status='assigned', technician_id=?, updated_at=?"
        " WHERE code=? AND status='new'",
        (g.tech["id"], now(), code.upper()),
    )
    if cur.rowcount == 0:
        return err("Job not available (already taken or not found)", 409)
    b = db.execute("SELECT id FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    log_status(db, b["id"], "assigned")
    db.commit()
    return jsonify({"ok": True, "code": code.upper(), "status": "assigned"})


VALID_TRANSITIONS = {
    "assigned": "en_route",
    "en_route": "arrived",
    "arrived": "working",
    "working": "done",
}


@app.post("/api/tech/jobs/<code>/status")
@require_technician
def tech_status(code):
    d = request.get_json(silent=True) or {}
    new_status = d.get("status")
    db = get_db()
    b = db.execute(
        "SELECT * FROM bookings WHERE code=? AND technician_id=?",
        (code.upper(), g.tech["id"]),
    ).fetchone()
    if not b:
        return err("Job not found for this technician", 404)
    if VALID_TRANSITIONS.get(b["status"]) != new_status:
        return err(f"Invalid transition {b['status']} → {new_status}", 409)
    if new_status == "done":
        pending = db.execute(
            "SELECT COUNT(*) c FROM parts_quotes WHERE booking_id=? AND status='pending'",
            (b["id"],),
        ).fetchone()["c"]
        if pending:
            return err("Resolve pending parts quotes before closing the job", 409)
        db.execute("UPDATE technicians SET jobs_done=jobs_done+1 WHERE id=?", (g.tech["id"],))
    db.execute(
        "UPDATE bookings SET status=?, updated_at=? WHERE id=?",
        (new_status, now(), b["id"]),
    )
    log_status(db, b["id"], new_status)
    db.commit()
    payout = round(b["labor_egp"] * (1 - COMMISSION_RATE)) if new_status == "done" else None
    return jsonify({"ok": True, "status": new_status, "payout_egp": payout})


@app.post("/api/tech/jobs/<code>/parts")
@require_technician
def tech_quote_part(code):
    d = request.get_json(silent=True) or {}
    if not d.get("part_name") or not isinstance(d.get("price_egp"), int) or d["price_egp"] <= 0:
        return err("part_name and positive integer price_egp required")
    db = get_db()
    b = db.execute(
        "SELECT * FROM bookings WHERE code=? AND technician_id=? AND status IN ('arrived','working')",
        (code.upper(), g.tech["id"]),
    ).fetchone()
    if not b:
        return err("Job must be yours and in arrived/working state", 409)
    cur = db.execute(
        "INSERT INTO parts_quotes (booking_id, part_name, price_egp, created_at) VALUES (?,?,?,?)",
        (b["id"], d["part_name"], d["price_egp"], now()),
    )
    db.commit()
    return jsonify({"ok": True, "part_id": cur.lastrowid, "status": "pending",
                    "note": "Customer must approve in-app before installation."}), 201


# --------------------------------------------------------------------------
# Admin API (X-Admin-Token)
# --------------------------------------------------------------------------

@app.get("/api/admin/bookings")
@require_admin
def admin_bookings():
    db = get_db()
    status = request.args.get("status")
    q = ("SELECT b.*, j.title AS job_title, t.full_name AS tech_name,"
         " t.rating_avg AS tech_rating, t.jobs_done AS tech_jobs,"
         " (SELECT COUNT(*) FROM job_quotes jq WHERE jq.booking_id=b.id"
         "   AND jq.status='pending') AS offer_count FROM bookings b"
         " JOIN jobs_catalog j ON j.id=b.job_catalog_id"
         " LEFT JOIN technicians t ON t.id=b.technician_id"
         + (" WHERE b.status=?" if status else "")
         + " ORDER BY b.created_at DESC")
    rows = db.execute(q, (status,) if status else ()).fetchall()
    return jsonify({"ok": True, "bookings": [dict(r) for r in rows]})


@app.get("/api/admin/applications")
@require_admin
def admin_applications():
    db = get_db()
    rows = db.execute(
        "SELECT t.id, t.full_name, t.mobile, t.national_id_last4, t.dob, t.governorate,"
        " t.district, t.trades, t.experience, t.transport, t.setup, t.status,"
        " t.assessment_hub, t.assessment_slot, t.rating_avg, t.rating_count,"
        " t.jobs_done, t.created_at, t.documents,"
        " (SELECT COUNT(*) FROM bookings b WHERE b.technician_id=t.id"
        "   AND b.status IN ('assigned','en_route','arrived','working')) AS active_jobs"
        " FROM technicians t ORDER BY t.created_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        rec = dict(r)
        rec["documents"] = sorted(json.loads(rec["documents"]).keys()) if rec["documents"] else []
        out.append(rec)
    return jsonify({"ok": True, "applications": out})


@app.post("/api/admin/technicians/<int:tech_id>/approve")
@require_admin
def admin_approve(tech_id):
    db = get_db()
    token = secrets.token_urlsafe(24)
    cur = db.execute(
        "UPDATE technicians SET status='approved', api_token=? WHERE id=? AND status!='approved'",
        (token, tech_id),
    )
    if cur.rowcount == 0:
        return err("Technician not found or already approved", 404)
    db.commit()
    return jsonify({"ok": True, "tech_id": tech_id, "api_token": token,
                    "note": "Deliver this token to the technician's app securely."})


@app.post("/api/admin/bookings/<code>/assign")
@require_admin
def admin_assign(code):
    d = request.get_json(silent=True) or {}
    tech_id = d.get("technician_id")
    if not isinstance(tech_id, int):
        return err("technician_id (integer) required")
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    if b["status"] not in ("new", "assigned"):
        return err(f"Cannot assign a booking in status '{b['status']}'", 409)
    t = db.execute(
        "SELECT * FROM technicians WHERE id=? AND status='approved'", (tech_id,)
    ).fetchone()
    if not t:
        return err("Technician not found or not approved", 404)
    if b["service_slug"] not in t["trades"].split(","):
        return err(f"Technician trades ({t['trades']}) do not cover '{b['service_slug']}'", 409)
    db.execute(
        "UPDATE bookings SET status='assigned', technician_id=?, updated_at=? WHERE id=?",
        (tech_id, now(), b["id"]),
    )
    log_status(db, b["id"], "assigned")
    db.commit()
    return jsonify({"ok": True, "code": b["code"], "status": "assigned",
                    "technician": t["full_name"]})


@app.post("/api/admin/bookings/<code>/cancel")
@require_admin
def admin_cancel(code):
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    if b["status"] in ("done", "cancelled"):
        return err(f"Cannot cancel a booking in status '{b['status']}'", 409)
    db.execute("UPDATE bookings SET status='cancelled', updated_at=? WHERE id=?", (now(), b["id"]))
    log_status(db, b["id"], "cancelled")
    db.commit()
    return jsonify({"ok": True, "code": b["code"], "status": "cancelled"})


@app.get("/api/admin/technicians/<int:tech_id>")
@require_admin
def admin_tech_profile(tech_id):
    db = get_db()
    t = db.execute("SELECT * FROM technicians WHERE id=?", (tech_id,)).fetchone()
    if not t:
        return err("Technician not found", 404)
    rec = dict(t)
    rec.pop("api_token", None)
    rec["documents"] = sorted(json.loads(rec["documents"]).keys()) if rec["documents"] else []
    jobs = db.execute(
        "SELECT b.code, b.status, b.day, b.time_window, b.area, b.total_egp, j.title"
        " FROM bookings b JOIN jobs_catalog j ON j.id=b.job_catalog_id"
        " WHERE b.technician_id=? ORDER BY b.created_at DESC LIMIT 50", (tech_id,)
    ).fetchall()
    rec["bookings"] = [dict(x) for x in jobs]
    rec["active_jobs"] = sum(1 for x in jobs if x["status"] in ("assigned", "en_route", "arrived", "working"))
    return jsonify({"ok": True, "technician": rec})


@app.get("/api/admin/technicians/<int:tech_id>/doc/<key>")
@require_admin
def admin_tech_doc(tech_id, key):
    db = get_db()
    t = db.execute("SELECT documents FROM technicians WHERE id=?", (tech_id,)).fetchone()
    if not t or not t["documents"]:
        return err("No documents", 404)
    docs = json.loads(t["documents"])
    fname = docs.get(key)
    if not fname or not os.path.isfile(os.path.join(DOCS_DIR, fname)):
        return err("Document not found", 404)
    return send_from_directory(DOCS_DIR, fname)


@app.delete("/api/admin/technicians/<int:tech_id>")
@require_admin
def admin_tech_delete(tech_id):
    db = get_db()
    t = db.execute("SELECT * FROM technicians WHERE id=?", (tech_id,)).fetchone()
    if not t:
        return err("Technician not found", 404)
    # release their open jobs back to the pool
    open_jobs = db.execute(
        "SELECT id FROM bookings WHERE technician_id=?"
        " AND status IN ('assigned','en_route','arrived','working')", (tech_id,)
    ).fetchall()
    for j in open_jobs:
        db.execute("UPDATE bookings SET status='new', technician_id=NULL, updated_at=? WHERE id=?",
                   (now(), j["id"]))
        log_status(db, j["id"], "new")
    db.execute("UPDATE bookings SET technician_id=NULL WHERE technician_id=?", (tech_id,))
    if t["documents"]:
        for fname in json.loads(t["documents"]).values():
            try:
                os.remove(os.path.join(DOCS_DIR, fname))
            except OSError:
                pass
    db.execute("DELETE FROM job_quotes WHERE technician_id=?", (tech_id,))
    db.execute("DELETE FROM technicians WHERE id=?", (tech_id,))
    db.commit()
    return jsonify({"ok": True, "deleted": tech_id, "jobs_released": len(open_jobs)})


@app.get("/api/admin/bookings/<code>/full")
@require_admin
def admin_booking_full(code):
    db = get_db()
    b = db.execute(
        "SELECT b.*, j.title AS job_title, t.full_name AS tech_name, t.mobile AS tech_mobile,"
        " t.rating_avg AS tech_rating FROM bookings b"
        " JOIN jobs_catalog j ON j.id=b.job_catalog_id"
        " LEFT JOIN technicians t ON t.id=b.technician_id"
        " WHERE b.code=?", (code.upper(),)
    ).fetchone()
    if not b:
        return err("Booking not found", 404)
    rec = dict(b)
    offers = db.execute(
        "SELECT q.id, q.extras_json, q.extras_egp, q.note, q.status, q.created_at,"
        " t.id AS technician_id, t.full_name, t.rating_avg, t.jobs_done,"
        " (SELECT COUNT(*) FROM bookings x WHERE x.technician_id=t.id"
        "   AND x.status IN ('assigned','en_route','arrived','working')) AS active_jobs"
        " FROM job_quotes q JOIN technicians t ON t.id=q.technician_id"
        " WHERE q.booking_id=? ORDER BY q.extras_egp", (b["id"],)).fetchall()
    rec["offers"] = []
    for q in offers:
        o = dict(q)
        o["items"] = json.loads(o.pop("extras_json") or "[]")
        rec["offers"].append(o)
    rec["parts_quotes"] = [dict(p) for p in db.execute(
        "SELECT id, part_name, price_egp, status, created_at FROM parts_quotes WHERE booking_id=?",
        (b["id"],)).fetchall()]
    rec["history"] = [dict(h) for h in db.execute(
        "SELECT status, at FROM status_log WHERE booking_id=? ORDER BY id", (b["id"],)).fetchall()]
    r = db.execute("SELECT stars, tags, comment FROM ratings WHERE booking_id=?", (b["id"],)).fetchone()
    rec["rating"] = dict(r) if r else None
    return jsonify({"ok": True, "booking": rec})


@app.post("/api/admin/offers/<int:offer_id>/accept")
@require_admin
def admin_accept_offer(offer_id):
    db = get_db()
    q = db.execute("SELECT * FROM job_quotes WHERE id=? AND status='pending'", (offer_id,)).fetchone()
    if not q:
        return err("Pending offer not found", 404)
    b = db.execute("SELECT * FROM bookings WHERE id=?", (q["booking_id"],)).fetchone()
    if b["status"] != "new":
        return err(f"Booking is already '{b['status']}'", 409)
    # labor stays at the fixed catalog price; extras become pre-approved parts
    items = json.loads(q["extras_json"] or "[]")
    for it in items:
        db.execute(
            "INSERT INTO parts_quotes (booking_id, part_name, price_egp, status, created_at)"
            " VALUES (?,?,?,'approved',?)",
            (b["id"], it["name"], it["price_egp"], now()),
        )
    new_total = b["labor_egp"] + b["service_fee_egp"] + b["parts_egp"] + q["extras_egp"]
    db.execute(
        "UPDATE bookings SET status='assigned', technician_id=?,"
        " parts_egp=parts_egp+?, total_egp=?, updated_at=? WHERE id=?",
        (q["technician_id"], q["extras_egp"], new_total, now(), b["id"]),
    )
    db.execute("UPDATE job_quotes SET status='accepted' WHERE id=?", (offer_id,))
    db.execute("UPDATE job_quotes SET status='rejected' WHERE booking_id=? AND id!=?",
               (b["id"], offer_id))
    log_status(db, b["id"], "assigned")
    db.commit()
    t = db.execute("SELECT full_name FROM technicians WHERE id=?", (q["technician_id"],)).fetchone()
    return jsonify({"ok": True, "code": b["code"], "technician": t["full_name"],
                    "labor_egp": b["labor_egp"], "extras_egp": q["extras_egp"],
                    "total_egp": new_total})


@app.delete("/api/admin/bookings/<code>")
@require_admin
def admin_booking_delete(code):
    db = get_db()
    b = db.execute("SELECT id FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    db.execute("DELETE FROM job_quotes WHERE booking_id=?", (b["id"],))
    db.execute("DELETE FROM parts_quotes WHERE booking_id=?", (b["id"],))
    db.execute("DELETE FROM ratings WHERE booking_id=?", (b["id"],))
    db.execute("DELETE FROM status_log WHERE booking_id=?", (b["id"],))
    db.execute("DELETE FROM bookings WHERE id=?", (b["id"],))
    db.commit()
    return jsonify({"ok": True, "deleted": code.upper()})


@app.get("/api/admin/stats")
@require_admin
def admin_stats():
    db = get_db()
    def one(q, *p):
        return db.execute(q, p).fetchone()[0]
    gmv = one("SELECT COALESCE(SUM(total_egp),0) FROM bookings WHERE status='done'")
    labor = one("SELECT COALESCE(SUM(labor_egp),0) FROM bookings WHERE status='done'")
    return jsonify({"ok": True, "stats": {
        "bookings_total": one("SELECT COUNT(*) FROM bookings"),
        "bookings_done": one("SELECT COUNT(*) FROM bookings WHERE status='done'"),
        "gmv_egp": gmv,
        "platform_revenue_egp": round(labor * COMMISSION_RATE)
                                + SERVICE_FEE * one("SELECT COUNT(*) FROM bookings WHERE status='done'"),
        "technicians_approved": one("SELECT COUNT(*) FROM technicians WHERE status='approved'"),
        "applications_pending": one("SELECT COUNT(*) FROM technicians WHERE status IN ('applied','assessment_booked')"),
        "avg_rating": round(one("SELECT COALESCE(AVG(stars),0) FROM ratings"), 2),
    }})


# --------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
