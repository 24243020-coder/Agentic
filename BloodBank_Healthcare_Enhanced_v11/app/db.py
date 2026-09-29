import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bloodbank.db"

def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS donors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        blood_group TEXT NOT NULL,
        city TEXT NOT NULL,
        phone TEXT,
        available INTEGER DEFAULT 1,
        available_units INTEGER DEFAULT 0,
        last_donation TEXT
    );
    CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_id INTEGER NOT NULL,
        units INTEGER NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'Willing',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        confirmed_at TEXT,
        FOREIGN KEY(donor_id) REFERENCES donors(id)
    );
    CREATE TABLE IF NOT EXISTS inventory (
        blood_group TEXT PRIMARY KEY,
        units INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT NOT NULL,
        blood_group TEXT NOT NULL,
        units INTEGER NOT NULL,
        hospital TEXT NOT NULL,
        urgency TEXT NOT NULL,
        status TEXT DEFAULT 'Pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        donor_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Safe migrations for databases created by earlier versions.
    donor_cols = [r[1] for r in conn.execute("PRAGMA table_info(donors)").fetchall()]
    if "available_units" not in donor_cols:
        conn.execute("ALTER TABLE donors ADD COLUMN available_units INTEGER DEFAULT 0")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(requests)").fetchall()]
    if "donor_id" not in cols:
        conn.execute("ALTER TABLE requests ADD COLUMN donor_id INTEGER")

    if conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0:
        conn.executemany("INSERT INTO inventory(blood_group,units) VALUES (?,?)",
            [("A+",24),("A-",8),("B+",18),("B-",6),("AB+",10),("AB-",3),("O+",30),("O-",7)])
    if conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0] == 0:
        donors = [
            ("Arun Kumar","O+","Chennai","9000000011",1,1,"2026-04-18"),
            ("Divya S","A+","Chennai","9000000012",1,1,"2026-05-10"),
            ("Karthik R","B+","Coimbatore","9000000013",1,1,"2026-03-22"),
            ("Meena P","O-","Chennai","9000000014",1,1,"2026-02-15"),
            ("Rahul M","AB+","Madurai","9000000015",1,1,"2026-06-01"),
            ("Nandhini V","A-","Salem","9000000016",0,0,"2026-01-11"),
            ("Sanjay K","B-","Chennai","9000000017",1,1,"2026-02-26"),
            ("Priya T","O+","Chennai","9000000018",1,1,"2026-05-21")
        ]
        conn.executemany("""INSERT INTO donors
        (name,blood_group,city,phone,available,available_units,last_donation)
        VALUES (?,?,?,?,?,?,?)""", donors)
    # Keep donor availability driven by the units they currently have.
    # For old databases that do not have a value yet, preserve available donors
    # as one unit and unavailable donors as zero.
    conn.execute("UPDATE donors SET available_units=CASE WHEN available_units IS NULL THEN 0 ELSE available_units END")
    # Carry forward unit counts from older donation records when possible.
    conn.execute("""
        UPDATE donors
        SET available_units=(
            SELECT COALESCE(SUM(dn.units),0)
            FROM donations dn
            WHERE dn.donor_id=donors.id AND dn.status IN ('Willing','Available')
        )
        WHERE available_units=0
          AND EXISTS (SELECT 1 FROM donations dn WHERE dn.donor_id=donors.id AND dn.status IN ('Willing','Available'))
    """)
    conn.execute("""
        UPDATE donors
        SET available_units=1
        WHERE available_units=0 AND available=1
          AND NOT EXISTS (SELECT 1 FROM donations dn WHERE dn.donor_id=donors.id AND dn.status='Confirmed')
    """)
    conn.execute("UPDATE donors SET available=CASE WHEN available_units>0 THEN 1 ELSE 0 END")

    # Seed a small activity feed only for a brand-new activity table.
    if conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0] == 0:
        conn.executemany("INSERT INTO activity(message) VALUES (?)", [
            ("Blood bank system is ready",),
            ("Donor network loaded",),
            ("Blood inventory loaded",),
        ])
    conn.commit()
    conn.close()
