# 🖥️ Cross-Platform System Health Monitor

A complete system health monitoring project with:
- **Go Client Utility**: Collects system health data (disk encryption, OS updates, antivirus, sleep settings) and sends to backend.
- **Python Backend (Flask)**: Receives data, stores in SQLite, exposes APIs with filtering and CSV export.
- **HTML/JS Dashboard**: Displays system status, allows filtering by OS and issue flags, auto-refreshes.

---

## 📂 Project Structure
```
.
├── client/           # Go client utility
│   └── main.go
├── backend/          # Python backend API
│   └── app.py
├── frontend/         # Dashboard UI
│   └── index.html
└── README.md
```

---

## 🚀 Getting Started

### 1️⃣ Install Requirements

#### Go Client
- Install Go: [https://go.dev/dl/](https://go.dev/dl/)
- Verify:
```bash
go version
```

#### Python Backend
- Python 3.8+ required
- Install dependencies:
```bash
pip install flask flask-cors
```

---

### 2️⃣ Run Backend API

```bash
cd backend
python app.py
```
Backend runs at:
```
http://localhost:5000
```

---

### 3️⃣ Run Go Client Utility

```bash
cd client
go build -o sysutil main.go
./sysutil
```

The client will:
- Collect system health data
- Print results to screen
- Send results to backend every **30 minutes**

---
You can build executable binary for any platform from your dev machine:

#### macOS
```bash
GOOS=darwin GOARCH=amd64 go build -o sysutil-darwin-amd64
GOOS=darwin GOARCH=arm64 go build -o sysutil-darwin-arm64
```
#### Windows
```bash
GOOS=windows GOARCH=amd64 go build -o sysutil-windows-amd64.exe
```
#### Linux
```bash
GOOS=linux GOARCH=amd64 go build -o sysutil-linux-amd64
```

### 4️⃣ View Dashboard

Open `frontend/index.html` in your browser.  
The dashboard will:
- Fetch system list from backend
- Show OS, last check-in, and status flags
- Allow filtering by OS and issue status
- Auto-refresh every 60 seconds

---

## 📡 API Endpoints

### `POST /report`
Receives system data from client:
```json
{
  "machine_id": "00:1A:2B:3C:4D:5E",
  "machine_name": "MyLaptop",
  "os": "Ubuntu",
  "os_version": "22.04",
  "checks": {
    "disk_encrypted": true,
    "os_up_to_date": false,
    "antivirus_present": true,
    "inactivity_sleep_minutes": 5
  }
}
```

### `GET /machines`
Returns latest status for all machines.

Query params:
- `os` → filter by OS
- `has_issues` → `true` or `false`

### `GET /export`
Returns CSV export of the latest status.

---

## 🛠 Development Notes
- Go client uses platform-specific commands for checks.
- Backend stores `has_issues` flag in DB if **any** of:
  - Disk not encrypted
  - OS not up-to-date
  - No antivirus present
- Dashboard fetches live data and auto-refreshes.

---

## ⚠️ Permissions
- Linux/macOS encryption checks may require `sudo`.
- Windows update & AV checks may require PowerShell execution permissions.

---

## 📜 License
MIT License
