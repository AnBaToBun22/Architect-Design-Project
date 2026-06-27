
# Nhận diện biển số xe - phiên bản Web

Dự án mẫu chuyển từ mô hình Android + ASP.NET sang nền tảng Web:

- Backend: Python Flask
- Frontend: HTML, CSS, JavaScript
- Database: SQLite để demo nhanh
- Giao diện cảnh sát: đăng nhập, mở camera bằng trình duyệt, chụp ảnh biển số, gửi lên server
- Giao diện quản trị: quản lý cảnh sát, danh sách đen/trắng, lịch sử quét, thông báo xe trong danh sách đen

## Tài khoản mặc định

| Vai trò | Tên đăng nhập | Mật khẩu |
| --- | --- | --- |
| Quản trị | `admin` | `admin123` |
| Cảnh sát | `police01` | `police123` |

## Chạy dự án

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Mở trình duyệt tại:

```text
http://127.0.0.1:5000
```

## Cấu trúc

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

## Ghi chú OCR

Bản hiện tại dùng OpenCV + Tesseract để đọc biển số từ ảnh tải lên hoặc ảnh chụp từ camera. Ngoài các thư viện trong `requirements.txt`, máy chạy server cần cài Tesseract OCR và thêm lệnh `tesseract` vào `PATH`.

Trên Windows có thể cài Tesseract từ UB Mannheim, sau đó kiểm tra:

```powershell
tesseract --version
```

Nếu OCR chưa đọc được biển số, cảnh sát vẫn có thể nhập biển số thủ công rồi bấm quét để kiểm tra blacklist/whitelist.

# Architect-Design-Project

