import http.server
import socketserver
import sqlite3
import urllib.parse
import html
import json
import csv
import io
from datetime import date, datetime

PORT = 8000
DB = "smartswasthya.db"

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS households(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        locality TEXT NOT NULL,
        contact TEXT
    );
    CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT,
        phone TEXT,
        household_id INTEGER,
        created_at TEXT DEFAULT CURRENT_DATE,
        FOREIGN KEY(household_id) REFERENCES households(id)
    );
    CREATE TABLE IF NOT EXISTS health_records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        record_date TEXT NOT NULL,
        weight REAL,
        bp TEXT,
        temperature REAL,
        glucose REAL,
        notes TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );
    CREATE TABLE IF NOT EXISTS visits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        visit_date TEXT NOT NULL,
        purpose TEXT,
        notes TEXT,
        next_followup TEXT,
        status TEXT DEFAULT 'Completed',
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );
    CREATE TABLE IF NOT EXISTS preventive(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        activity TEXT,
        activity_date TEXT,
        status TEXT,
        notes TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );
    """)
    c.commit()
    c.close()

def seed():
    c = db()
    if c.execute("SELECT COUNT(*) FROM households").fetchone()[0] == 0:
        c.execute("INSERT INTO households(code,locality,contact) VALUES(?,?,?)",
                  ("H001","Shivaji Nagar","9876543210"))
        c.execute("INSERT INTO households(code,locality,contact) VALUES(?,?,?)",
                  ("H002","Kothrud","9876543211"))
        c.execute("INSERT INTO households(code,locality,contact) VALUES(?,?,?)",
                  ("H003","Hadapsar","9876543212"))
        c.execute("""INSERT INTO patients(name,age,gender,phone,household_id)
                     VALUES(?,?,?,?,?)""",
                  ("Rahul Sharma",45,"Male","9876500001",1))
        c.execute("""INSERT INTO patients(name,age,gender,phone,household_id)
                     VALUES(?,?,?,?,?)""",
                  ("Priya Patil",32,"Female","9876500002",2))
        c.execute("""INSERT INTO patients(name,age,gender,phone,household_id)
                     VALUES(?,?,?,?,?)""",
                  ("Amit Kumar",68,"Male","9876500003",3))
        c.execute("""INSERT INTO health_records
                     (patient_id,record_date,weight,bp,temperature,glucose,notes)
                     VALUES(?,?,?,?,?,?,?)""",
                  (1,"2026-08-10",72,"150/95",37.0,110,"Follow-up required"))
        c.execute("""INSERT INTO health_records
                     (patient_id,record_date,weight,bp,temperature,glucose,notes)
                     VALUES(?,?,?,?,?,?,?)""",
                  (2,"2026-09-01",60,"118/78",36.7,92,"Routine check"))
        c.execute("""INSERT INTO visits
                     (patient_id,visit_date,purpose,notes,next_followup,status)
                     VALUES(?,?,?,?,?,?)""",
                  (1,"2026-08-10","Follow-up","BP monitoring","2026-08-20","Completed"))
        c.execute("""INSERT INTO visits
                     (patient_id,visit_date,purpose,notes,next_followup,status)
                     VALUES(?,?,?,?,?,?)""",
                  (2,"2026-09-01","Routine","All normal","2026-10-01","Completed"))
        c.execute("""INSERT INTO preventive
                     (patient_id,activity,activity_date,status,notes)
                     VALUES(?,?,?,?,?)""",
                  (1,"Blood pressure screening","2026-08-10","Completed",""))
        c.commit()
    c.close()

def esc(x):
    return html.escape(str(x if x is not None else ""))

def priority(pid):
    c = db()
    p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    r = c.execute("SELECT * FROM health_records WHERE patient_id=? ORDER BY record_date DESC LIMIT 1",(pid,)).fetchone()
    v = c.execute("SELECT * FROM visits WHERE patient_id=? ORDER BY visit_date DESC LIMIT 1",(pid,)).fetchone()
    c.close()
    score, reasons = 0, []
    today = date.today()
    if v and v["next_followup"]:
        try:
            d = datetime.strptime(v["next_followup"], "%Y-%m-%d").date()
            if d < today:
                score += 3; reasons.append("Follow-up is overdue")
        except ValueError: pass
    if r and r["bp"]:
        try:
            systolic = int(r["bp"].split("/")[0])
            if systolic >= 140:
                score += 3; reasons.append("Recent systolic BP is 140 or above")
        except (ValueError, IndexError): pass
    if r and r["glucose"] is not None and r["glucose"] >= 200:
        score += 3; reasons.append("Recent glucose reading is high")
    if p and p["age"] >= 65:
        score += 1; reasons.append("Patient is in 65+ age group")
    if v:
        try:
            days = (today - datetime.strptime(v["visit_date"], "%Y-%m-%d").date()).days
            if days > 30:
                score += 2; reasons.append("No visit recorded in the last 30 days")
        except ValueError: pass
    else:
        score += 2; reasons.append("No visit has been recorded")
    level = "HIGH" if score >= 5 else "MEDIUM" if score >= 3 else "LOW"
    if not reasons: reasons = ["No current priority indicator"]
    return level, score, reasons

def layout(title, body, active=""):
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | SmartSwasthya</title>
<link rel="stylesheet" href="/static/style.css"><script src="/static/app.js"></script>
</head>
<body>
<header class="top">
  <div class="brand"><div class="logo">✚</div><div><b>SmartSwasthya</b><small>Community Health Intelligence</small></div></div>
  <nav>
    <a href="/">Dashboard</a><a href="/patients">Patients</a><a href="/households">Households</a>
    <a href="/priority">Priority</a><a href="/planner">Planner</a><a href="/reports">Reports</a>
  </nav>
</header>
<main class="wrap">{body}</main>
<footer>SmartSwasthya • CEP Project • Prototype for academic demonstration</footer>
</body></html>"""

def dashboard():
    c=db()
    h=c.execute("SELECT COUNT(*) FROM households").fetchone()[0]
    p=c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    v=c.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    r=c.execute("SELECT COUNT(*) FROM health_records").fetchone()[0]
    locality=c.execute("""SELECT h.locality,COUNT(p.id) n FROM households h
                          LEFT JOIN patients p ON p.household_id=h.id
                          GROUP BY h.locality ORDER BY n DESC""").fetchall()
    people=c.execute("SELECT * FROM patients ORDER BY id DESC LIMIT 5").fetchall()
    c.close()
    high=medium=low=0
    for x in db().execute("SELECT id FROM patients").fetchall():
        lv,_,_=priority(x["id"])
        if lv=="HIGH": high+=1
        elif lv=="MEDIUM": medium+=1
        else: low+=1
    local_labels=json.dumps([x["locality"] for x in locality])
    local_values=json.dumps([x["n"] for x in locality])
    recent="".join(f"<tr><td>{esc(x['name'])}</td><td>{x['age']}</td><td>{esc(x['gender'])}</td><td><a class='link' href='/patient?id={x['id']}'>Open</a></td></tr>" for x in people)
    body=f"""
    <section class="hero"><div><span class="eyebrow">COMMUNITY HEALTH • SMART WORKFLOW</span>
    <h1>Good morning, Health Worker 👋</h1><p>Manage households, health records and follow-ups from one place.</p>
    <a class="btn primary" href="/add_patient">＋ Add Patient</a>
    <a class="btn ghost" href="/priority">View Priority Cases</a></div>
    <div class="hero-art">🩺<span>Smart<br>Care</span></div></section>
    <div class="cards">
      <div class="stat"><span>Households</span><strong>{h}</strong><em>Registered</em></div>
      <div class="stat"><span>Patients</span><strong>{p}</strong><em>Active records</em></div>
      <div class="stat"><span>Health Records</span><strong>{r}</strong><em>Digital entries</em></div>
      <div class="stat"><span>Visits</span><strong>{v}</strong><em>Recorded</em></div>
    </div>
    <div class="grid2">
      <section class="panel"><div class="panelhead"><h2>Priority Overview</h2><a href="/priority">Details →</a></div>
        <div class="prioritybox"><div><b class="high">{high}</b><span>High</span></div><div><b class="medium">{medium}</b><span>Medium</span></div><div><b class="low">{low}</b><span>Low</span></div></div>
        <div class="bar"><i style="width:{min(high*25,100)}%"></i></div>
        <p class="muted">Priorities are explainable rule-based indicators for this academic prototype, not medical diagnoses.</p>
      </section>
      <section class="panel"><div class="panelhead"><h2>Patients by Locality</h2></div><canvas id="localityChart" height="170"></canvas></section>
    </div>
    <section class="panel"><div class="panelhead"><h2>Recently Added Patients</h2><a href="/patients">View all →</a></div>
    <table><tr><th>Name</th><th>Age</th><th>Gender</th><th>Action</th></tr>{recent}</table></section>
    <script>
    drawBars("localityChart",{local_labels},{local_values});
    </script>"""
    return layout("Dashboard",body)

def households():
    c=db(); rows=c.execute("SELECT * FROM households ORDER BY id DESC").fetchall(); c.close()
    tr="".join(f"<tr><td><b>{esc(x['code'])}</b></td><td>{esc(x['locality'])}</td><td>{esc(x['contact'])}</td></tr>" for x in rows)
    return layout("Households",f"""<div class="pagehead"><div><span class="eyebrow">COMMUNITY</span><h1>Households</h1><p>Organize patients by household and locality.</p></div><a class="btn primary" href="/add_household">＋ Add Household</a></div>
    <section class="panel"><table><tr><th>Household ID</th><th>Locality</th><th>Contact</th></tr>{tr}</table></section>""")

def add_household():
    return layout("Add Household",form_page("Add Household","/add_household",[
        ("Household ID","code","text","H004"),("Locality","locality","text","Locality name"),("Contact","contact","text","Phone number")]))

def patients():
    c=db(); rows=c.execute("""SELECT p.*,h.code,h.locality FROM patients p LEFT JOIN households h ON h.id=p.household_id ORDER BY p.id DESC""").fetchall(); c.close()
    tr=""
    for x in rows:
        lv,sc,_=priority(x["id"])
        tr+=f"""<tr><td><div class="person"><div class="avatar">{esc(x['name'][0].upper())}</div><div><b>{esc(x['name'])}</b><small>{esc(x['phone'])}</small></div></div></td>
        <td>{x['age']}</td><td>{esc(x['gender'])}</td><td>{esc(x['locality'])}</td><td><span class="pill {lv.lower()}">{lv}</span></td><td><a class="link" href="/patient?id={x['id']}">View →</a></td></tr>"""
    return layout("Patients",f"""<div class="pagehead"><div><span class="eyebrow">PATIENT DIRECTORY</span><h1>Patients</h1><p>Search and manage digital community health profiles.</p></div><a class="btn primary" href="/add_patient">＋ Add Patient</a></div>
    <section class="panel"><div class="search"><input id="patientSearch" placeholder="Search patient, locality or gender..." onkeyup="filterTable('patientSearch','patientTable')"></div>
    <table id="patientTable"><tr><th>Patient</th><th>Age</th><th>Gender</th><th>Locality</th><th>Priority</th><th>Action</th></tr>{tr}</table></section>""")

def add_patient():
    c=db(); hs=c.execute("SELECT * FROM households ORDER BY code").fetchall(); c.close()
    opts="".join(f"<option value='{x['id']}'>{esc(x['code'])} — {esc(x['locality'])}</option>" for x in hs)
    body=f"""<div class="pagehead"><div><span class="eyebrow">PATIENT MANAGEMENT</span><h1>Add Patient</h1><p>Create a new digital health profile.</p></div></div>
    <form class="form panel" method="POST" action="/add_patient">
      <div class="formgrid"><label>Full Name<input name="name" required></label><label>Age<input type="number" name="age" min="0" max="120" required></label>
      <label>Gender<select name="gender"><option>Female</option><option>Male</option><option>Other</option></select></label>
      <label>Phone<input name="phone"></label><label>Household<select name="household_id">{opts}</select></label></div>
      <button class="btn primary" type="submit">Save Patient</button><a class="btn ghost" href="/patients">Cancel</a>
    </form>"""
    return layout("Add Patient",body)

def patient(pid):
    c=db(); p=c.execute("""SELECT p.*,h.code,h.locality FROM patients p LEFT JOIN households h ON h.id=p.household_id WHERE p.id=?""",(pid,)).fetchone()
    if not p: c.close(); return layout("Not Found","<h1>Patient not found</h1>")
    rec=c.execute("SELECT * FROM health_records WHERE patient_id=? ORDER BY record_date DESC",(pid,)).fetchall()
    vis=c.execute("SELECT * FROM visits WHERE patient_id=? ORDER BY visit_date DESC",(pid,)).fetchall()
    prev=c.execute("SELECT * FROM preventive WHERE patient_id=? ORDER BY activity_date DESC",(pid,)).fetchall(); c.close()
    lv,sc,reasons=priority(pid)
    rr="".join(f"<tr><td>{esc(x['record_date'])}</td><td>{x['weight'] or '—'}</td><td>{esc(x['bp']) or '—'}</td><td>{x['temperature'] or '—'}</td><td>{x['glucose'] or '—'}</td><td>{esc(x['notes'])}</td></tr>" for x in rec)
    vr="".join(f"<tr><td>{esc(x['visit_date'])}</td><td>{esc(x['purpose'])}</td><td>{esc(x['next_followup']) or '—'}</td><td>{esc(x['status'])}</td></tr>" for x in vis)
    pr="".join(f"<tr><td>{esc(x['activity'])}</td><td>{esc(x['activity_date'])}</td><td>{esc(x['status'])}</td><td>{esc(x['notes'])}</td></tr>" for x in prev)
    why="".join(f"<li>{esc(x)}</li>" for x in reasons)
    body=f"""<div class="profiletop"><div class="profilecard panel"><div class="avatar big">{esc(p['name'][0].upper())}</div><div><span class="eyebrow">PATIENT PROFILE</span><h1>{esc(p['name'])}</h1><p>{x if False else p['age']} years • {esc(p['gender'])} • {esc(p['locality'])}</p><p class="muted">{esc(p['phone'])} • Household {esc(p['code'])}</p></div></div>
    <div class="risk panel"><span>Current Priority</span><b class="pill {lv.lower()}">{lv}</b><strong>{sc}</strong><small>priority score</small></div></div>
    <div class="actions"><a class="btn primary" href="/add_record?patient={pid}">＋ Health Record</a><a class="btn primary" href="/add_visit?patient={pid}">＋ Visit</a><a class="btn ghost" href="/add_preventive?patient={pid}">＋ Preventive Activity</a></div>
    <div class="grid2"><section class="panel"><div class="panelhead"><h2>Why this patient?</h2></div><ul class="why">{why}</ul></section><section class="panel"><div class="panelhead"><h2>Care Summary</h2></div><p>Use the latest recorded observations and follow-up information to support visit planning.</p><div class="notice">⚠ This system supports workflow prioritization; it does not diagnose illness.</div></section></div>
    <section class="panel"><div class="panelhead"><h2>Health Records</h2></div><table><tr><th>Date</th><th>Weight</th><th>BP</th><th>Temperature</th><th>Glucose</th><th>Notes</th></tr>{rr}</table></section>
    <section class="panel"><div class="panelhead"><h2>Visit History</h2></div><table><tr><th>Date</th><th>Purpose</th><th>Next Follow-up</th><th>Status</th></tr>{vr}</table></section>
    <section class="panel"><div class="panelhead"><h2>Preventive Activities</h2></div><table><tr><th>Activity</th><th>Date</th><th>Status</th><th>Notes</th></tr>{pr}</table></section>"""
    return layout(p["name"],body)

def form_page(title,action,fields,hidden=None):
    hidden=hidden or []
    h="".join(f"<input type='hidden' name='{esc(k)}' value='{esc(v)}'>" for k,v in hidden)
    fs=""
    for label,name,typ,ph in fields:
        if typ=="textarea": control=f"<textarea name='{name}' placeholder='{esc(ph)}'></textarea>"
        else: control=f"<input type='{typ}' name='{name}' placeholder='{esc(ph)}'>"
        fs+=f"<label>{label}{control}</label>"
    return f"""<div class="pagehead"><div><span class="eyebrow">SMARTSWASTHYA</span><h1>{title}</h1></div></div>
    <form class="form panel" method="POST" action="{action}">{h}<div class="formgrid">{fs}</div><button class="btn primary" type="submit">Save</button></form>"""

def add_record(pid):
    return layout("Health Record",form_page("Add Health Record","/add_record",
        [("Weight (kg)","weight","number","72"),("Blood Pressure","bp","text","120/80"),("Temperature","temperature","number","36.8"),("Glucose","glucose","number","100"),("Notes","notes","textarea","Observation or follow-up note")],
        [("patient_id",pid)]))

def add_visit(pid):
    return layout("Visit",form_page("Record Community Visit","/add_visit",
        [("Visit Date","visit_date","date",str(date.today())),("Purpose","purpose","text","Routine / Follow-up / Screening"),("Notes","notes","textarea","Visit notes"),("Next Follow-up","next_followup","date","")],
        [("patient_id",pid)]))

def add_preventive(pid):
    return layout("Preventive",form_page("Add Preventive Activity","/add_preventive",
        [("Activity","activity","text","Vaccination / BP screening / Nutrition"),("Activity Date","activity_date","date",str(date.today())),("Status","status","text","Completed / Pending"),("Notes","notes","textarea","Notes")],
        [("patient_id",pid)]))

def priority_page():
    c=db(); ps=c.execute("SELECT * FROM patients ORDER BY name").fetchall(); c.close()
    rows=""
    for p in ps:
        lv,sc,rs=priority(p["id"])
        rows+=f"<tr><td><a class='link' href='/patient?id={p['id']}'>{esc(p['name'])}</a></td><td><span class='pill {lv.lower()}'>{lv}</span></td><td><b>{sc}</b></td><td>{'<br>'.join(esc(x) for x in rs)}</td></tr>"
    return layout("Priority Cases",f"""<div class="pagehead"><div><span class="eyebrow">SMART PRIORITIZATION</span><h1>Priority Cases</h1><p>Explainable indicators help organize the health worker's visit queue.</p></div></div>
    <section class="notice">ℹ Priority is a workflow aid, not a clinical diagnosis or emergency triage tool.</section>
    <section class="panel"><table><tr><th>Patient</th><th>Priority</th><th>Score</th><th>Why?</th></tr>{rows}</table></section>""")

def planner():
    c=db(); ps=c.execute("SELECT * FROM patients").fetchall(); c.close()
    data=[]
    for p in ps:
        lv,sc,rs=priority(p["id"]); data.append((0 if lv=="HIGH" else 1 if lv=="MEDIUM" else 2,-sc,p,lv,rs))
    data.sort(key=lambda x:(x[0],x[1]))
    rows="".join(f"<tr><td><b>{i}</b></td><td><a class='link' href='/patient?id={p['id']}'>{esc(p['name'])}</a></td><td><span class='pill {lv.lower()}'>{lv}</span></td><td>{sc}</td><td>{esc(rs[0])}</td><td><a class='btn small' href='/add_visit?patient={p['id']}'>Record Visit</a></td></tr>" for i,(_,__,p,lv,rs) in enumerate(data,1) for sc in [priority(p["id"])[1]])
    return layout("Visit Planner",f"""<div class="pagehead"><div><span class="eyebrow">ACTION PLAN</span><h1>Smart Visit Planner</h1><p>Suggested visit order based on explainable priority indicators.</p></div></div>
    <section class="panel"><table><tr><th>#</th><th>Patient</th><th>Priority</th><th>Score</th><th>Reason</th><th>Action</th></tr>{rows}</table></section>""")

def reports():
    c=db()
    h=c.execute("SELECT COUNT(*) FROM households").fetchone()[0]; p=c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    v=c.execute("SELECT COUNT(*) FROM visits").fetchone()[0]; r=c.execute("SELECT COUNT(*) FROM health_records").fetchone()[0]
    c.close()
    return layout("Reports",f"""<div class="pagehead"><div><span class="eyebrow">ANALYTICS</span><h1>Reports & Data</h1><p>Overview for project demonstration and record export.</p></div><a class="btn primary" href="/export">↓ Export Patients CSV</a></div>
    <div class="cards"><div class="stat"><span>Households</span><strong>{h}</strong></div><div class="stat"><span>Patients</span><strong>{p}</strong></div><div class="stat"><span>Visits</span><strong>{v}</strong></div><div class="stat"><span>Health Records</span><strong>{r}</strong></div></div>
    <section class="panel"><h2>Project Analytics</h2><p>This report module can be expanded with monthly visits, locality comparisons, follow-up completion, preventive activity coverage and additional charts.</p>
    <div class="notice">For academic demonstration, use synthetic/sample data. Do not enter identifiable patient information without appropriate authorization and privacy controls.</div></section>""")

class Handler(http.server.BaseHTTPRequestHandler):
    def send_html(self,s):
        b=s.encode()
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def redirect(self,u):
        self.send_response(303); self.send_header("Location",u); self.end_headers()
    def form(self):
        n=int(self.headers.get("Content-Length",0)); return urllib.parse.parse_qs(self.rfile.read(n).decode())
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query); p=u.path
        if p=="/": self.send_html(dashboard())
        elif p=="/households": self.send_html(households())
        elif p=="/add_household": self.send_html(add_household())
        elif p=="/patients": self.send_html(patients())
        elif p=="/add_patient": self.send_html(add_patient())
        elif p=="/patient": self.send_html(patient(int(q.get("id",["0"])[0])))
        elif p=="/add_record": self.send_html(add_record(int(q.get("patient",["0"])[0])))
        elif p=="/add_visit": self.send_html(add_visit(int(q.get("patient",["0"])[0])))
        elif p=="/add_preventive": self.send_html(add_preventive(int(q.get("patient",["0"])[0])))
        elif p=="/priority": self.send_html(priority_page())
        elif p=="/planner": self.send_html(planner())
        elif p=="/reports": self.send_html(reports())
        elif p=="/export":
            c=db(); rows=c.execute("""SELECT p.name,p.age,p.gender,p.phone,h.code,h.locality FROM patients p LEFT JOIN households h ON h.id=p.household_id""").fetchall(); c.close()
            out=io.StringIO(); w=csv.writer(out); w.writerow(["Name","Age","Gender","Phone","Household","Locality"]); [w.writerow(list(x)) for x in rows]
            b=out.getvalue().encode(); self.send_response(200); self.send_header("Content-Type","text/csv"); self.send_header("Content-Disposition","attachment; filename=patients.csv"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
        elif p=="/static/style.css":
            try:
                b=open("static/style.css","rb").read(); self.send_response(200); self.send_header("Content-Type","text/css"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
            except: self.send_response(404); self.end_headers()
        elif p=="/static/app.js":
            try:
                b=open("static/app.js","rb").read(); self.send_response(200); self.send_header("Content-Type","application/javascript"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
            except: self.send_response(404); self.end_headers()
        else: self.send_response(404); self.end_headers()
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path; f=self.form(); c=db()
        try:
            if p=="/add_household":
                c.execute("INSERT INTO households(code,locality,contact) VALUES(?,?,?)",(f.get("code",[""])[0],f.get("locality",[""])[0],f.get("contact",[""])[0])); c.commit(); self.redirect("/households")
            elif p=="/add_patient":
                c.execute("INSERT INTO patients(name,age,gender,phone,household_id) VALUES(?,?,?,?,?)",(f.get("name",[""])[0],int(f.get("age",["0"])[0]),f.get("gender",[""])[0],f.get("phone",[""])[0],int(f.get("household_id",["0"])[0]))); c.commit(); self.redirect("/patients")
            elif p=="/add_record":
                pid=int(f.get("patient_id",["0"])[0]); c.execute("""INSERT INTO health_records(patient_id,record_date,weight,bp,temperature,glucose,notes) VALUES(?,?,?,?,?,?,?)""",(pid,str(date.today()),float(f.get("weight",["0"])[0] or 0),f.get("bp",[""])[0],float(f.get("temperature",["0"])[0] or 0),float(f.get("glucose",["0"])[0] or 0),f.get("notes",[""])[0])); c.commit(); self.redirect("/patient?id="+str(pid))
            elif p=="/add_visit":
                pid=int(f.get("patient_id",["0"])[0]); c.execute("""INSERT INTO visits(patient_id,visit_date,purpose,notes,next_followup,status) VALUES(?,?,?,?,?,?)""",(pid,f.get("visit_date",[""])[0],f.get("purpose",[""])[0],f.get("notes",[""])[0],f.get("next_followup",[""])[0],"Completed")); c.commit(); self.redirect("/patient?id="+str(pid))
            elif p=="/add_preventive":
                pid=int(f.get("patient_id",["0"])[0]); c.execute("""INSERT INTO preventive(patient_id,activity,activity_date,status,notes) VALUES(?,?,?,?,?)""",(pid,f.get("activity",[""])[0],f.get("activity_date",[""])[0],f.get("status",[""])[0],f.get("notes",[""])[0])); c.commit(); self.redirect("/patient?id="+str(pid))
            else: self.send_response(404); self.end_headers()
        except Exception as e:
            c.rollback(); self.send_html(layout("Error",f"<section class='panel'><h1>Could not save</h1><p>{esc(e)}</p><a class='btn primary' href='/'>Back</a></section>"))
        finally: c.close()

if __name__=="__main__":
    init_db(); seed()
    print("SmartSwasthya running at http://127.0.0.1:8000")
    with socketserver.TCPServer(("",PORT),Handler) as server:
        server.serve_forever()
