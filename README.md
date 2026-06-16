# RSVP Check-In System

A Django-based event attendance management system that replaces manual sign-in sheets with a fast, searchable, real-time check-in workflow for university information sessions and campus events.

> Built to eliminate the inefficiencies of manual attendance tracking — slow lookups, lost paper lists, no live headcount, and error-prone post-event reporting.

---

## Overview

The RSVP Check-In System streamlines on-site event operations from check-in to reporting. Staff can import a participant list, search attendees instantly by name or UNID, check in registered guests, register walk-ins on the spot, and export a clean attendance record after the event — all while watching live attendance numbers update on a dashboard.

**Role:** Project Initiator & Backend Developer
The project was conceived and proposed to address real attendance-tracking pain points at campus events, then driven from concept through development. Backend functionality (data import, search, check-in logic, exports, and the live dashboard) was implemented in Python/Django.

Developed with TEK Club, University of Utah Asia Campus.

---

## Key Features

- **Participant Import** — Bulk-import RSVP lists from CSV/Excel files.
- **Attendee Search** — Instant lookup by name or UNID for fast on-site check-in.
- **Registered Check-In** — One-action check-in for pre-registered attendees.
- **Walk-In Registration** — Register and check in unregistered guests at the door.
- **Real-Time Dashboard** — Live view of total RSVP count, checked-in attendees, guest (walk-in) count, and current total attendance.
- **Attendance Export** — Export the final attendance record (CSV/Excel) for post-event reporting.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python · Django |
| Data I/O | CSV / Excel Import-Export |
| Data Layer | Database Modeling (Django ORM) |
| Validation | Server-side Form Validation |

---

## Screenshots

<!-- Add screenshots or a short demo GIF here -->
<!-- Example:
![Dashboard](docs/dashboard.png)
![Check-In Screen](docs/checkin.png)
-->

_Coming soon._

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

The app will be available at `http://127.0.0.1:8000/`.

---

## Usage

1. **Import a participant list** — Upload your RSVP CSV/Excel file to populate the event roster.
2. **Check in attendees** — Search by name or UNID and check in registered guests with one action.
3. **Register walk-ins** — Add unregistered guests directly at the event.
4. **Monitor the dashboard** — Track live attendance: total RSVPs, checked-in count, walk-in count, and current total.
5. **Export results** — Download the final attendance record for reporting after the event.

---

## Project Structure

```
rsvp-checkin-system/
├── manage.py
├── requirements.txt
├── <project_name>/        # Django project settings
├── checkin/               # Core app: models, views, import/export, dashboard
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/
└── README.md
```

<!-- Update the structure above to match your actual repository layout. -->

---

## Roles & Contributors

- **Sejin Kim** — Project Initiator & Backend Developer
- TEK Club, University of Utah Asia Campus — Co-developers

---

## License

<!-- Choose a license, e.g. MIT, and add a LICENSE file. -->
This project is licensed under the MIT License — see the `LICENSE` file for details.
