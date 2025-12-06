# Calendar Aggregator - Deployment Guide

This guide explains how to deploy the Calendar Aggregator on a standard Linux system.

## System Requirements

- Python 3.11+
- SQLite3
- 512MB RAM minimum
- 1GB disk space

## Quick Start (Otomatik Kurulum)

En kolay kurulum için interaktif setup scriptini kullanın:

```bash
git clone <repository-url>
cd calendar-aggregator

# Otomatik kurulum scripti
chmod +x setup.sh
./setup.sh
```

Script sizden:
- Admin kullanıcı adı
- Admin şifresi (en az 8 karakter)
- Sunucu portu

bilgilerini isteyecek ve otomatik olarak:
- Güvenli SESSION_SECRET oluşturacak
- .env dosyasını yapılandıracak
- Virtual environment kuracak
- Bağımlılıkları yükleyecek

## Manuel Kurulum

### 1. Clone and Setup

```bash
git clone <repository-url>
cd calendar-aggregator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file in the project root:

```bash
# KRITIK: Guvenli bir anahtar olusturun
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET=your-secure-secret-key-here

# Admin hesabi (ilk giris icin)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# Sunucu ayarlari
HOST=0.0.0.0
PORT=5000
```

**ÖNEMLİ**: `SESSION_SECRET` değerini değiştirirseniz tüm kullanıcıların oturumları kapanır. Sunucu yeniden başlatıldığında bu değer aynı kaldığı sürece oturumlar korunur.

### 3. Run the Application

```bash
# Development mode
source venv/bin/activate
python main.py

# Production mode with Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app -k uvicorn.workers.UvicornWorker
```

## Production Deployment

### Using systemd

Create `/etc/systemd/system/calendar-aggregator.service`:

```ini
[Unit]
Description=Calendar Aggregator
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/calendar-aggregator
Environment="PATH=/opt/calendar-aggregator/venv/bin"
EnvironmentFile=/opt/calendar-aggregator/.env
ExecStart=/opt/calendar-aggregator/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 main:app -k uvicorn.workers.UvicornWorker
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable calendar-aggregator
sudo systemctl start calendar-aggregator
```

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "main:app", "-k", "uvicorn.workers.UvicornWorker"]
```

Build and run:

```bash
docker build -t calendar-aggregator .
docker run -d -p 5000:5000 \
  -e SESSION_SECRET=your-secret-here \
  -v ./data:/app/data \
  calendar-aggregator
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## OAuth Configuration

### Google Calendar

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "Google Calendar API"
4. Create OAuth 2.0 credentials:
   - Application type: Web application
   - Authorized redirect URIs: `https://your-domain.com/auth/google/callback`
5. Copy Client ID and Client Secret
6. Add them in Admin > Settings

Required scopes (automatically requested):
- `https://www.googleapis.com/auth/calendar.readonly`

### Microsoft Outlook/Office 365

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to Azure Active Directory > App registrations
3. New registration:
   - Name: Calendar Aggregator
   - Supported account types: Choose based on your needs
   - Redirect URI: Web - `https://your-domain.com/auth/outlook/callback`
4. Under "API permissions", add:
   - Microsoft Graph > Delegated > `Calendars.Read`
5. Create a client secret under "Certificates & secrets"
6. Add Client ID, Client Secret, and Tenant ID in Admin > Settings

**Tenant ID options:**
- `common` - All Microsoft accounts
- `organizations` - Work/school accounts only
- `consumers` - Personal Microsoft accounts only
- `{tenant-id}` - Specific organization only

## Multi-User Setup

1. Default admin account is created on first start:
   - Username: `admin` (or from ADMIN_USERNAME env)
   - Password: `admin123` (or from ADMIN_PASSWORD env)

2. Change default password immediately after first login

3. Create user accounts in Admin > Users

4. Each user:
   - Has their own calendar sources
   - Gets a unique ICS feed URL
   - Can connect their own Google/Microsoft accounts

## Base URL Configuration

For proper OAuth redirects, configure the Base URL in Admin > General Settings:

- **Base URL**: The public URL of your application (e.g., `https://calendar.example.com`)
- **Public Domain**: Optional separate domain for ICS feed URLs

## Database

The application uses SQLite by default. The database file is `calendar_aggregator.db` in the project root.

### Backup

```bash
# Simple backup
cp calendar_aggregator.db calendar_aggregator.db.backup

# With date
cp calendar_aggregator.db "backups/calendar_$(date +%Y%m%d_%H%M%S).db"
```

### Migration

Database migrations are automatic on startup. The schema is created/updated when the application starts.

## Troubleshooting

### OAuth Errors

- Verify redirect URIs match exactly (including trailing slashes)
- Ensure Base URL is set correctly in Admin > General Settings
- Check that OAuth credentials are correct

### Sync Issues

- Check Admin > Logs for error messages
- Verify OAuth tokens are not expired
- For CalDAV, verify URL and credentials

### Port Already in Use

```bash
# Find process using port 5000
lsof -i :5000

# Kill process
kill -9 <PID>
```

## Security Recommendations

1. **Change default credentials** immediately after deployment
2. **Use HTTPS** in production with valid SSL certificates
3. **Set a strong SESSION_SECRET** - Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
4. **Regular backups** of the database
5. **Keep dependencies updated** - Run `pip install -U -r requirements.txt` periodically
