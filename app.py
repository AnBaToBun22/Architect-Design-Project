import base64
import os
import re
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "vehicle_plate.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'police')),
                badge_no TEXT,
                phone TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL,
                list_type TEXT NOT NULL CHECK(list_type IN ('blacklist', 'whitelist')),
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scan_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                color TEXT,
                list_type TEXT NOT NULL,
                location TEXT,
                image_path TEXT,
                police_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(police_id) REFERENCES users(id)
            );
            """
        )

        user_count = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
        if user_count == 0:
            now = datetime.utcnow().isoformat()
            db.executemany(
                """
                INSERT INTO users (full_name, username, password_hash, role, badge_no, phone, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "System Admin",
                        "admin",
                        generate_password_hash("admin123"),
                        "admin",
                        None,
                        "0900000000",
                        now,
                    ),
                    (
                        "Police Officer 01",
                        "police01",
                        generate_password_hash("police123"),
                        "police",
                        "P001",
                        "0911111111",
                        now,
                    ),
                ],
            )

        vehicle_count = db.execute("SELECT COUNT(*) AS total FROM vehicles").fetchone()["total"]
        if vehicle_count == 0:
            now = datetime.utcnow().isoformat()
            db.executemany(
                """
                INSERT INTO vehicles (plate_number, color, list_type, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("51A12345", "Red", "blacklist", "Traffic violation", now),
                    ("30F67890", "White", "whitelist", "Verified vehicle", now),
                    ("59C24680", "Black", "blacklist", "Wanted vehicle", now),
                ],
            )


def normalize_plate(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def recognize_plate_from_image(_image_path):
    # Placeholder for OpenCV + Tesseract/EasyOCR integration.
    # The simple demo relies on the text entered by the police user.
    return ""


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for("home"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def current_user():
    if "user_id" not in session:
        return None
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.route("/")
def home():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if session.get("role") == "police":
        return redirect(url_for("police_scan"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("home"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/police")
@login_required("police")
def police_scan():
    with get_db() as db:
        vehicles = db.execute(
            "SELECT plate_number, color, list_type FROM vehicles ORDER BY list_type, plate_number"
        ).fetchall()
    return render_template("police.html", user=current_user(), vehicles=vehicles)


@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    with get_db() as db:
        stats = {
            "police": db.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'police'").fetchone()["total"],
            "blacklist": db.execute("SELECT COUNT(*) AS total FROM vehicles WHERE list_type = 'blacklist'").fetchone()["total"],
            "whitelist": db.execute("SELECT COUNT(*) AS total FROM vehicles WHERE list_type = 'whitelist'").fetchone()["total"],
            "scans": db.execute("SELECT COUNT(*) AS total FROM scan_logs").fetchone()["total"],
        }
        police = db.execute("SELECT * FROM users WHERE role = 'police' ORDER BY id DESC").fetchall()
        vehicles = db.execute("SELECT * FROM vehicles ORDER BY list_type, plate_number").fetchall()
        logs = db.execute(
            """
            SELECT scan_logs.*, users.full_name AS police_name
            FROM scan_logs
            LEFT JOIN users ON users.id = scan_logs.police_id
            ORDER BY scan_logs.id DESC
            LIMIT 50
            """
        ).fetchall()
    return render_template("admin.html", user=current_user(), stats=stats, police=police, vehicles=vehicles, logs=logs)


@app.post("/api/scan")
@login_required("police")
def api_scan():
    payload = request.get_json(silent=True) or {}
    plate_number = normalize_plate(payload.get("plate_number"))
    location = payload.get("location", "").strip()
    image_data = payload.get("image_data", "")
    image_path = None

    if image_data.startswith("data:image"):
        header, encoded = image_data.split(",", 1)
        extension = "jpg" if "jpeg" in header or "jpg" in header else "png"
        filename = f"scan_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.{extension}"
        target = UPLOAD_DIR / filename
        target.write_bytes(base64.b64decode(encoded))
        image_path = f"/static/uploads/{filename}"

    if not plate_number and image_path:
        plate_number = normalize_plate(recognize_plate_from_image(BASE_DIR / image_path.lstrip("/")))

    if not plate_number:
        return jsonify({"ok": False, "message": "Plate number is required."}), 400

    with get_db() as db:
        vehicle = db.execute("SELECT * FROM vehicles WHERE plate_number = ?", (plate_number,)).fetchone()
        if vehicle:
            color = vehicle["color"]
            list_type = vehicle["list_type"]
        else:
            color = "Unknown"
            list_type = "unknown"

        db.execute(
            """
            INSERT INTO scan_logs (plate_number, color, list_type, location, image_path, police_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plate_number,
                color,
                list_type,
                location,
                image_path,
                session["user_id"],
                datetime.utcnow().isoformat(),
            ),
        )

    return jsonify(
        {
            "ok": True,
            "plate_number": plate_number,
            "color": color,
            "list_type": list_type,
            "is_blacklist": list_type == "blacklist",
            "message": "Blacklist vehicle detected!" if list_type == "blacklist" else "Scan saved.",
        }
    )


@app.get("/api/notifications")
@login_required("admin")
def api_notifications():
    after_id = int(request.args.get("after_id", 0))
    with get_db() as db:
        rows = db.execute(
            """
            SELECT scan_logs.*, users.full_name AS police_name
            FROM scan_logs
            LEFT JOIN users ON users.id = scan_logs.police_id
            WHERE scan_logs.id > ? AND scan_logs.list_type = 'blacklist'
            ORDER BY scan_logs.id DESC
            """,
            (after_id,),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/admin/police")
@login_required("admin")
def add_police():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    badge_no = request.form.get("badge_no", "").strip()
    phone = request.form.get("phone", "").strip()
    if not full_name or not username or not password:
        flash("Full name, username and password are required.", "error")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_db() as db:
            db.execute(
                """
                INSERT INTO users (full_name, username, password_hash, role, badge_no, phone, created_at)
                VALUES (?, ?, ?, 'police', ?, ?, ?)
                """,
                (full_name, username, generate_password_hash(password), badge_no, phone, datetime.utcnow().isoformat()),
            )
        flash("Police account added.", "success")
    except sqlite3.IntegrityError:
        flash("Username already exists.", "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/vehicles")
@login_required("admin")
def add_vehicle():
    plate_number = normalize_plate(request.form.get("plate_number"))
    color = request.form.get("color", "").strip() or "Unknown"
    list_type = request.form.get("list_type", "blacklist")
    note = request.form.get("note", "").strip()
    if list_type not in {"blacklist", "whitelist"} or not plate_number:
        flash("Valid plate number and list type are required.", "error")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_db() as db:
            db.execute(
                """
                INSERT INTO vehicles (plate_number, color, list_type, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plate_number, color, list_type, note, datetime.utcnow().isoformat()),
            )
        flash("Vehicle added.", "success")
    except sqlite3.IntegrityError:
        flash("Plate number already exists.", "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/vehicles/<int:vehicle_id>/delete")
@login_required("admin")
def delete_vehicle(vehicle_id):
    with get_db() as db:
        db.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    flash("Vehicle removed.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000, use_reloader=False)
