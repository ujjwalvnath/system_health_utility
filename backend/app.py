from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import sqlite3
import json
import csv
import io
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "syshealth.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS machines (
        machine_id TEXT PRIMARY KEY,
        machine_name TEXT,
        os TEXT,
        os_version TEXT,
        disk_encrypted INTEGER,
        os_up_to_date INTEGER,
        antivirus_present INTEGER,
        inactivity_sleep_minutes INTEGER,
        has_issues INTEGER,
        raw_json TEXT,
        last_check TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

def compute_has_issues(checks: dict) -> int:
    """
    returns 1 if an issue exists, else 0.
    Issues if: disk_encrypted is falsy OR os_up_to_date falsy OR antivirus_present falsy OR inactivity_sleep_minutes > 10
    Accepts booleans or integers/strings.
    """
    # normalize values
    def truthy(v):
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1","true","yes","y","on"):
                return True
            return False
        return False

    disk_encrypted = truthy(checks.get("disk_encrypted"))
    os_up_to_date = truthy(checks.get("os_up_to_date"))
    antivirus_present = truthy(checks.get("antivirus_present"))
    inactivity_sleep_minutes = checks.get("inactivity_sleep_minutes")
    try:
        inactivity = int(inactivity_sleep_minutes) if inactivity_sleep_minutes is not None else 999
    except Exception:
        inactivity = 999

    if (not disk_encrypted) or (not os_up_to_date) or (not antivirus_present) or (inactivity > 10):
        return 1
    return 0

@app.route("/report", methods=["POST"])
def report():
    """
    Expects JSON payload with:
    {
      "machine_id": "unique-id",
      "machine_name": "host1.example",
      "os": "Ubuntu",
      "os_version": "22.04",
      "checks": {
         "disk_encrypted": true/false,
         "os_up_to_date": true/false,
         "antivirus_present": true/false,
         "inactivity_sleep_minutes": 5
      }
    }
    """
    payload = request.get_json(force=True)
    if not payload or "machine_id" not in payload:
        return jsonify({"error":"missing machine_id"}), 400

    machine_id = str(payload.get("machine_id"))
    machine_name = payload.get("machine_name") or payload.get("hostname") or None
    os_name = payload.get("os") or None
    os_version = payload.get("os_version") or None
    checks = payload.get("checks") or {}

    disk_encrypted = 1 if checks.get("disk_encrypted") else 0
    os_up_to_date = 1 if checks.get("os_up_to_date") else 0
    antivirus_present = 1 if checks.get("antivirus_present") else 0
    try:
        inactivity = int(checks.get("inactivity_sleep_minutes")) if checks.get("inactivity_sleep_minutes") is not None else None
    except Exception:
        inactivity = None

    has_issues = compute_has_issues(checks)
    raw = json.dumps(checks)
    last_check = datetime.utcnow().isoformat(timespec="seconds")

    conn = get_conn()
    cur = conn.cursor()
    # Upsert by machine_id (SQLite ON CONFLICT)
    cur.execute("""
        INSERT INTO machines (
            machine_id, machine_name, os, os_version,
            disk_encrypted, os_up_to_date, antivirus_present,
            inactivity_sleep_minutes, has_issues, raw_json, last_check
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(machine_id) DO UPDATE SET
            machine_name=excluded.machine_name,
            os=excluded.os,
            os_version=excluded.os_version,
            disk_encrypted=excluded.disk_encrypted,
            os_up_to_date=excluded.os_up_to_date,
            antivirus_present=excluded.antivirus_present,
            inactivity_sleep_minutes=excluded.inactivity_sleep_minutes,
            has_issues=excluded.has_issues,
            raw_json=excluded.raw_json,
            last_check=excluded.last_check
    """, (
        machine_id, machine_name, os_name, os_version,
        disk_encrypted, os_up_to_date, antivirus_present,
        inactivity, has_issues, raw, last_check
    ))
    conn.commit()
    conn.close()

    return jsonify({"status":"saved","machine_id":machine_id, "has_issues": bool(has_issues)}), 201


@app.route("/machines", methods=["GET"])
def list_machines():
    """
    Optional query params:
      - os=Ubuntu%2022.04
      - only_issues=1
    """
    os_filter = request.args.get("os")
    only_issues = request.args.get("only_issues")

    sql = "SELECT * FROM machines"
    clauses = []
    params = []

    if os_filter:
        clauses.append("os = ?")
        params.append(os_filter)
    if only_issues and only_issues.lower() in ("1","true","yes"):
        clauses.append("has_issues = 1")

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY last_check DESC"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        rec = dict(r)
        # convert ints to booleans where appropriate for JSON clarity
        rec["disk_encrypted"] = bool(rec["disk_encrypted"])
        rec["os_up_to_date"] = bool(rec["os_up_to_date"])
        rec["antivirus_present"] = bool(rec["antivirus_present"])
        rec["has_issues"] = bool(rec["has_issues"])
        # parse raw_json into checks object
        try:
            rec["checks"] = json.loads(rec.get("raw_json") or "{}")
        except Exception:
            rec["checks"] = {}
        result.append(rec)
    return jsonify(result)


@app.route("/export.csv", methods=["GET"])
def export_csv():
    # reuse filters if provided
    os_filter = request.args.get("os")
    only_issues = request.args.get("only_issues")

    sql = "SELECT * FROM machines"
    clauses = []
    params = []
    if os_filter:
        clauses.append("os = ?"); params.append(os_filter)
    if only_issues and only_issues.lower() in ("1","true","yes"):
        clauses.append("has_issues = 1")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY last_check DESC"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    header = ["machine_id","machine_name","os","os_version","disk_encrypted","os_up_to_date","antivirus_present","inactivity_sleep_minutes","has_issues","last_check"]
    writer.writerow(header)
    for r in rows:
        writer.writerow([
            r["machine_id"],
            r["machine_name"],
            r["os"],
            r["os_version"],
            r["disk_encrypted"],
            r["os_up_to_date"],
            r["antivirus_present"],
            r["inactivity_sleep_minutes"],
            r["has_issues"],
            r["last_check"]
        ])
    csv_data = output.getvalue()
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=machines.csv"})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
