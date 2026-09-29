from .db import get_db
from .rag import search_policies

def inventory_tool(blood_group=None):
    conn=get_db()
    if blood_group:
        row=conn.execute("SELECT * FROM inventory WHERE blood_group=?", (blood_group.upper(),)).fetchone()
        conn.close()
        return dict(row) if row else {"error":f"No inventory record for {blood_group.upper()}"}
    rows=conn.execute("SELECT * FROM inventory ORDER BY blood_group").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def donor_search_tool(blood_group, city=None):
    conn=get_db()
    if city:
        rows=conn.execute("SELECT * FROM donors WHERE blood_group=? AND available=1 AND city LIKE ? ORDER BY id",
                           (blood_group.upper(),f"%{city}%")).fetchall()
    else:
        rows=conn.execute("SELECT * FROM donors WHERE blood_group=? AND available=1 ORDER BY id",
                           (blood_group.upper(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def policy_search_tool(query):
    return search_policies(query)

def list_requests_tool():
    conn=get_db()
    rows=conn.execute("SELECT * FROM requests ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_request_tool(patient_name,blood_group,units,hospital,urgency):
    conn=get_db()
    cur=conn.execute(
        "INSERT INTO requests(patient_name,blood_group,units,hospital,urgency,status) VALUES (?,?,?,?,?,'Pending')",
        (patient_name,blood_group.upper(),int(units),hospital,urgency))
    conn.commit()
    rid=cur.lastrowid
    conn.close()
    return {"request_id":rid,"status":"Pending"}


def fulfill_request_tool(request_id):
    conn=get_db()
    row=conn.execute("SELECT * FROM requests WHERE id=?", (int(request_id),)).fetchone()
    if not row:
        conn.close(); return {"ok":False,"message":"Blood request not found."}
    if row["status"] != "Pending":
        conn.close(); return {"ok":False,"message":f"Blood request #{request_id} is already processed."}
    stock=conn.execute("SELECT units FROM inventory WHERE blood_group=?", (row["blood_group"],)).fetchone()
    if not stock or stock["units"] < row["units"]:
        conn.close(); return {"ok":False,"message":f"Not enough {row['blood_group']} stock to fulfill request #{request_id}."}
    if row["donor_id"]:
        donor=conn.execute("SELECT name,available_units FROM donors WHERE id=?", (row["donor_id"],)).fetchone()
        if not donor or donor["available_units"] < row["units"]:
            conn.close(); return {"ok":False,"message":f"The assigned donor does not have enough units for request #{request_id}."}
    conn.execute("UPDATE inventory SET units=units-?, updated_at=CURRENT_TIMESTAMP WHERE blood_group=?", (row["units"],row["blood_group"]))
    conn.execute("UPDATE requests SET status='Fulfilled' WHERE id=?", (request_id,))
    donor_name=None; remaining=None
    if row["donor_id"]:
        donor=conn.execute("SELECT name,available_units FROM donors WHERE id=?", (row["donor_id"],)).fetchone()
        remaining=donor["available_units"]-row["units"]
        donor_name=donor["name"]
        conn.execute("UPDATE donors SET available_units=?, available=? WHERE id=?", (remaining,1 if remaining>0 else 0,row["donor_id"]))
    conn.commit(); conn.close()
    return {"ok":True,"request_id":request_id,"patient_name":row["patient_name"],"blood_group":row["blood_group"],"units":row["units"],"donor_name":donor_name,"donor_remaining_units":remaining,"message":f"Blood request #{request_id} for {row['patient_name']} was fulfilled successfully."}

def tool_catalog():
    return {"inventory":inventory_tool,"donor_search":donor_search_tool,
            "policy_search":policy_search_tool,"list_requests":list_requests_tool,
            "create_request":create_request_tool,"fulfill_request":fulfill_request_tool}
