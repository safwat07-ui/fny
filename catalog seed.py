"""
فنّي (Fanni) — starter parts & products catalog.

Seeded once into the `products` table on first boot (only when the table is
empty). After that, the admin dashboard is the source of truth: edit prices,
costs, stock and availability there — this file is never re-applied.

Prices are INDICATIVE Egyptian-market figures (EGP, Q4 2026) meant as a
starting point. Verify every cost against current supplier quotes before
launch; parts prices move with the dollar rate.

Row: (sku, services, kind, category, name_en, name_ar, unit, cost_egp, price_egp)
  services  comma-separated service slugs the item is offered under
  kind      'part'    = spare part / consumable used during a repair or install
            'product' = complete device the customer buys (AC unit, camera kit…)
  unit      pc | m | kg | pack | set | roll

Default stock policy (editable per item in the admin):
  products → Fanni-supplied from inventory (stock tracked, platform revenue)
  parts    → technician-supplied at the fixed catalog price (no stock tracking)
"""

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
