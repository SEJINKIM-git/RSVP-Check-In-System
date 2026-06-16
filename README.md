# RSVP Check-In System

A web-based event attendance management system that replaces manual sign-in sheets with a fast, searchable, real-time check-in workflow for university information sessions and campus events.

**🔗 Live Demo:** https://spring26-rsvp-checkin-system-taupe.vercel.app/checkin/

> Built to eliminate the inefficiencies of manual attendance tracking — slow lookups, lost paper lists, no live headcount, and error-prone post-event reporting.

---

## Overview

The RSVP Check-In System streamlines on-site event operations from check-in to reporting, all from one focused dashboard. Staff import a participant list, search attendees by name or UNID (or scan a QR code), check in registered guests, register walk-ins on the spot, and review analytics on attendance trends — while a live dashboard tracks the running headcount in real time.

**Role:** Project Initiator & Backend Developer
The project was conceived and proposed to address real attendance-tracking pain points at campus events, then driven from concept through development. Backend functionality — data import/export, attendee search, check-in logic, guest registration, and the live dashboard — was implemented and integrated end to end.

Developed with TEK Club, University of Utah Asia Campus.

---

## Key Features

- **Live Dashboard** — A single overview showing current total attendance (checked-in RSVPs + recorded guests), RSVP statistics (total invited, checked in, check-in progress %), and guest registration count.
- **Registered Check-In** — Search the imported RSVP list by name or UNID and confirm participants without leaving the queue, including **QR code scanning** for fast entry.
- **Guest (Walk-In) Registration** — A focused manual-entry flow for on-site guests who weren't pre-registered.
- **Analytics** — Visualize check-in trends by hour and participant breakdown by major.
- **Data Tools** — Import participant lists and export attendance records (CSV/Excel).
- **Mobile-Friendly UI** — Responsive layout with a bottom navigation bar (Home · Scan · Guests · Tools) for quick on-site use.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python · Django |
| Data I/O | CSV / Excel Import-Export |
| Data Layer | Database Modeling (Django ORM) |
| Validation | Server-side Form Validation |
| Deployment | Vercel |

<!-- NOTE: Update this table if the deployed app uses a different stack (e.g. Next.js). -->

---

## Screenshots

<!-- Add screenshots or a short demo GIF here -->
<!-- Example:
![Dashboard](docs/dashboard.png)
![Check-In Screen](docs/checkin.png)
![Analytics](docs/analytics.png)
-->

_Coming soon — see the [live demo](https://spring26-rsvp-checkin-system-taupe.vercel.app/checkin/)._

---

## App Structure

| Route | Page | Purpose |
| --- | --- | --- |
| `/checkin/` | Dashboard | Live attendance overview and quick links to both check-in flows |
| `/checkin/registered/` | Registered Check-In | Search/scan and check in pre-registered participants |
| `/checkin/guest/` | Guest Registration | Manual entry for walk-in guests |
| `/checkin/analytics/` | Analytics | Check-in trends by hour and breakdown by major |
| `/checkin/import/` | Data Tools | Import RSVP lists and export attendance records |

---

## Getting Started

### Prerequisites

- Python 3.x
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/rsvp-checkin-system.git
cd rsvp-checkin-system

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply database migrations
python manage.py migrate

# 5. (Optional) Create an admin account
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

The app will be available at `http://127.0.0.1:8000/checkin/`.

---

## Usage

1. **Import a participant list** — Upload your RSVP CSV/Excel file under **Data Tools** to populate the event roster.
2. **Check in attendees** — Use **Registered Check-In** to search by name/UNID or scan a QR code, and confirm participants.
3. **Register walk-ins** — Use **Guest Registration** to add and check in unregistered guests on-site.
4. **Monitor the dashboard** — Watch live attendance: total invited, checked in, check-in progress %, and guest count.
5. **Review analytics** — See check-in trends by hour and participant breakdown by major.
6. **Export results** — Download the final attendance record for post-event reporting.

---

## Roles & Contributors

- **Sejin Kim** — Project Initiator & Backend Developer
- TEK Club, University of Utah Asia Campus — Co-developers

---

## License

<!-- Choose a license, e.g. MIT, and add a LICENSE file. -->
This project is licensed under the MIT License — see the `LICENSE` file for details.
