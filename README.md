# fny
# فنّي (Fanni) — Pilot Backend

Flask + SQLite. Serves the website AND the API from one process.

## Run locally
    pip install -r requirements.txt
    python3 app.py            # http://localhost:8000

## Deploy (Railway / Render / any VPS)
    Start command:  gunicorn -w 2 -b 0.0.0.0:$PORT app:app
    Env vars:       FANNI_ADMIN_TOKEN=<strong-secret>   (required in prod!)
                    FANNI_DB=/data/fanni.db             (persistent disk path)

## API map
    Public
      GET  /api/services                          price catalog
      POST /api/bookings                          create booking → {code, total_egp}
      GET  /api/bookings/<code>                   tracking (status, tech, parts, history)
      POST /api/bookings/<code>/parts/<id>/decision   {"decision":"approved"|"rejected"}
      POST /api/bookings/<code>/rating            {"stars":1-5,"tags":[...]}
      POST /api/technicians/apply                 onboarding application

    Technician (header X-Tech-Token)
      GET  /api/tech/jobs                         open jobs in his trades (+ his cut)
      POST /api/tech/jobs/<code>/accept
      POST /api/tech/jobs/<code>/status           assigned→en_route→arrived→working→done
      POST /api/tech/jobs/<code>/parts            quote part (blocks close until decided)

    Admin (header X-Admin-Token)
      GET  /api/admin/bookings[?status=]
      GET  /api/admin/applications
      POST /api/admin/technicians/<id>/approve    issues the tech's API token
      GET  /api/admin/stats                       GMV, platform revenue, ratings

## Business rules encoded
    - Fixed labor price + EGP 25 service fee, locked at booking
    - 20% platform commission on labor (technician sees his net upfront)
    - Parts must be customer-approved in-app before job can close
    - Ratings only after completion; one per booking; updates tech average
    - Status transitions enforced server-side (no skipping states)

## Pilot → production notes
    - Swap SQLite for Postgres when concurrent load grows
    - Add SMS (customer notifications) via Vodafone/WE gateway or Twilio
    - Add OTP login for customers; move tech tokens to proper auth
    - Document/photo uploads: S3-compatible storage (uploads are stubbed in UI)