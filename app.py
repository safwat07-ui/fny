"""
فنّي (Fanni) — Pilot Backend
Flask + SQLite. Single-file API powering the customer booking flow,
technician onboarding, job lifecycle, parts approval, and ratings.

Run:      python3 app.py                 (dev, port 8000)
Prod:     gunicorn -w 2 -b 0.0.0.0:8000 app:app
Env:      FANNI_ADMIN_TOKEN  (default: change-me-admin)
          FANNI_DB           (default: fanni.db)
"""

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

app = Flask(__name__, static_folder=None)

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
    try:
        db.execute("ALTER TABLE technicians ADD COLUMN dob TEXT")
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
    db.commit()
    ref = f"FN-2026-{cur.lastrowid:04d}"
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
        jobs.append({
            "code": b["code"], "title": b["title"], "service": b["service_slug"],
            "area": b["area"], "day": b["day"], "time_window": b["time_window"],
            "notes": b["notes"], "customer_price_egp": b["labor_egp"],
            "you_earn_egp": round(b["labor_egp"] * (1 - COMMISSION_RATE)),
        })
    return jsonify({"ok": True, "jobs": jobs})


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
    q = ("SELECT b.*, j.title AS job_title, t.full_name AS tech_name FROM bookings b"
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
        "SELECT id, full_name, mobile, national_id_last4, dob, governorate, district,"
        " trades, experience, transport, setup, status, assessment_hub,"
        " assessment_slot, rating_avg, rating_count, jobs_done, created_at"
        " FROM technicians ORDER BY created_at DESC"
    ).fetchall()
    return jsonify({"ok": True, "applications": [dict(r) for r in rows]})


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
