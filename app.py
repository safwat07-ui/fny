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
import hashlib
import hmac as hmac_lib
import json
import threading
import urllib.request
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
# WhatsApp Cloud API (optional — notifications no-op until configured)
WA_TOKEN = os.environ.get("WA_TOKEN", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
ADMIN_WHATSAPP = os.environ.get("ADMIN_WHATSAPP", "")          # e.g. 2010XXXXXXXX
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
# Paymob (optional — online payment disabled until configured)
PAYMOB_API_KEY = os.environ.get("PAYMOB_API_KEY", "")
PAYMOB_INTEGRATION_ID = os.environ.get("PAYMOB_INTEGRATION_ID", "")
PAYMOB_IFRAME_ID = os.environ.get("PAYMOB_IFRAME_ID", "")
PAYMOB_HMAC = os.environ.get("PAYMOB_HMAC", "")
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
    payment_status TEXT DEFAULT 'unpaid',  -- unpaid|paid|refunded
    paymob_order_id TEXT,
    txn_id TEXT,
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

-- Parts & products catalog (spare parts + devices a customer can be quoted)
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    sku TEXT UNIQUE NOT NULL,
    services TEXT NOT NULL,               -- comma-separated service slugs
    kind TEXT NOT NULL DEFAULT 'part',    -- part|product
    category TEXT,
    name_en TEXT NOT NULL,
    name_ar TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'pc',      -- pc|m|kg|pack|set|roll
    cost_egp INTEGER NOT NULL DEFAULT 0,  -- Fanni's purchase cost (never shown to techs/customers)
    price_egp INTEGER NOT NULL,           -- fixed customer price per unit
    track_stock INTEGER NOT NULL DEFAULT 0, -- 1 = Fanni-supplied from inventory; 0 = tech sources it
    stock_qty INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_moves (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    delta INTEGER NOT NULL,               -- + in, - out
    qty_after INTEGER NOT NULL,
    reason TEXT NOT NULL,                 -- restock|adjust|damaged|job_use|job_return
    booking_id INTEGER,
    note TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_log (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,                   -- set for catalog items
    job_catalog_id INTEGER,               -- set for labor prices
    field TEXT NOT NULL,                  -- price|cost
    old_egp INTEGER,
    new_egp INTEGER NOT NULL,
    note TEXT,
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

# --------------------------------------------------------------------------
# Starter parts & products catalog
# --------------------------------------------------------------------------
# فنّي (Fanni) — starter parts & products catalog.
#
# Seeded once into the `products` table on first boot (only when the table is
# empty). After that, the admin dashboard is the source of truth: edit prices,
# costs, stock and availability there — this file is never re-applied.
#
# Prices are INDICATIVE Egyptian-market figures (EGP, Q4 2026) meant as a
# starting point. Verify every cost against current supplier quotes before
# launch; parts prices move with the dollar rate.
#
# Row: (sku, services, kind, category, name_en, name_ar, unit, cost_egp, price_egp)
#   services  comma-separated service slugs the item is offered under
#   kind      'part'    = spare part / consumable used during a repair or install
#             'product' = complete device the customer buys (AC unit, camera kit…)
#   unit      pc | m | kg | pack | set | roll
#
# Default stock policy (editable per item in the admin):
#   products → Fanni-supplied from inventory (stock tracked, platform revenue)
#   parts    → technician-supplied at the fixed catalog price (no stock tracking)

CATALOG = [
    # ───────────────────────── Air conditioning ─────────────────────────
    ("AC-CAP-35", "ac", "part", "Electrical", "Compressor run capacitor 35µF", "مكثف كمبروسر 35 ميكرو", "pc", 180, 280),
    ("AC-CAP-45", "ac", "part", "Electrical", "Compressor run capacitor 45µF", "مكثف كمبروسر 45 ميكرو", "pc", 210, 320),
    ("AC-CAP-FAN", "ac", "part", "Electrical", "Fan motor capacitor 2–5µF", "مكثف مروحة 2–5 ميكرو", "pc", 70, 120),
    ("AC-OLP", "ac", "part", "Electrical", "Compressor overload protector", "أوفرلود كمبروسر", "pc", 90, 160),
    ("AC-CONT-30", "ac", "part", "Electrical", "Outdoor contactor 2-pole 30A", "كونتاكتور وحدة خارجية 30 أمبير", "pc", 250, 400),
    ("AC-BRK-20", "ac", "part", "Electrical", "Circuit breaker 20A", "قاطع كهرباء 20 أمبير", "pc", 150, 250),
    ("AC-VPROT", "ac", "part", "Electrical", "AC voltage protector", "جهاز حماية جهد للتكييف", "pc", 450, 700),
    ("AC-CBL-25", "ac", "part", "Electrical", "Power cable 3×2.5mm", "كابل كهرباء 3×2.5 مم", "m", 60, 95),
    ("AC-GAS-R410", "ac", "part", "Refrigerant", "Refrigerant R410A", "فريون R410A", "kg", 500, 800),
    ("AC-GAS-R32", "ac", "part", "Refrigerant", "Refrigerant R32", "فريون R32", "kg", 450, 750),
    ("AC-GAS-R22", "ac", "part", "Refrigerant", "Refrigerant R22", "فريون R22", "kg", 380, 650),
    ("AC-DRIER", "ac", "part", "Refrigerant", "Filter drier", "فلتر درير", "pc", 80, 150),
    ("AC-SVALVE", "ac", "part", "Refrigerant", "Service valve", "بلف سيرفيس", "pc", 250, 400),
    ("AC-MOT-IN", "ac", "part", "Motors & fans", "Indoor fan motor (split)", "موتور مروحة داخلية", "pc", 900, 1400),
    ("AC-MOT-OUT", "ac", "part", "Motors & fans", "Outdoor fan motor", "موتور مروحة خارجية", "pc", 1100, 1700),
    ("AC-BLOWER", "ac", "part", "Motors & fans", "Indoor cross-flow blower", "مروحة اسطوانية (بلاور)", "pc", 500, 800),
    ("AC-SWING", "ac", "part", "Motors & fans", "Swing (louver) motor", "موتور ريشة", "pc", 150, 260),
    ("AC-COMP-15", "ac", "part", "Motors & fans", "Rotary compressor 1.5HP", "كمبروسر روتاري 1.5 حصان", "pc", 6500, 8500),
    ("AC-PCB-UNI", "ac", "part", "Boards & sensors", "Universal indoor control board", "كارتة تكييف يونيفرسال", "pc", 900, 1450),
    ("AC-SNS-ROOM", "ac", "part", "Boards & sensors", "Room temperature sensor", "حساس حرارة الغرفة", "pc", 60, 120),
    ("AC-SNS-PIPE", "ac", "part", "Boards & sensors", "Pipe (coil) sensor", "حساس الماسورة", "pc", 60, 120),
    ("AC-REMOTE", "ac", "part", "Boards & sensors", "Universal AC remote", "ريموت تكييف يونيفرسال", "pc", 120, 200),
    ("AC-PIPE-38", "ac", "part", "Piping & installation", "Insulated copper pipe ¼+⅜ (≤1.5HP)", "مواسير نحاس معزولة ¼+⅜ (حتى 1.5 حصان)", "m", 380, 550),
    ("AC-PIPE-12", "ac", "part", "Piping & installation", "Insulated copper pipe ¼+½ (2.25–3HP)", "مواسير نحاس معزولة ¼+½ (2.25–3 حصان)", "m", 480, 700),
    ("AC-DRAIN", "ac", "part", "Piping & installation", "Drain hose", "خرطوم صرف", "m", 15, 30),
    ("AC-TAPE", "ac", "part", "Piping & installation", "Insulation tape", "شريط عزل", "roll", 25, 50),
    ("AC-FLARE", "ac", "part", "Piping & installation", "Flare nut set", "طقم صواميل فلير", "set", 40, 80),
    ("AC-BRKT", "ac", "part", "Piping & installation", "Outdoor unit wall bracket", "حامل الوحدة الخارجية", "pc", 350, 550),
    ("AC-FILTER", "ac", "part", "Consumables", "Indoor air filter set", "طقم فلاتر هواء", "set", 80, 150),
    ("AC-CLEAN", "ac", "part", "Consumables", "Coil cleaning spray", "سبراي تنظيف المبخر", "pc", 120, 200),
    ("AC-U-15C", "ac", "product", "AC units", "Split AC 1.5HP cool only", "تكييف سبليت 1.5 حصان بارد", "pc", 28000, 31500),
    ("AC-U-15INV", "ac", "product", "AC units", "Split AC 1.5HP inverter cool/heat", "تكييف سبليت 1.5 حصان إنفرتر بارد/ساخن", "pc", 34000, 38000),
    ("AC-U-225C", "ac", "product", "AC units", "Split AC 2.25HP cool only", "تكييف سبليت 2.25 حصان بارد", "pc", 35000, 39000),
    ("AC-U-3C", "ac", "product", "AC units", "Split AC 3HP cool only", "تكييف سبليت 3 حصان بارد", "pc", 44000, 49000),

    # ───────────────────────── Satellite & TV ─────────────────────────
    ("SAT-LNB-1", "satellite", "part", "Dish & LNB", "LNB single", "LNB سنجل", "pc", 90, 160),
    ("SAT-LNB-2", "satellite", "part", "Dish & LNB", "LNB twin", "LNB توين", "pc", 150, 250),
    ("SAT-LNB-4", "satellite", "part", "Dish & LNB", "LNB quad", "LNB كواد", "pc", 260, 400),
    ("SAT-DISH-90", "satellite", "part", "Dish & LNB", "Satellite dish 90cm", "طبق دش 90 سم", "pc", 450, 700),
    ("SAT-DISH-120", "satellite", "part", "Dish & LNB", "Satellite dish 120cm", "طبق دش 120 سم", "pc", 750, 1100),
    ("SAT-MOUNT", "satellite", "part", "Mounting", "Dish wall/roof mount", "حامل طبق حائط/سطح", "pc", 150, 250),
    ("SAT-DISEQC", "satellite", "part", "Cabling", "DiSEqC switch 4×1", "ديسك 4×1", "pc", 90, 160),
    ("SAT-MSW-58", "satellite", "part", "Cabling", "Multiswitch 5×8", "مالتي سويتش 5×8", "pc", 900, 1400),
    ("SAT-RG6", "satellite", "part", "Cabling", "RG6 coaxial cable", "كابل كواكسيال RG6", "m", 8, 15),
    ("SAT-FCON", "satellite", "part", "Cabling", "F-connectors (pack of 10)", "فيش F (عبوة 10)", "pack", 25, 50),
    ("TV-HDMI-15", "satellite", "part", "Cabling", "HDMI cable 1.5m", "كابل HDMI 1.5 متر", "pc", 60, 120),
    ("TV-HDMI-5", "satellite", "part", "Cabling", "HDMI cable 5m", "كابل HDMI 5 متر", "pc", 140, 240),
    ("TV-BRKT-FIX", "satellite", "part", "Mounting", "TV wall bracket fixed (≤65\")", "حامل شاشة ثابت حتى 65 بوصة", "pc", 250, 400),
    ("TV-BRKT-MOV", "satellite", "part", "Mounting", "TV wall bracket tilt/swivel (≤65\")", "حامل شاشة متحرك حتى 65 بوصة", "pc", 650, 1000),
    ("TV-REMOTE", "satellite", "part", "TV repair", "Universal TV remote", "ريموت شاشة يونيفرسال", "pc", 80, 150),
    ("TV-LED-32", "satellite", "part", "TV repair", "LED backlight strip set 32\"", "طقم ليد شاشة 32 بوصة", "set", 350, 600),
    ("TV-LED-43", "satellite", "part", "TV repair", "LED backlight strip set 43\"", "طقم ليد شاشة 43 بوصة", "set", 550, 900),
    ("TV-LED-55", "satellite", "part", "TV repair", "LED backlight strip set 55\"", "طقم ليد شاشة 55 بوصة", "set", 900, 1400),
    ("TV-PSU-UNI", "satellite", "part", "TV repair", "Universal TV power supply board", "باور سبلاي شاشة يونيفرسال", "pc", 600, 1000),
    ("TV-MB-UNI", "satellite", "part", "TV repair", "Universal TV main board", "بوردة شاشة يونيفرسال", "pc", 1200, 1800),
    ("SAT-RCV-HD", "satellite", "product", "Receivers", "HD satellite receiver", "ريسيفر HD", "pc", 650, 950),
    ("SAT-RCV-4K", "satellite", "product", "Receivers", "4K Android receiver", "ريسيفر أندرويد 4K", "pc", 1800, 2500),
    ("TV-43-SMART", "satellite", "product", "TVs", "Smart TV 43\"", "شاشة سمارت 43 بوصة", "pc", 11000, 12500),
    ("TV-55-SMART", "satellite", "product", "TVs", "Smart TV 55\" 4K", "شاشة سمارت 55 بوصة 4K", "pc", 17500, 19900),

    # ───────────────────────── CCTV & security ─────────────────────────
    ("CC-BNC", "cctv", "part", "Connectors", "BNC connectors (pack of 10)", "فيش BNC (عبوة 10)", "pack", 30, 60),
    ("CC-DCJ", "cctv", "part", "Connectors", "DC power jacks (pack of 10)", "فيش باور DC (عبوة 10)", "pack", 25, 50),
    ("CC-BALUN", "cctv", "part", "Connectors", "Video balun (pair)", "بالون فيديو (زوج)", "set", 60, 110),
    ("CC-COAXPWR", "cctv", "part", "Cabling", "Coax + power combo cable", "كابل كواكسيال + باور", "m", 10, 18),
    ("CC-PSU-5A", "cctv", "part", "Power", "Power supply 12V 5A", "باور سبلاي 12 فولت 5 أمبير", "pc", 180, 300),
    ("CC-PSU-BOX", "cctv", "part", "Power", "Power box 12V 10A (9 channel)", "باور بوكس 12 فولت 10 أمبير 9 مخارج", "pc", 450, 700),
    ("CC-JBOX", "cctv", "part", "Mounting", "Camera junction box", "علبة توصيل كاميرا", "pc", 60, 110),
    ("CC-BRKT", "cctv", "part", "Mounting", "Camera wall bracket", "حامل كاميرا حائط", "pc", 40, 80),
    ("CC-HDD-1T", "cctv", "part", "Storage", "Surveillance hard disk 1TB", "هارد مراقبة 1 تيرا", "pc", 2200, 2900),
    ("CC-HDD-2T", "cctv", "part", "Storage", "Surveillance hard disk 2TB", "هارد مراقبة 2 تيرا", "pc", 3000, 3900),
    ("CC-POE-4", "cctv", "part", "Networking", "PoE switch 4-port", "سويتش PoE 4 مخارج", "pc", 900, 1300),
    ("CC-POE-8", "cctv", "part", "Networking", "PoE switch 8-port", "سويتش PoE 8 مخارج", "pc", 1500, 2100),
    ("CC-CAM-AD2", "cctv", "product", "Cameras", "2MP analog dome camera", "كاميرا دوم أنالوج 2 ميجا", "pc", 450, 700),
    ("CC-CAM-AB2", "cctv", "product", "Cameras", "2MP analog bullet camera", "كاميرا بوليت أنالوج 2 ميجا", "pc", 500, 750),
    ("CC-CAM-ID4", "cctv", "product", "Cameras", "4MP IP PoE dome camera", "كاميرا دوم IP PoE 4 ميجا", "pc", 1300, 1800),
    ("CC-CAM-IB4", "cctv", "product", "Cameras", "4MP IP PoE bullet camera", "كاميرا بوليت IP PoE 4 ميجا", "pc", 1400, 1950),
    ("CC-CAM-WIFI", "cctv,smart-home", "product", "Cameras", "WiFi smart indoor camera", "كاميرا واي فاي داخلية ذكية", "pc", 900, 1300),
    ("CC-DVR-4", "cctv", "product", "Recorders", "4-channel DVR", "جهاز تسجيل DVR 4 قنوات", "pc", 1300, 1800),
    ("CC-DVR-8", "cctv", "product", "Recorders", "8-channel DVR", "جهاز تسجيل DVR 8 قنوات", "pc", 1900, 2600),
    ("CC-NVR-4", "cctv", "product", "Recorders", "4-channel NVR", "جهاز تسجيل NVR 4 قنوات", "pc", 1800, 2500),
    ("CC-NVR-8P", "cctv", "product", "Recorders", "8-channel PoE NVR", "جهاز تسجيل NVR PoE 8 قنوات", "pc", 3800, 5000),
    ("CC-KIT-4A", "cctv", "product", "Kits", "4-camera kit 2MP (DVR + 1TB + PSU)", "باكدج 4 كاميرات 2 ميجا (DVR + هارد 1 تيرا + باور)", "set", 5200, 6900),
    ("CC-KIT-4IP", "cctv", "product", "Kits", "4-camera IP kit 4MP (PoE NVR + 1TB)", "باكدج 4 كاميرات IP 4 ميجا (NVR PoE + هارد 1 تيرا)", "set", 9800, 12900),

    # ───────────────────── Shared network cabling ─────────────────────
    ("NET-CAT6", "wifi,cctv,smart-home", "part", "Cabling", "CAT6 network cable", "كابل شبكة CAT6", "m", 14, 24),
    ("NET-RJ45", "wifi,cctv", "part", "Connectors", "RJ45 connectors (pack of 10)", "فيش RJ45 (عبوة 10)", "pack", 25, 50),
    ("NET-KEYST", "wifi", "part", "Connectors", "RJ45 keystone jack", "بريزة شبكة كيستون", "pc", 60, 100),
    ("NET-FACE1", "wifi", "part", "Connectors", "Network wall faceplate 1-port", "وش بريزة شبكة مخرج واحد", "pc", 40, 80),
    ("NET-PATCH1", "wifi,cctv", "part", "Cabling", "Patch cord 1m", "باتش كورد 1 متر", "pc", 40, 75),
    ("NET-PATCH3", "wifi,cctv", "part", "Cabling", "Patch cord 3m", "باتش كورد 3 متر", "pc", 60, 110),
    ("NET-TRUNK", "wifi,cctv,intercom", "part", "Installation", "Cable trunking", "مجرى كابلات (ترانكنج)", "m", 25, 45),
    ("NET-CONDUIT", "wifi,cctv,intercom", "part", "Installation", "PVC conduit", "خرطوم كهرباء PVC", "m", 15, 30),

    # ───────────────────────── WiFi & networking ─────────────────────────
    ("WF-RTR-AX", "wifi", "product", "Routers & mesh", "WiFi 6 dual-band router", "راوتر واي فاي 6 دوال باند", "pc", 1800, 2500),
    ("WF-MESH-2", "wifi", "product", "Routers & mesh", "Mesh WiFi system (2-pack)", "نظام ميش واي فاي (2 قطعة)", "set", 4500, 6000),
    ("WF-MESH-3", "wifi", "product", "Routers & mesh", "Mesh WiFi system (3-pack)", "نظام ميش واي فاي (3 قطع)", "set", 6500, 8500),
    ("WF-EXT", "wifi", "product", "Routers & mesh", "WiFi range extender", "مقوي إشارة واي فاي", "pc", 800, 1200),
    ("WF-AP", "wifi", "product", "Routers & mesh", "Ceiling access point", "أكسس بوينت سقف", "pc", 2200, 3000),
    ("WF-SW-8", "wifi", "product", "Switches & power", "Gigabit switch 8-port", "سويتش جيجابت 8 مخارج", "pc", 700, 1000),
    ("WF-PLC", "wifi", "product", "Switches & power", "Powerline adapter kit", "طقم باورلاين", "set", 1500, 2100),
    ("WF-UPS", "wifi", "product", "Switches & power", "Mini UPS for router", "يو بي إس للراوتر", "pc", 900, 1300),

    # ───────────────────────── Video intercom ─────────────────────────
    ("IC-CBL-4C", "intercom", "part", "Cabling", "Intercom cable 4-core", "كابل إنتركم 4 أسلاك", "m", 12, 22),
    ("IC-PSU", "intercom", "part", "Power", "Intercom power supply 12V 2A", "باور سبلاي إنتركم 12 فولت", "pc", 120, 200),
    ("IC-STRIKE", "intercom", "part", "Locks", "Electric door strike", "كالون كهربائي", "pc", 650, 950),
    ("IC-HANDSET", "intercom", "part", "Spare units", "Audio intercom handset", "سماعة إنتركم صوتي", "pc", 450, 700),
    ("IC-BUTTON", "intercom", "part", "Spare units", "Exit push button", "زرار خروج", "pc", 60, 110),
    ("IC-KIT-7", "intercom", "product", "Intercom kits", "Video intercom kit 7\" (1 apartment)", "طقم إنتركم فيديو 7 بوصة (شقة)", "set", 3800, 5000),
    ("IC-MON-7", "intercom", "product", "Intercom kits", "Extra indoor monitor 7\"", "شاشة داخلية إضافية 7 بوصة", "pc", 2200, 3000),
    ("IC-DOOR-1", "intercom", "product", "Door stations", "Outdoor door station 1-button", "وحدة باب خارجية زر واحد", "pc", 1500, 2100),
    ("IC-DOOR-4", "intercom", "product", "Door stations", "Multi-apartment door station (4 buttons)", "وحدة باب لعمارة (4 أزرار)", "pc", 2800, 3800),
    ("IC-WIFI-BELL", "intercom,smart-home", "product", "Door stations", "WiFi video doorbell", "جرس باب فيديو واي فاي", "pc", 2000, 2800),

    # ───────────────────────── Smart home ─────────────────────────
    ("SH-BAT-CR2032", "smart-home", "part", "Consumables", "CR2032 batteries (pack of 5)", "بطاريات CR2032 (عبوة 5)", "pack", 50, 90),
    ("SH-BAT-AA", "smart-home", "part", "Consumables", "AA batteries (pack of 4)", "بطاريات AA (عبوة 4)", "pack", 60, 100),
    ("SH-BOX", "smart-home", "part", "Installation", "Deep wall back box", "علبة حائط عميقة", "pc", 25, 50),
    ("SH-SW-1", "smart-home", "product", "Switches & lighting", "Smart wall switch 1-gang", "مفتاح ذكي خط واحد", "pc", 450, 700),
    ("SH-SW-2", "smart-home", "product", "Switches & lighting", "Smart wall switch 2-gang", "مفتاح ذكي خطين", "pc", 550, 850),
    ("SH-SW-3", "smart-home", "product", "Switches & lighting", "Smart wall switch 3-gang", "مفتاح ذكي 3 خطوط", "pc", 650, 950),
    ("SH-BULB", "smart-home", "product", "Switches & lighting", "Smart LED bulb E27", "لمبة ذكية E27", "pc", 300, 450),
    ("SH-PLUG", "smart-home", "product", "Switches & lighting", "Smart plug", "بريزة ذكية", "pc", 350, 550),
    ("SH-HUB", "smart-home", "product", "Hubs & sensors", "Smart home hub (Zigbee)", "هاب منزل ذكي Zigbee", "pc", 1200, 1700),
    ("SH-IR", "smart-home", "product", "Hubs & sensors", "Smart IR remote hub", "ريموت ذكي IR", "pc", 400, 650),
    ("SH-DOOR-S", "smart-home", "product", "Hubs & sensors", "Door/window sensor", "حساس باب/شباك", "pc", 350, 550),
    ("SH-MOTION", "smart-home", "product", "Hubs & sensors", "Motion sensor", "حساس حركة", "pc", 400, 600),
    ("SH-SMOKE", "smart-home", "product", "Hubs & sensors", "Smart smoke detector", "حساس دخان ذكي", "pc", 600, 900),
    ("SH-LEAK", "smart-home", "product", "Hubs & sensors", "Water leak sensor", "حساس تسريب مياه", "pc", 350, 550),
    ("SH-LOCK-FP", "smart-home", "product", "Locks & motors", "Fingerprint smart lock", "قفل ذكي ببصمة", "pc", 4500, 6500),
    ("SH-CURTAIN", "smart-home", "product", "Locks & motors", "Smart curtain motor", "موتور ستارة ذكي", "pc", 3500, 5000),
]


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
    for tbl, col in (("technicians", "dob TEXT"), ("technicians", "documents TEXT"),
                     ("bookings", "payment_status TEXT DEFAULT 'unpaid'"),
                     ("bookings", "paymob_order_id TEXT"), ("bookings", "txn_id TEXT"),
                     ("parts_quotes", "product_id INTEGER"),
                     ("parts_quotes", "qty INTEGER DEFAULT 1"),
                     ("parts_quotes", "unit_price_egp INTEGER"),
                     ("parts_quotes", "cost_egp INTEGER DEFAULT 0"),
                     ("parts_quotes", "supplied_by TEXT DEFAULT 'tech'"),
                     ("parts_quotes", "part_name_en TEXT"),
                     ("jobs_catalog", "active INTEGER DEFAULT 1")):
        try:
            db.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
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
    if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        ts = now()
        for sku, services, kind, cat, en, ar, unit, cost, price in CATALOG:
            tracked = 1 if kind == "product" else 0
            db.execute(
                "INSERT OR IGNORE INTO products (sku, services, kind, category, name_en, name_ar, unit,"
                " cost_egp, price_egp, track_stock, stock_qty, reorder_level, active,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,1,?,?)",
                (sku, services, kind, cat, en, ar, unit, cost, price, tracked,
                 2 if tracked else 0, ts, ts),
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


def _wa_send(phone, text):
    try:
        req = urllib.request.Request(
            f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages",
            data=json.dumps({"messaging_product": "whatsapp", "to": phone,
                             "type": "text", "text": {"body": text}}).encode(),
            headers={"Authorization": f"Bearer {WA_TOKEN}",
                     "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        print(f"[notify] failed to {phone}: {e}")


def notify(phone, text):
    """Fire-and-forget WhatsApp message. No-ops if the gateway isn't configured."""
    if not (WA_TOKEN and WA_PHONE_ID and phone):
        print(f"[notify-skip] {phone}: {text[:70]}")
        return
    to = "2" + re.sub(r"\D", "", phone)[-11:] if not str(phone).startswith("2") else str(phone)
    threading.Thread(target=_wa_send, args=(to, text), daemon=True).start()


def track_link(code, lang="ar"):
    base = PUBLIC_BASE_URL or ""
    return f"{base}/track.html?code={code}&lang={lang}"


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
            "SELECT id, part_name, part_name_en, qty, price_egp, status"
            " FROM parts_quotes WHERE booking_id=?",
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
        "payment_status": b["payment_status"] if "payment_status" in b.keys() else "unpaid",
        "payment_available": bool(PAYMOB_API_KEY and PAYMOB_INTEGRATION_ID and PAYMOB_IFRAME_ID),
        "technician": tech,
        "parts_quotes": parts,
        "history": history,
    }


# --------------------------------------------------------------------------
# Catalog & inventory helpers
# --------------------------------------------------------------------------

PRODUCT_UNITS = ("pc", "m", "kg", "pack", "set", "roll")
MAX_LINE_QTY = 100


def qty_label(name, qty):
    return name if qty == 1 else f"{name} ×{qty}"


def resolve_items(db, items, trades):
    """Turn technician line items into priced quote lines.

    Each item is either a catalog pick  {"product_id": int, "qty": int}
    (price, name and supply source come from the catalog — the tech can't change
    the price) or a custom line {"name": str, "price_egp": int} for anything
    not in the catalog. Returns (lines, error)."""
    if not isinstance(items, list) or len(items) > 15:
        return None, "items must be a list (max 15)"
    lines = []
    for it in items:
        if not isinstance(it, dict):
            return None, "Each item must be an object"
        if it.get("product_id") is not None:
            pid, qty = it.get("product_id"), it.get("qty", 1)
            if not isinstance(pid, int) or not isinstance(qty, int) or not 1 <= qty <= MAX_LINE_QTY:
                return None, f"Catalog items need integer product_id and qty (1–{MAX_LINE_QTY})"
            p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
            if not p:
                return None, "Catalog item not found or no longer available"
            if not set(p["services"].split(",")) & set(trades):
                return None, f"{p['name_en']} is outside your trades"
            if p["track_stock"] and p["stock_qty"] < qty:
                return None, f"Not enough stock for {p['name_ar']} (available: {p['stock_qty']})"
            lines.append({
                "product_id": p["id"], "qty": qty, "sku": p["sku"],
                "name": qty_label(p["name_ar"], qty), "name_en": qty_label(p["name_en"], qty),
                "unit_price_egp": p["price_egp"], "price_egp": p["price_egp"] * qty,
                "cost_egp": p["cost_egp"] * qty,
                "supplied_by": "fanni" if p["track_stock"] else "tech",
            })
        else:
            name = (it.get("name") or "").strip()[:120]
            price = it.get("price_egp")
            if not name or not isinstance(price, int) or not 10 <= price <= 100000:
                return None, "Each custom item needs a name and integer price_egp (10–100000)"
            lines.append({"product_id": None, "qty": 1, "name": name, "name_en": None,
                          "unit_price_egp": price, "price_egp": price, "cost_egp": 0,
                          "supplied_by": "tech"})
    return lines, None


def move_stock(db, product_id, delta, reason, booking_id=None, note=None):
    """Apply a stock movement. Outgoing moves never take stock below zero.
    Returns the new quantity, or None if there wasn't enough stock."""
    cur = db.execute(
        "UPDATE products SET stock_qty=stock_qty+?, updated_at=? WHERE id=? AND stock_qty+?>=0",
        (delta, now(), product_id, delta),
    )
    if cur.rowcount == 0:
        return None
    after = db.execute("SELECT stock_qty FROM products WHERE id=?", (product_id,)).fetchone()[0]
    db.execute(
        "INSERT INTO stock_moves (product_id, delta, qty_after, reason, booking_id, note, at)"
        " VALUES (?,?,?,?,?,?,?)",
        (product_id, delta, after, reason, booking_id, note, now()),
    )
    return after


def consume_part(db, part, booking_id):
    """Deduct Fanni-supplied stock for an approved part line. Returns error or None."""
    if part["supplied_by"] != "fanni" or not part["product_id"]:
        return None
    if move_stock(db, part["product_id"], -(part["qty"] or 1), "job_use", booking_id) is None:
        return "Out of stock — this item can no longer be supplied. Contact Fanni support."
    return None


def release_booking_stock(db, booking_id):
    """Return Fanni-supplied stock for a booking that won't complete."""
    for p in db.execute(
        "SELECT product_id, qty FROM parts_quotes WHERE booking_id=? AND status='approved'"
        " AND supplied_by='fanni' AND product_id IS NOT NULL", (booking_id,)
    ).fetchall():
        move_stock(db, p["product_id"], p["qty"] or 1, "job_return", booking_id)


def insert_part_line(db, booking_id, line, status):
    return db.execute(
        "INSERT INTO parts_quotes (booking_id, part_name, part_name_en, price_egp, status,"
        " product_id, qty, unit_price_egp, cost_egp, supplied_by, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (booking_id, line["name"], line.get("name_en"), line["price_egp"], status,
         line.get("product_id"), line.get("qty", 1), line.get("unit_price_egp"),
         line.get("cost_egp", 0), line.get("supplied_by", "tech"), now()),
    )


def tech_parts_egp(db, booking_id):
    """Approved parts the technician supplied himself (his money, not Fanni's)."""
    return db.execute(
        "SELECT COALESCE(SUM(price_egp),0) FROM parts_quotes WHERE booking_id=?"
        " AND status='approved' AND COALESCE(supplied_by,'tech')='tech'", (booking_id,)
    ).fetchone()[0]


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
            " FROM jobs_catalog WHERE service_id=? AND COALESCE(active,1)=1 ORDER BY id",
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
        " JOIN services s ON s.id=j.service_id WHERE j.id=? AND COALESCE(j.active,1)=1",
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
    notify(ADMIN_WHATSAPP,
           f"فنّي — طلب جديد {code}\n{job['title']}\n{d['area']} · {d['day']} {d['time_window']}\n"
           f"موبايل العميل: {re.sub(r'[^0-9]', '', d['customer_mobile'])}\nافتح اللوحة لتوزيعه.")
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
    if decision == "approved":
        problem = consume_part(db, p, b["id"])
        if problem:
            return err(problem, 409)
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
# Payments — Paymob (cards & wallets, Egypt)
# --------------------------------------------------------------------------

def _paymob_post(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


@app.post("/api/bookings/<code>/pay")
def start_payment(code):
    if not (PAYMOB_API_KEY and PAYMOB_INTEGRATION_ID and PAYMOB_IFRAME_ID):
        return err("Online payment is not configured yet — pay cash after the job.", 503)
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    if b["payment_status"] == "paid":
        return err("Already paid", 409)
    try:
        auth = _paymob_post("https://accept.paymob.com/api/auth/tokens",
                            {"api_key": PAYMOB_API_KEY})
        token = auth["token"]
        order = _paymob_post("https://accept.paymob.com/api/ecommerce/orders",
                             {"auth_token": token, "delivery_needed": "false",
                              "amount_cents": b["total_egp"] * 100, "currency": "EGP",
                              "merchant_order_id": f"{b['code']}-{int(datetime.now().timestamp())}",
                              "items": []})
        db.execute("UPDATE bookings SET paymob_order_id=?, payment_method='card' WHERE id=?",
                   (str(order["id"]), b["id"]))
        db.commit()
        pk = _paymob_post("https://accept.paymob.com/api/acceptance/payment_keys",
                          {"auth_token": token, "amount_cents": b["total_egp"] * 100,
                           "expiration": 3600, "order_id": order["id"],
                           "billing_data": {"first_name": (b["customer_name"] or "Customer").split(" ")[0],
                                            "last_name": (b["customer_name"] or "Fanni").split(" ")[-1],
                                            "phone_number": "+2" + b["customer_mobile"],
                                            "email": "na@fanni.eg", "apartment": "NA", "floor": "NA",
                                            "street": b["address"][:80], "building": "NA",
                                            "city": b["area"][:40], "country": "EG",
                                            "state": "NA", "postal_code": "NA", "shipping_method": "NA"},
                           "currency": "EGP", "integration_id": int(PAYMOB_INTEGRATION_ID)})
        iframe = (f"https://accept.paymob.com/api/acceptance/iframes/"
                  f"{PAYMOB_IFRAME_ID}?payment_token={pk['token']}")
        return jsonify({"ok": True, "iframe_url": iframe, "amount_egp": b["total_egp"]})
    except Exception as e:
        print(f"[paymob] {e}")
        return err("Payment gateway error — try again or pay cash.", 502)


@app.post("/api/payments/webhook")
def paymob_webhook():
    data = request.get_json(silent=True) or {}
    obj = data.get("obj") or {}
    if PAYMOB_HMAC:
        fields = ["amount_cents", "created_at", "currency", "error_occured",
                  "has_parent_transaction", "id", "integration_id", "is_3d_secure",
                  "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
                  "is_voided", "order", "owner", "pending",
                  "source_data.pan", "source_data.sub_type", "source_data.type", "success"]
        def dig(o, path):
            cur = o
            for p in path.split("."):
                cur = (cur or {}).get(p) if isinstance(cur, dict) else None
            if path == "order" and isinstance(cur, dict):
                cur = cur.get("id")
            return cur
        concat = "".join(str(dig(obj, f)).lower() if isinstance(dig(obj, f), bool)
                         else str(dig(obj, f)) for f in fields)
        calc = hmac_lib.new(PAYMOB_HMAC.encode(), concat.encode(), hashlib.sha512).hexdigest()
        if calc != (request.args.get("hmac") or data.get("hmac") or ""):
            return err("Invalid HMAC", 403)
    if not obj.get("success"):
        return jsonify({"ok": True, "ignored": True})
    order_id = str((obj.get("order") or {}).get("id", ""))
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE paymob_order_id=?", (order_id,)).fetchone()
    if not b:
        return err("Unknown order", 404)
    db.execute("UPDATE bookings SET payment_status='paid', txn_id=?, updated_at=? WHERE id=?",
               (str(obj.get("id", "")), now(), b["id"]))
    db.commit()
    notify(b["customer_mobile"], f"فنّي ✓ تم استلام دفعتك {b['total_egp']} جنيه لطلب {b['code']}. شكرًا!")
    notify(ADMIN_WHATSAPP, f"فنّي 💳 دفع أونلاين مؤكد: {b['code']} — {b['total_egp']} جنيه")
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
    db = get_db()
    clean, problem = resolve_items(db, d.get("items") or [], g.tech["trades"].split(","))
    if problem:
        return err(problem)
    extras = sum(i["price_egp"] for i in clean)
    tech_extras = sum(i["price_egp"] for i in clean if i["supplied_by"] == "tech")
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
                    "you_earn_egp": round(b["labor_egp"] * (1 - COMMISSION_RATE)) + tech_extras,
                    "status": "pending"}), 201


@app.get("/api/tech/my")
@require_technician
def tech_my():
    db = get_db()
    t = g.tech
    jobs = db.execute(
        "SELECT b.id, b.code, b.status, b.day, b.time_window, b.area, b.address, b.notes,"
        " b.labor_egp, b.parts_egp, b.total_egp, b.customer_mobile, j.title"
        " FROM bookings b JOIN jobs_catalog j ON j.id=b.job_catalog_id"
        " WHERE b.technician_id=? AND b.status!='cancelled'"
        " ORDER BY CASE WHEN b.status='done' THEN 1 ELSE 0 END, b.updated_at DESC LIMIT 50",
        (t["id"],),
    ).fetchall()
    active, done = [], []
    earnings = 0
    for j in jobs:
        rec = dict(j)
        rec["you_earn_egp"] = round(j["labor_egp"] * (1 - COMMISSION_RATE))
        bid = rec.pop("id")
        rec["tech_parts_egp"] = tech_parts_egp(db, bid)          # parts he supplied → his
        rec["fanni_parts_egp"] = (j["parts_egp"] or 0) - rec["tech_parts_egp"]  # from Fanni stock
        rec["parts"] = [dict(p) for p in db.execute(
            "SELECT part_name, qty, price_egp, status, COALESCE(supplied_by,'tech') AS supplied_by"
            " FROM parts_quotes WHERE booking_id=? ORDER BY id", (bid,)).fetchall()]
        if j["status"] == "done":
            earnings += rec["you_earn_egp"] + rec["tech_parts_egp"]
        # customer contact only once the job is truly his and underway
        if j["status"] not in ("assigned", "en_route", "arrived", "working"):
            rec.pop("customer_mobile", None)
            rec.pop("address", None)
        (done if j["status"] == "done" else active).append(rec)
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
    b = db.execute("SELECT * FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    log_status(db, b["id"], "assigned")
    db.commit()
    notify(b["customer_mobile"],
           f"فنّي ✓ الفني {g.tech['full_name']} ({round(g.tech['rating_avg'],1)}★) قبل طلبك {b['code']}\n"
           f"تابع طلبك: {track_link(b['code'])}")
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
    if new_status == "done":
        fresh = db.execute("SELECT total_egp FROM bookings WHERE id=?", (b["id"],)).fetchone()
        notify(b["customer_mobile"],
               f"فنّي ✓ اكتمل طلبك {b['code']}\nالإجمالي: {fresh['total_egp']} جنيه\n"
               f"ضمان ٣٠ يوم على الشغل 🛡️\nقيّم الفني: {track_link(b['code'])}")
    elif new_status == "en_route":
        notify(b["customer_mobile"], f"فنّي 🛵 الفني في الطريق إليك الآن — طلب {b['code']}")
    payout = round(b["labor_egp"] * (1 - COMMISSION_RATE)) if new_status == "done" else None
    return jsonify({"ok": True, "status": new_status, "payout_egp": payout})


@app.post("/api/tech/jobs/<code>/parts")
@require_technician
def tech_quote_part(code):
    """Quote a part found during the visit. Either a catalog item
    {"product_id", "qty"} at its fixed price, or a custom {"part_name", "price_egp"}."""
    d = request.get_json(silent=True) or {}
    if d.get("product_id") is not None:
        item = {"product_id": d.get("product_id"), "qty": d.get("qty", 1)}
    else:
        if not d.get("part_name") or not isinstance(d.get("price_egp"), int) or d["price_egp"] <= 0:
            return err("part_name and positive integer price_egp required (or a catalog product_id)")
        item = {"name": d["part_name"], "price_egp": d["price_egp"]}
    db = get_db()
    b = db.execute(
        "SELECT * FROM bookings WHERE code=? AND technician_id=? AND status IN ('arrived','working')",
        (code.upper(), g.tech["id"]),
    ).fetchone()
    if not b:
        return err("Job must be yours and in arrived/working state", 409)
    lines, problem = resolve_items(db, [item], g.tech["trades"].split(","))
    if problem:
        return err(problem)
    line = lines[0]
    cur = insert_part_line(db, b["id"], line, "pending")
    db.commit()
    return jsonify({"ok": True, "part_id": cur.lastrowid, "status": "pending",
                    "part_name": line["name"], "price_egp": line["price_egp"],
                    "supplied_by": line["supplied_by"],
                    "note": "Customer must approve in-app before installation."}), 201


@app.get("/api/tech/catalog")
@require_technician
def tech_catalog():
    """Parts & products for the technician's trades, at fixed customer prices.
    Costs are never exposed here."""
    db = get_db()
    trades = set(g.tech["trades"].split(","))
    out = []
    for p in db.execute("SELECT * FROM products WHERE active=1 ORDER BY kind, category, name_ar").fetchall():
        svcs = p["services"].split(",")
        if not trades & set(svcs):
            continue
        out.append({
            "id": p["id"], "sku": p["sku"], "services": svcs, "kind": p["kind"],
            "category": p["category"], "name_en": p["name_en"], "name_ar": p["name_ar"],
            "unit": p["unit"], "price_egp": p["price_egp"],
            "supplied_by": "fanni" if p["track_stock"] else "tech",
            "in_stock": (p["stock_qty"] if p["track_stock"] else None),
            "available": (not p["track_stock"]) or p["stock_qty"] > 0,
        })
    return jsonify({"ok": True, "items": out})


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
    release_booking_stock(db, b["id"])
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


@app.post("/api/admin/technicians/<int:tech_id>/reset-token")
@require_admin
def admin_tech_reset_token(tech_id):
    db = get_db()
    t = db.execute("SELECT * FROM technicians WHERE id=? AND status='approved'", (tech_id,)).fetchone()
    if not t:
        return err("Approved technician not found", 404)
    token = secrets.token_urlsafe(24)
    db.execute("UPDATE technicians SET api_token=? WHERE id=?", (token, tech_id))
    db.commit()
    return jsonify({"ok": True, "tech_id": tech_id, "api_token": token,
                    "note": "Old token is now invalid — the technician must log in again."})


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
        "SELECT id, part_name, qty, price_egp, status, COALESCE(supplied_by,'tech') AS supplied_by, created_at FROM parts_quotes WHERE booking_id=?",
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
        it.setdefault("supplied_by", "tech")
        it.setdefault("qty", 1)
        it.setdefault("product_id", None)
        problem = consume_part(db, it, b["id"])
        if problem:
            db.rollback()
            return err(f"{it['name']}: {problem}", 409)
        insert_part_line(db, b["id"], it, "approved")
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
    t = db.execute("SELECT full_name, rating_avg FROM technicians WHERE id=?", (q["technician_id"],)).fetchone()
    notify(b["customer_mobile"],
           f"فنّي ✓ تم تعيين فني لطلبك {b['code']}\n"
           f"الفني: {t['full_name']} ({round(t['rating_avg'],1)}★)\n"
           f"الإجمالي: {new_total} جنيه\nتابع طلبك: {track_link(b['code'])}")
    return jsonify({"ok": True, "code": b["code"], "technician": t["full_name"],
                    "labor_egp": b["labor_egp"], "extras_egp": q["extras_egp"],
                    "total_egp": new_total})


@app.delete("/api/admin/bookings/<code>")
@require_admin
def admin_booking_delete(code):
    db = get_db()
    b = db.execute("SELECT id, status FROM bookings WHERE code=?", (code.upper(),)).fetchone()
    if not b:
        return err("Booking not found", 404)
    if b["status"] not in ("done", "cancelled"):
        release_booking_stock(db, b["id"])   # parts never got used — back on the shelf
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
    supplied = "FROM parts_quotes p JOIN bookings b ON b.id=p.booking_id WHERE b.status='done'" \
               " AND p.status='approved' AND p.supplied_by='fanni'"
    parts_sales = one("SELECT COALESCE(SUM(p.price_egp),0) " + supplied)
    parts_margin = parts_sales - one("SELECT COALESCE(SUM(p.cost_egp),0) " + supplied)
    return jsonify({"ok": True, "stats": {
        "bookings_total": one("SELECT COUNT(*) FROM bookings"),
        "bookings_done": one("SELECT COUNT(*) FROM bookings WHERE status='done'"),
        "gmv_egp": gmv,
        "platform_revenue_egp": round(labor * COMMISSION_RATE)
                                + SERVICE_FEE * one("SELECT COUNT(*) FROM bookings WHERE status='done'")
                                + parts_margin,
        "parts_sales_egp": parts_sales,
        "parts_margin_egp": parts_margin,
        "inventory_value_egp": one("SELECT COALESCE(SUM(stock_qty*cost_egp),0) FROM products"
                                   " WHERE track_stock=1 AND stock_qty>0"),
        "low_stock_count": one("SELECT COUNT(*) FROM products WHERE active=1 AND track_stock=1"
                               " AND stock_qty<=reorder_level"),
        "technicians_approved": one("SELECT COUNT(*) FROM technicians WHERE status='approved'"),
        "applications_pending": one("SELECT COUNT(*) FROM technicians WHERE status IN ('applied','assessment_booked')"),
        "avg_rating": round(one("SELECT COALESCE(AVG(stars),0) FROM ratings"), 2),
    }})


# --------------------------------------------------------------------------
# Admin — inventory & pricing (X-Admin-Token)
# --------------------------------------------------------------------------

SERVICE_SLUGS = [s[0] for s in SEED_SERVICES]
PRODUCT_FIELDS = {  # field: (type, validator)
    "sku": str, "services": str, "kind": str, "category": str, "name_en": str,
    "name_ar": str, "unit": str, "cost_egp": int, "price_egp": int,
    "track_stock": int, "reorder_level": int, "active": int,
}


def product_admin(p):
    rec = dict(p)
    rec["services"] = p["services"].split(",")
    rec["margin_egp"] = p["price_egp"] - p["cost_egp"]
    rec["margin_pct"] = round(100 * (p["price_egp"] - p["cost_egp"]) / p["price_egp"], 1) if p["price_egp"] else 0
    rec["low_stock"] = bool(p["track_stock"] and p["active"] and p["stock_qty"] <= p["reorder_level"])
    return rec


def clean_product(d, partial=False):
    """Validate admin input for a catalog item. Returns (fields, error)."""
    out = {}
    for k, typ in PRODUCT_FIELDS.items():
        if k not in d:
            continue
        v = d[k]
        if k == "services" and isinstance(v, list):
            v = ",".join(v)
        if typ is int:
            if isinstance(v, bool):
                v = int(v)
            if not isinstance(v, int) or v < 0:
                return None, f"{k} must be a non-negative integer"
        else:
            v = (v or "").strip() if isinstance(v, str) else ""
        out[k] = v
    if "sku" in out:
        out["sku"] = out["sku"].upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{1,39}", out["sku"]):
            return None, "SKU: 2–40 letters, digits or dashes"
    if "services" in out:
        svcs = [s for s in out["services"].split(",") if s]
        if not svcs or any(s not in SERVICE_SLUGS for s in svcs):
            return None, f"services must be from: {', '.join(SERVICE_SLUGS)}"
        out["services"] = ",".join(dict.fromkeys(svcs))
    if "kind" in out and out["kind"] not in ("part", "product"):
        return None, "kind must be 'part' or 'product'"
    if "unit" in out and out["unit"] not in PRODUCT_UNITS:
        return None, f"unit must be one of: {', '.join(PRODUCT_UNITS)}"
    for k in ("name_en", "name_ar"):
        if k in out and not out[k]:
            return None, f"{k} is required"
    if "price_egp" in out and out["price_egp"] <= 0:
        return None, "price_egp must be greater than 0"
    for k in ("track_stock", "active"):
        if k in out:
            out[k] = 1 if out[k] else 0
    if not partial:
        missing = [k for k in ("sku", "services", "name_en", "name_ar", "price_egp") if k not in out]
        if missing:
            return None, f"Missing fields: {', '.join(missing)}"
    return out, None


def log_price(db, field, old, new, product_id=None, job_id=None, note=None):
    if old != new:
        db.execute(
            "INSERT INTO price_log (product_id, job_catalog_id, field, old_egp, new_egp, note, at)"
            " VALUES (?,?,?,?,?,?,?)", (product_id, job_id, field, old, new, note, now()))


@app.get("/api/admin/inventory")
@require_admin
def admin_inventory():
    db = get_db()
    rows = db.execute("SELECT * FROM products ORDER BY services, kind, category, name_en").fetchall()
    items = [product_admin(p) for p in rows]
    # units sold (completed jobs) per item, for spotting fast movers
    sold = {r["product_id"]: r["n"] for r in db.execute(
        "SELECT p.product_id, SUM(p.qty) n FROM parts_quotes p JOIN bookings b ON b.id=p.booking_id"
        " WHERE p.status='approved' AND p.product_id IS NOT NULL AND b.status='done'"
        " GROUP BY p.product_id").fetchall()}
    for it in items:
        it["sold_qty"] = sold.get(it["id"], 0)
    return jsonify({"ok": True, "items": items, "services": SERVICE_SLUGS, "units": PRODUCT_UNITS})


@app.post("/api/admin/inventory")
@require_admin
def admin_inventory_create():
    d = request.get_json(silent=True) or {}
    f, problem = clean_product(d)
    if problem:
        return err(problem)
    f.setdefault("kind", "part")
    f.setdefault("unit", "pc")
    f.setdefault("cost_egp", 0)
    f.setdefault("track_stock", 1 if f["kind"] == "product" else 0)
    f.setdefault("reorder_level", 0)
    f.setdefault("active", 1)
    f.setdefault("category", "")
    db = get_db()
    cols = list(f.keys()) + ["stock_qty", "created_at", "updated_at"]
    try:
        cur = db.execute(
            f"INSERT INTO products ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            list(f.values()) + [0, now(), now()])
    except sqlite3.IntegrityError:
        return err(f"SKU {f['sku']} already exists", 409)
    pid = cur.lastrowid
    opening = d.get("opening_stock")
    if isinstance(opening, int) and opening > 0:
        move_stock(db, pid, opening, "restock", note="Opening stock")
    db.commit()
    p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    return jsonify({"ok": True, "item": product_admin(p)}), 201


@app.patch("/api/admin/inventory/<int:pid>")
@require_admin
def admin_inventory_update(pid):
    d = request.get_json(silent=True) or {}
    f, problem = clean_product(d, partial=True)
    if problem:
        return err(problem)
    if not f:
        return err("Nothing to update")
    db = get_db()
    p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        return err("Item not found", 404)
    if p["track_stock"] and f.get("track_stock") == 0 and p["stock_qty"] > 0:
        return err(f"Write off or use the {p['stock_qty']} units in stock before turning off stock tracking", 409)
    log_price(db, "price", p["price_egp"], f.get("price_egp", p["price_egp"]), product_id=pid)
    log_price(db, "cost", p["cost_egp"], f.get("cost_egp", p["cost_egp"]), product_id=pid)
    sets = ", ".join(f"{k}=?" for k in f)
    try:
        db.execute(f"UPDATE products SET {sets}, updated_at=? WHERE id=?", list(f.values()) + [now(), pid])
    except sqlite3.IntegrityError:
        return err("That SKU is already used by another item", 409)
    db.commit()
    return jsonify({"ok": True, "item": product_admin(
        db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())})


@app.post("/api/admin/inventory/<int:pid>/stock")
@require_admin
def admin_inventory_stock(pid):
    """Stock movement: {"delta": +10, "reason": "restock", "note": "..."}
    or a count correction: {"set_qty": 7, "note": "stock take"}."""
    d = request.get_json(silent=True) or {}
    db = get_db()
    p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        return err("Item not found", 404)
    if not p["track_stock"]:
        return err("Stock isn't tracked for this item — turn on 'Fanni-supplied' first", 409)
    note = (d.get("note") or "").strip()[:200] or None
    if "set_qty" in d:
        target = d["set_qty"]
        if not isinstance(target, int) or target < 0:
            return err("set_qty must be a non-negative integer")
        delta, reason = target - p["stock_qty"], "adjust"
        if delta == 0:
            return jsonify({"ok": True, "item": product_admin(p)})
    else:
        delta, reason = d.get("delta"), d.get("reason", "restock")
        if not isinstance(delta, int) or delta == 0 or abs(delta) > 100000:
            return err("delta must be a non-zero integer")
        if reason not in ("restock", "adjust", "damaged"):
            return err("reason must be restock, adjust or damaged")
        if reason == "restock" and delta < 0:
            return err("A restock must add stock")
    if move_stock(db, pid, delta, reason, note=note) is None:
        return err(f"Only {p['stock_qty']} in stock", 409)
    # restock at a new purchase price → update cost (optional)
    unit_cost = d.get("unit_cost_egp")
    if reason == "restock" and isinstance(unit_cost, int) and unit_cost > 0 and unit_cost != p["cost_egp"]:
        log_price(db, "cost", p["cost_egp"], unit_cost, product_id=pid, note="restock")
        db.execute("UPDATE products SET cost_egp=? WHERE id=?", (unit_cost, pid))
    db.commit()
    return jsonify({"ok": True, "item": product_admin(
        db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())})


@app.get("/api/admin/inventory/<int:pid>/history")
@require_admin
def admin_inventory_history(pid):
    db = get_db()
    p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        return err("Item not found", 404)
    moves = [dict(m) for m in db.execute(
        "SELECT m.*, b.code AS booking_code FROM stock_moves m"
        " LEFT JOIN bookings b ON b.id=m.booking_id WHERE m.product_id=?"
        " ORDER BY m.id DESC LIMIT 100", (pid,)).fetchall()]
    prices = [dict(x) for x in db.execute(
        "SELECT field, old_egp, new_egp, note, at FROM price_log WHERE product_id=?"
        " ORDER BY id DESC LIMIT 50", (pid,)).fetchall()]
    return jsonify({"ok": True, "item": product_admin(p), "moves": moves, "prices": prices})


@app.post("/api/admin/inventory/reprice")
@require_admin
def admin_inventory_reprice():
    """Bulk price change, e.g. after a currency move:
    {"percent": 10, "field": "price"|"cost"|"both", "services": ["ac"], "kind": "part",
     "category": "Refrigerant", "ids": [..], "round_to": 5, "dry_run": true}"""
    d = request.get_json(silent=True) or {}
    pct = d.get("percent")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not -90 <= pct <= 500 or pct == 0:
        return err("percent must be a non-zero number between -90 and 500")
    field = d.get("field", "price")
    if field not in ("price", "cost", "both"):
        return err("field must be price, cost or both")
    round_to = d.get("round_to", 5)
    if not isinstance(round_to, int) or round_to not in (1, 5, 10, 50, 100):
        return err("round_to must be 1, 5, 10, 50 or 100")
    db = get_db()
    rows = db.execute("SELECT * FROM products").fetchall()
    svcs, kind, cat, ids = d.get("services") or [], d.get("kind"), d.get("category"), d.get("ids")
    def keep(p):
        if ids:
            return p["id"] in ids
        return ((not svcs or set(p["services"].split(",")) & set(svcs))
                and (not kind or p["kind"] == kind) and (not cat or p["category"] == cat))
    def bump(v):
        return max(round_to, int(round(v * (1 + pct / 100) / round_to)) * round_to) if v else v
    changes = []
    for p in filter(keep, rows):
        new_price = bump(p["price_egp"]) if field in ("price", "both") else p["price_egp"]
        new_cost = bump(p["cost_egp"]) if field in ("cost", "both") else p["cost_egp"]
        changes.append({"id": p["id"], "sku": p["sku"], "name_en": p["name_en"],
                        "price_from": p["price_egp"], "price_to": new_price,
                        "cost_from": p["cost_egp"], "cost_to": new_cost})
    if not d.get("dry_run"):
        note = f"bulk {pct:+g}%"
        for c in changes:
            log_price(db, "price", c["price_from"], c["price_to"], product_id=c["id"], note=note)
            log_price(db, "cost", c["cost_from"], c["cost_to"], product_id=c["id"], note=note)
            db.execute("UPDATE products SET price_egp=?, cost_egp=?, updated_at=? WHERE id=?",
                       (c["price_to"], c["cost_to"], now(), c["id"]))
        db.commit()
    return jsonify({"ok": True, "dry_run": bool(d.get("dry_run")), "count": len(changes),
                    "changes": changes})


@app.get("/api/admin/pricing/jobs")
@require_admin
def admin_pricing_jobs():
    """Fixed labor prices per job type (what the customer books)."""
    db = get_db()
    rows = db.execute(
        "SELECT j.id, j.title, j.detail, j.price_egp, j.is_inspection, COALESCE(j.active,1) AS active,"
        " s.slug AS service, s.name_en AS service_en, s.name_ar AS service_ar,"
        " (SELECT COUNT(*) FROM bookings b WHERE b.job_catalog_id=j.id) AS bookings"
        " FROM jobs_catalog j JOIN services s ON s.id=j.service_id ORDER BY s.id, j.id").fetchall()
    return jsonify({"ok": True, "jobs": [dict(r) for r in rows],
                    "service_fee_egp": SERVICE_FEE, "commission_rate": COMMISSION_RATE})


@app.patch("/api/admin/pricing/jobs/<int:job_id>")
@require_admin
def admin_pricing_job_update(job_id):
    """Change a job's labor price / text. Existing bookings keep the price they
    were booked at — only new bookings use the new price."""
    d = request.get_json(silent=True) or {}
    db = get_db()
    j = db.execute("SELECT * FROM jobs_catalog WHERE id=?", (job_id,)).fetchone()
    if not j:
        return err("Job type not found", 404)
    f = {}
    if "price_egp" in d:
        if not isinstance(d["price_egp"], int) or isinstance(d["price_egp"], bool) or not 10 <= d["price_egp"] <= 200000:
            return err("price_egp must be an integer 10–200000")
        f["price_egp"] = d["price_egp"]
    for k in ("title", "detail"):
        if k in d:
            v = (d[k] or "").strip()[:160]
            if k == "title" and not v:
                return err("title can't be empty")
            f[k] = v
    if "active" in d:
        f["active"] = 1 if d["active"] else 0
    if not f:
        return err("Nothing to update")
    log_price(db, "price", j["price_egp"], f.get("price_egp", j["price_egp"]), job_id=job_id)
    db.execute(f"UPDATE jobs_catalog SET {', '.join(k + '=?' for k in f)} WHERE id=?",
               list(f.values()) + [job_id])
    db.commit()
    return jsonify({"ok": True, "job": dict(db.execute(
        "SELECT id, title, detail, price_egp, is_inspection, COALESCE(active,1) AS active"
        " FROM jobs_catalog WHERE id=?", (job_id,)).fetchone())})


# --------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
