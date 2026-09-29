from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import date
from .db import get_db
bp=Blueprint("main",__name__)

ALLOWED_GROUPS={"A+","A-","B+","B-","AB+","AB-","O+","O-"}

def log_activity(message):
    c=get_db()
    c.execute("INSERT INTO activity(message) VALUES (?)", (message,))
    c.commit()
    c.close()

@bp.get("/")
def index(): return render_template("index.html")

@bp.get("/api/dashboard")
def dashboard():
    c=get_db()
    inv=[dict(x) for x in c.execute("SELECT * FROM inventory ORDER BY blood_group")]
    donors=c.execute("SELECT COUNT(*) FROM donors WHERE available=1").fetchone()[0]
    pending=c.execute("SELECT COUNT(*) FROM requests WHERE status='Pending'").fetchone()[0]
    recent=[dict(x) for x in c.execute("""SELECT r.*, d.name AS donor_name
        FROM requests r LEFT JOIN donors d ON d.id=r.donor_id
        ORDER BY r.id DESC LIMIT 6""").fetchall()]
    activity=[dict(x) for x in c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 8")]
    c.close()
    return jsonify({"inventory":inv,"available_donors":donors,"pending_requests":pending,"recent_requests":recent,"recent_activity":activity})

@bp.get("/api/donors")
def donors():
    c=get_db()
    rows=[dict(x) for x in c.execute("""SELECT d.*,
        (SELECT reason FROM donations WHERE donor_id=d.id ORDER BY id DESC LIMIT 1) AS donation_reason
        FROM donors d ORDER BY d.available DESC,d.id DESC""").fetchall()]
    c.close()
    resp=jsonify(rows)
    resp.headers["Cache-Control"]="no-store"
    return resp

@bp.post("/api/donors")
def create_donor():
    d=request.get_json() or {}
    if any(not str(d.get(k, "")).strip() for k in ["name","blood_group","city","units"]):
        return jsonify({"error":"Name, blood group, city and units willing to donate are required"}),400
    group=d["blood_group"].upper().strip()
    if group not in ALLOWED_GROUPS:
        return jsonify({"error":"Invalid blood group"}),400
    try: units=int(d["units"])
    except (TypeError,ValueError): return jsonify({"error":"Units must be a whole number"}),400
    if units<1 or units>10: return jsonify({"error":"Donation units must be between 1 and 10"}),400
    c=get_db()
    cur=c.execute("INSERT INTO donors(name,blood_group,city,phone,available,available_units,last_donation) VALUES (?,?,?,?,1,?,?)",
                  (d["name"].strip(),group,d["city"].strip(),d.get("phone","").strip(),units,d.get("last_donation") or None))
    did=cur.lastrowid
    c.execute("INSERT INTO donations(donor_id,units,reason,status) VALUES (?,?,?,'Available')",
              (did,units,d.get("reason","").strip()))
    c.execute("UPDATE inventory SET units=units+?, updated_at=CURRENT_TIMESTAMP WHERE blood_group=?",(units,group))
    c.commit(); c.close()
    log_activity(f"Donor added — {d['name'].strip()} ({group}) added {units} unit(s) to blood inventory")
    return jsonify({"ok":True,"donor_id":did})

@bp.post("/api/request")
def create_request():
    d=request.get_json() or {}
    if any(not d.get(k) for k in ["patient_name","blood_group","units","hospital","urgency"]):
        return jsonify({"error":"All fields are required"}),400
    group=d["blood_group"].upper()
    try: units=int(d["units"])
    except (TypeError,ValueError): return jsonify({"error":"Units must be a whole number"}),400
    if group not in ALLOWED_GROUPS or units<1:
        return jsonify({"error":"Enter a valid blood group and unit count"}),400
    c=get_db()
    donor_id=d.get("donor_id") or None
    if donor_id:
        donor=c.execute("SELECT id, blood_group, available, available_units FROM donors WHERE id=?",(donor_id,)).fetchone()
        if not donor or not donor["available"] or donor["blood_group"] != group or donor["available_units"] < units:
            c.close(); return jsonify({"error":"Selected donor is unavailable or blood group does not match"}),400
    cur=c.execute("INSERT INTO requests(patient_name,blood_group,units,hospital,urgency,status,donor_id) VALUES (?,?,?,?,?,'Pending',?)",
                  (d["patient_name"].strip(),group,units,d["hospital"].strip(),d["urgency"],donor_id))
    c.commit(); rid=cur.lastrowid; c.close()
    donor_note=" with a donor assigned" if donor_id else ""
    log_activity(f"Blood request #{rid} created — {units} unit(s) {group}{donor_note}")
    return jsonify({"ok":True,"request_id":rid})

@bp.post("/api/agent")
def agent():
    d=request.get_json() or {}; text=d.get("message","").strip()
    if not text: return jsonify({"error":"Enter a message"}),400
    result=current_app.extensions["blood_agent"].invoke(text)
    log_activity(current_app.extensions["blood_agent"].activity_message(text, result))
    return jsonify({"answer":result["answer"],"steps":result.get("steps",[])})

@bp.post("/api/requests/<int:request_id>/fulfill")
def fulfill_request(request_id):
    c=get_db()
    row=c.execute("SELECT * FROM requests WHERE id=?",(request_id,)).fetchone()
    if not row:
        c.close(); return jsonify({"error":"Request not found"}),404
    if row["status"] != "Pending":
        c.close(); return jsonify({"error":"Request is already processed"}),400
    stock=c.execute("SELECT blood_group, units FROM inventory WHERE blood_group=?",(row["blood_group"],)).fetchone()
    if not stock or stock["units"] < row["units"]:
        c.close(); return jsonify({"error":f"Not enough {row['blood_group']} stock to fulfill this request"}),400
    c.execute("UPDATE inventory SET units=units-?, updated_at=CURRENT_TIMESTAMP WHERE blood_group=?",(row["units"],row["blood_group"]))
    c.execute("UPDATE requests SET status='Fulfilled' WHERE id=?",(request_id,))
    if row["donor_id"]:
        donor=c.execute("SELECT name, available_units FROM donors WHERE id=?",(row["donor_id"],)).fetchone()
        if not donor or donor["available_units"] < row["units"]:
            c.rollback(); c.close(); return jsonify({"error":"The assigned donor does not have enough units available"}),400
        remaining=donor["available_units"]-row["units"]
        c.execute("UPDATE donors SET available_units=?, available=? WHERE id=?",(remaining,1 if remaining>0 else 0,row["donor_id"]))
    c.commit(); c.close()
    log_activity(f"Blood issued — request #{request_id}: {row['units']} unit(s) {row['blood_group']}")
    return jsonify({"ok":True})
