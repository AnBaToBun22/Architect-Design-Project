
# Vehicle Number Plate Recognition - Web Version

Du an mau chuyen tu mo hinh Android + ASP.NET sang Web-based:

- Backend: Python Flask
- Frontend: HTML, CSS, JavaScript
- Database: SQLite de demo nhanh
- Police UI: dang nhap, mo camera bang trinh duyet, chup anh bien so, gui len server
- Admin UI: quan ly police, blacklist/whitelist, scan logs, thong bao xe blacklist

## Tai khoan mac dinh

| Role | Username | Password |
| --- | --- | --- |
| Admin | `admin` | `admin123` |
| Police | `police01` | `police123` |

## Chay du an

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Mo trinh duyet tai:

```text
http://127.0.0.1:5000
```

## Cau truc

```text
.
|-- app.py
|-- requirements.txt
|-- vehicle_plate.db       # tu sinh khi chay
|-- static
|   |-- css
|   |   `-- style.css
|   `-- js
|       |-- admin.js
|       `-- police.js
`-- templates
    |-- admin.html
    |-- layout.html
    |-- login.html
    `-- police.html
```

## Ghi chu OCR

Ban demo don gian uu tien luong nghiep vu hoan chinh. Police co the chup anh va nhap bien so doc duoc. Module `recognize_plate_from_image` trong `app.py` da duoc tach rieng de sau nay thay bang OpenCV + Tesseract/EasyOCR.

# Architect-Design-Project

