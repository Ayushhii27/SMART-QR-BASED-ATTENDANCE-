# FINAL UPGRADED app.py

from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector
import qrcode
import pandas as pd
import os
import math
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_code"

# ---------------- DB CONFIG ----------------
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "your_password",
    "database": "qr_attendance"
}

# ---------------- GPS CLASSROOM LOCATION ----------------
CLASS_LAT = 28.6139
CLASS_LON = 77.2090
ALLOWED_RADIUS = 50   # meters

# ---------------- SESSION ----------------
qr_session_active = False

# ---------------- DB ----------------
def get_db():
    return mysql.connector.connect(
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        buffered=True
    )
# ---------------- DISTANCE ----------------
def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)

    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

# ---------------- HOME ----------------
@app.route("/")
def home():
    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE role='student'")
    total_students = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE role='teacher'")
    total_teachers = cur.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("SELECT COUNT(*) FROM logs WHERE date=%s", (today,))
    present = cur.fetchone()[0]

    absent = total_students - present
    if absent < 0:
        absent = 0

    cur.close()
    con.close()

    return render_template(
        "index.html",
        total_students=total_students,
        total_teachers=total_teachers,
        present=present,
        absent=absent
    )

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        con = get_db()
        cur = con.cursor()

        cur.execute(
            "SELECT username, role FROM users WHERE username=%s AND password=%s",
            (username, password)
        )

        user = cur.fetchone()

        cur.close()
        con.close()

        if user:
            session["username"] = user[0]
            session["role"] = user[1]

            if user[1] == "admin":
                return redirect("/admin")
            elif user[1] == "teacher":
                return redirect("/teacher")
            else:
                return redirect("/student")

        return "Invalid Login"

    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- ADMIN ----------------
@app.route("/admin")
def admin():

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE role='student'")
    total_students = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE role='teacher'")
    total_teachers = cur.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM logs WHERE date=%s", (today,))
    present = cur.fetchone()[0]

    cur.execute("SELECT username, role FROM users ORDER BY id DESC LIMIT 5")
    users = cur.fetchall()

    cur.close()
    con.close()

    return render_template(
        "admin.html",
        total_students=total_students,
        total_teachers=total_teachers,
        present=present,
        users=users,
        username=session.get("username"),
        role=session.get("role")
    )

# ---------------- ADD STUDENT ----------------
@app.route("/add_student", methods=["POST"])
def add_student():

    roll = request.form["roll"]

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT * FROM users WHERE username=%s", (roll,))
    already = cur.fetchone()

    if already:
        cur.close()
        con.close()
        return "Student already exists"

    cur.execute(
        "INSERT INTO users(username,password,role) VALUES(%s,%s,'student')",
        (roll, roll)
    )

    con.commit()

    cur.close()
    con.close()

    return redirect("/admin")

# ---------------- TEACHER ----------------
@app.route("/teacher")
def teacher():

    global qr_session_active

    token = str(int(time.time()/30))

    img = qrcode.make(token)

    if not os.path.exists("static"):
        os.makedirs("static")

    img.save("static/qr.png")

    con = get_db()
    cur = con.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM logs WHERE date=%s", (today,))
    present = cur.fetchone()[0]

    cur.close()
    con.close()

    return render_template(
        "teacher.html",
        present=present,
        qr_active=qr_session_active,
        username=session.get("username"),
        role=session.get("role")
    )

# ---------------- START SESSION ----------------
@app.route("/start_session")
def start_session():
    global qr_session_active
    qr_session_active = True
    return redirect("/teacher")

# ---------------- END SESSION ----------------
@app.route("/end_session")
def end_session():
    global qr_session_active
    qr_session_active = False
    return redirect("/teacher")

# ---------------- STUDENT ----------------
@app.route("/student")
def student():

    username = session.get("username")

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM logs WHERE roll=%s", (username,))
    total_present = cur.fetchone()[0]

    total_classes = 30

    percent = int((total_present / total_classes) * 100) if total_classes > 0 else 0

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute(
        "SELECT * FROM logs WHERE roll=%s AND date=%s",
        (username, today)
    )

    today_status = "Present" if cur.fetchone() else "Absent"

    cur.execute(
        "SELECT date,time FROM logs WHERE roll=%s ORDER BY id DESC LIMIT 5",
        (username,)
    )

    recent = cur.fetchall()

    cur.close()
    con.close()

    return render_template(
        "student.html",
        percent=percent,
        total_classes=total_classes,
        today_status=today_status,
        recent=recent,
        username=username,
        role=session.get("role")
    )

# ---------------- SCAN QR ----------------
@app.route("/scan_qr", methods=["POST"])
def scan_qr():

    global qr_session_active

    if not qr_session_active:
        return "Attendance Session Closed ❌"

    roll = request.form["roll"]
    qr_value = request.form["qr_value"]
    lat = float(request.form["lat"])
    lon = float(request.form["lon"])

    current_token = str(int(time.time()/30))

    if qr_value != current_token:
        return "Invalid or Expired QR ❌"

    distance = get_distance(lat, lon, CLASS_LAT, CLASS_LON)

    if distance > ALLOWED_RADIUS:
        return "Outside Classroom Radius ❌"

    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M:%S")

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "SELECT * FROM logs WHERE roll=%s AND date=%s",
        (roll, today)
    )

    already = cur.fetchone()

    if already:
        cur.close()
        con.close()
        return "Duplicate Attendance ❌"

    cur.execute(
        "INSERT INTO logs(roll,date,time) VALUES(%s,%s,%s)",
        (roll, today, now)
    )

    con.commit()

    cur.close()
    con.close()

    return "Attendance Marked Successfully ✅"

# ---------------- REPORTS ----------------
@app.route("/reports")
def reports():

    roll = request.args.get("roll", "")
    date = request.args.get("date", "")

    con = get_db()
    cur = con.cursor()

    query = "SELECT roll,date,time FROM logs WHERE 1=1"
    values = []

    if roll:
        query += " AND roll=%s"
        values.append(roll)

    if date:
        query += " AND date=%s"
        values.append(date)

    query += " ORDER BY id DESC"

    cur.execute(query, tuple(values))
    rows = cur.fetchall()

    cur.close()
    con.close()

    return render_template(
        "reports.html",
        rows=rows,
        username=session.get("username"),
        role=session.get("role")
    )

# ---------------- EXPORT ----------------
@app.route("/export")
def export():

    con = get_db()

    df = pd.read_sql("SELECT * FROM logs", con)

    file = "attendance_report.csv"
    df.to_csv(file, index=False)

    con.close()

    return send_file(file, as_attachment=True)

# ---------------- RUN ----------------
import os
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)