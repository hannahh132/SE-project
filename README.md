<<<<<<< HEAD
# Disaster Relief & Volunteer Management System

Flask + SQLite web app implementing the core features in the SRS.

## Run
    pip install -r requirements.txt
    python app.py            # open http://127.0.0.1:5000
    python seed_demo.py      # optional demo data (demo users use password: demo123)

Default admin: `admin@relief.com` / `admin123` (change after first login / before deployment).
Set `SECRET_KEY` env var for any real deployment.

## Roles
- **Victim**: submit emergency requests (food, water, medical, rescue, shelter), track status.
- **Volunteer**: register skills/availability, start and complete assigned requests.
- **NGO**: add/restock relief materials, record distributions against requests.
- **Admin**: assign volunteers, monitor all requests, manage users and roles, also manages resources.

## Structure
    app.py            routes, DB schema, role-based access
    templates/        Jinja pages    static/style.css   styling
    seed_demo.py      demo data
=======
# SE-project
>>>>>>> c89d8dc4816560052dd6d26eaf8fe82fd9b37cb7
