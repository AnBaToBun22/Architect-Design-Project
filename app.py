import base64
import smtplib
import os
import re
import sqlite3
from datetime import datetime
from email.message import EmailMessage
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
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "trantin202ad@gmail.com")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_SENDER"] = os.environ.get("MAIL_SENDER", app.config["MAIL_USERNAME"])
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
                        "Quản trị hệ thống",
                        "admin",
                        generate_password_hash("admin123"),
                        "admin",
                        None,
                        "0900000000",
                        now,
                    ),
                    (
                        "Cảnh sát 01",
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
                    ("51A12345", "Đỏ", "blacklist", "Vi phạm giao thông", now),
                    ("30F67890", "Trắng", "whitelist", "Xe đã xác minh", now),
                    ("59C24680", "Đen", "blacklist", "Xe cần theo dõi", now),
                ],
            )


def normalize_plate(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def looks_like_plate(value):
    plate = normalize_plate(value)
    return bool(re.fullmatch(r"\d{2}[A-Z]{1,2}\d{4,6}", plate))


def extract_plate_candidates(text):
    normalized_text = (text or "").upper()
    rough_tokens = re.findall(r"[A-Z0-9][A-Z0-9\.\-\s]{5,14}[A-Z0-9]", normalized_text)
    candidates = []
    for token in rough_tokens + [normalized_text]:
        compact = normalize_plate(token)
        for size in range(7, 11):
            for index in range(0, max(len(compact) - size + 1, 0)):
                candidate = compact[index : index + size]
                if looks_like_plate(candidate) and candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def find_tesseract_cmd():
    configured = os.environ.get("TESSERACT_CMD")
    if configured and Path(configured).exists():
        return configured

    for candidate in (
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return ""


def recognize_plate_from_image(image_path):
    try:
        import cv2
        import pytesseract
    except ImportError:
        app.logger.warning("OCR libraries are not installed. Run pip install -r requirements.txt.")
        return "", "Máy chủ chưa cài đủ thư viện OCR. Vui lòng chạy pip install -r requirements.txt."

    tesseract_cmd = find_tesseract_cmd()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    image = cv2.imread(str(image_path))
    if image is None:
        return "", "Không đọc được file ảnh vừa tải lên. Vui lòng thử ảnh khác."

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    variants = [
        gray,
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            2,
        ),
    ]

    config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    all_candidates = []
    for variant in variants:
        try:
            text = pytesseract.image_to_string(variant, lang="eng", config=config)
        except pytesseract.TesseractNotFoundError:
            app.logger.warning("Tesseract executable was not found. Install Tesseract OCR and add it to PATH.")
            return "", "Máy chủ chưa cài Tesseract OCR nên chưa thể tự quét biển số từ ảnh."
        except Exception:
            app.logger.exception("Could not recognize plate from image.")
            continue

        for candidate in extract_plate_candidates(text):
            if candidate not in all_candidates:
                all_candidates.append(candidate)

    if not all_candidates:
        return "", "Không nhận diện được biển số trong ảnh. Vui lòng thử ảnh rõ hơn, chụp gần biển số hơn."

    with get_db() as db:
        placeholders = ",".join("?" for _ in all_candidates)
        known = db.execute(
            f"SELECT plate_number FROM vehicles WHERE plate_number IN ({placeholders})",
            all_candidates,
        ).fetchone()
    return (known["plate_number"] if known else all_candidates[0]), ""


def format_list_type(list_type):
    labels = {
        "blacklist": "Danh sách đen",
        "whitelist": "Danh sách trắng",
        "unknown": "Chưa xác định",
    }
    return labels.get(list_type, list_type)


def send_scan_email(scan_info):
    if not app.config["MAIL_SERVER"] or not app.config["MAIL_SENDER"]:
        app.logger.warning("Chưa cấu hình SMTP, bỏ qua gửi email tới %s.", ADMIN_EMAIL)
        return False

    is_blacklist = scan_info["list_type"] == "blacklist"
    subject_prefix = "CẢNH BÁO XE DANH SÁCH ĐEN" if is_blacklist else "Thông báo lượt quét biển số"
    message = EmailMessage()
    message["Subject"] = f"{subject_prefix}: {scan_info['plate_number']}"
    message["From"] = app.config["MAIL_SENDER"]
    message["To"] = ADMIN_EMAIL
    message.set_content(
        "\n".join(
            [
                "Hệ thống vừa ghi nhận một lượt quét biển số.",
                "",
                f"Biển số: {scan_info['plate_number']}",
                f"Loại: {format_list_type(scan_info['list_type'])}",
                f"Màu xe: {scan_info['color']}",
                f"Vị trí: {scan_info['location'] or 'Chưa nhập'}",
                f"Cảnh sát thực hiện: {scan_info['police_name'] or 'Chưa xác định'}",
                f"Thời gian: {scan_info['created_at']}",
            ]
        )
    )

    image_path = scan_info.get("image_path")
    if image_path:
        attachment_path = BASE_DIR / image_path.lstrip("/")
        if attachment_path.exists():
            maintype = "image"
            subtype = attachment_path.suffix.lstrip(".") or "jpeg"
            message.add_attachment(
                attachment_path.read_bytes(),
                maintype=maintype,
                subtype="jpeg" if subtype == "jpg" else subtype,
                filename=attachment_path.name,
            )

    with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as smtp:
        if app.config["MAIL_USE_TLS"]:
            smtp.starttls()
        if app.config["MAIL_USERNAME"] and app.config["MAIL_PASSWORD"]:
            smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        smtp.send_message(message)
    return True


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Bạn không có quyền truy cập trang này.", "error")
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
        flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")
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
    ocr_error = ""
    recognized_by_ocr = False
    created_at = datetime.utcnow().isoformat()

    if image_data.startswith("data:image"):
        header, encoded = image_data.split(",", 1)
        extension = "jpg" if "jpeg" in header or "jpg" in header else "png"
        filename = f"scan_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.{extension}"
        target = UPLOAD_DIR / filename
        target.write_bytes(base64.b64decode(encoded))
        image_path = f"/static/uploads/{filename}"

    if not plate_number and image_path:
        recognized_plate, ocr_error = recognize_plate_from_image(BASE_DIR / image_path.lstrip("/"))
        plate_number = normalize_plate(recognized_plate)
        recognized_by_ocr = bool(plate_number)

    if not plate_number:
        if image_path:
            message = ocr_error or "Không đọc được biển số từ ảnh. Vui lòng thử ảnh rõ hơn hoặc nhập biển số thủ công."
        else:
            message = "Vui lòng chụp hoặc tải ảnh biển số, hoặc nhập biển số xe."
        return jsonify({"ok": False, "message": message, "ocr_error": ocr_error}), 400

    with get_db() as db:
        vehicle = db.execute("SELECT * FROM vehicles WHERE plate_number = ?", (plate_number,)).fetchone()
        if vehicle:
            color = vehicle["color"]
            list_type = vehicle["list_type"]
        else:
            color = "Chưa xác định"
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
                created_at,
            ),
        )

    scan_info = {
        "plate_number": plate_number,
        "color": color,
        "list_type": list_type,
        "location": location,
        "image_path": image_path,
        "police_name": session.get("full_name"),
        "created_at": created_at,
    }
    email_sent = False
    try:
        email_sent = send_scan_email(scan_info)
    except Exception:
        app.logger.exception("Không gửi được email thông báo lượt quét.")

    return jsonify(
        {
            "ok": True,
            "plate_number": plate_number,
            "color": color,
            "list_type": list_type,
            "is_blacklist": list_type == "blacklist",
            "email_sent": email_sent,
            "recognized_by_ocr": recognized_by_ocr,
            "message": "Phát hiện xe trong danh sách đen!" if list_type == "blacklist" else "Đã lưu lượt quét.",
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
        flash("Vui lòng nhập họ tên, tên đăng nhập và mật khẩu.", "error")
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
        flash("Đã thêm tài khoản cảnh sát.", "success")
    except sqlite3.IntegrityError:
        flash("Tên đăng nhập đã tồn tại.", "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/vehicles")
@login_required("admin")
def add_vehicle():
    plate_number = normalize_plate(request.form.get("plate_number"))
    color = request.form.get("color", "").strip() or "Chưa xác định"
    list_type = request.form.get("list_type", "blacklist")
    note = request.form.get("note", "").strip()
    if list_type not in {"blacklist", "whitelist"} or not plate_number:
        flash("Vui lòng nhập biển số hợp lệ và chọn loại danh sách.", "error")
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
        flash("Đã thêm xe.", "success")
    except sqlite3.IntegrityError:
        flash("Biển số này đã tồn tại.", "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/vehicles/<int:vehicle_id>/delete")
@login_required("admin")
def delete_vehicle(vehicle_id):
    with get_db() as db:
        db.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    flash("Đã xóa xe.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000, use_reloader=False)
