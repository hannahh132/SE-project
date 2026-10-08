"""Optional: python seed_demo.py  -> adds demo users (password: demo123), resources and requests."""
from werkzeug.security import generate_password_hash as h
from app import app, run, q1, init_db
init_db()
with app.app_context():
    if q1("SELECT 1 FROM users WHERE email='victim@demo.com'"): raise SystemExit("Demo data already present.")
    pw = h("demo123")
    v = run("INSERT INTO users(name,email,phone,password,role) VALUES('Anil Kumar','victim@demo.com','9000000001',?,'victim')", (pw,)).lastrowid
    vol = run("INSERT INTO users(name,email,phone,password,role) VALUES('Meera Nair','volunteer@demo.com','9000000002',?,'volunteer')", (pw,)).lastrowid
    run("INSERT INTO users(name,email,phone,password,role) VALUES('Red Cross Kerala','ngo@demo.com','9000000003',?,'ngo')", (pw,))
    run("INSERT INTO volunteers(user_id,skills,location) VALUES(?,?,?)", (vol, "First aid, boat rescue", "Kottayam"))
    for n, c, qn, u in [("Rice", "Food", 500, "kg"), ("Drinking water", "Water", 40, "litres"), ("First-aid kits", "Medical", 15, "kits"), ("Tarpaulin", "Shelter", 80, "sheets")]:
        run("INSERT INTO resources(name,category,quantity,unit,location) VALUES(?,?,?,?,'Central warehouse')", (n, c, qn, u))
    run("INSERT INTO requests(victim_id,type,description,location,people,urgency) VALUES(?,?,?,?,?,?)",
        (v, "Rescue", "Family of 5 stranded on first floor, water rising.", "Kuttanad, Alappuzha", 5, "Critical"))
    run("INSERT INTO requests(victim_id,type,description,location,people,urgency) VALUES(?,?,?,?,?,?)",
        (v, "Food", "Need food packets for 2 days.", "Kottayam relief camp", 20, "High"))
    print("Demo data added.")
