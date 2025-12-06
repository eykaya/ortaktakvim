# Calendar Aggregator

## Overview

A multi-user calendar aggregation app that syncs multiple calendar sources (Google Calendar, Outlook/Office 365, Apple iCloud via CalDAV, ICS/Webcal feeds) and publishes per-user unified read-only ICS/webcal calendar feeds with per-account masking.

## Recent Changes

- **2024-12-06**: Multi-User Architecture & Sync Management
  - Added User model with roles (Admin, User)
  - Per-user calendar sources and ICS feeds
  - Admin panel for user management (add/remove users, reset passwords)
  - Global settings for base URL and public domain configuration
  - Configurable sync interval (1-1440 minutes) in admin panel
  - Manual sync button for immediate synchronization
  - Application log viewer in admin panel
  - Profile page for users to manage their settings and feed tokens
  - Database-backed sessions for persistence across server restarts
  - Removed Replit-specific dependencies for standard Linux deployment
  - Created DEPLOY.md and setup.sh for easy deployment

- **2024-12-03**: Custom OAuth Settings
  - Added Settings page for user-managed OAuth credentials
  - Users can configure their own Google Cloud and Azure App credentials
  - Full control over OAuth permissions (only calendar.readonly scopes)
  - Token storage with automatic refresh support

- **2024-12-03**: Enhanced with visual calendar and OAuth support
  - Added FullCalendar.js visual calendar preview (month/week/day/list views)
  - Microsoft Outlook OAuth integration (read-only calendar access)
  - Google Calendar OAuth already integrated (read-only)
  - Apple iCloud uses CalDAV with app-password (Apple doesn't support OAuth for CalDAV)
  - ICS/Webcal feed support for public shared calendars

## User Preferences

- All calendar integrations must use **read-only** permissions only
- No write, modify, delete, or email access should be requested
- Simple, functional UI over complex styling
- Self-hostable on standard Linux systems without cloud dependencies

## Project Architecture

```
/
├── main.py                 # FastAPI application entry point
├── src/
│   ├── __init__.py
│   ├── database.py         # SQLAlchemy database configuration
│   ├── models.py           # User, CalendarSource, Event, GlobalSettings, ApplicationLog models
│   ├── auth.py             # Multi-user authentication with bcrypt password hashing
│   ├── crypto.py           # Password encryption/decryption (Fernet AES-128)
│   ├── settings_service.py # Global settings management
│   ├── logging_service.py  # Application logging to database
│   ├── custom_oauth_service.py  # Google/Microsoft OAuth integration
│   ├── caldav_service.py   # CalDAV client for Outlook/iCloud
│   ├── ics_feed_service.py # ICS/Webcal feed fetcher
│   ├── sync_service.py     # Calendar sync orchestration
│   ├── ics_generator.py    # Unified ICS feed generation
│   └── scheduler.py        # APScheduler background sync
├── templates/
│   ├── base.html           # Base template with navigation
│   ├── login.html          # Login page
│   ├── dashboard.html      # User dashboard
│   ├── admin.html          # Admin panel (users, settings)
│   ├── logs.html           # Application log viewer
│   ├── profile.html        # User profile page
│   ├── sources_add.html    # Add calendar source form
│   ├── sources_edit.html   # Edit calendar source form
│   ├── settings.html       # OAuth settings (admin only)
│   └── preview.html        # Unified calendar preview
├── calendar_aggregator.db  # SQLite database (auto-created)
├── requirements.txt        # Python dependencies
├── DEPLOY.md               # Deployment guide for Linux systems
└── .gitignore
```

## Multi-User Architecture

### User Roles

- **Admin**: Can manage users, configure OAuth settings, view logs, set base URL/domain
- **User**: Can add/manage their own calendar sources, has unique ICS feed URL

### Data Isolation

- Each user has their own calendar sources
- Each user gets a unique feed token for their ICS feed
- OAuth tokens are stored per-user (each user connects their own Google/Microsoft account)
- Admin configures global OAuth client credentials (Client ID/Secret)

### Key Models

- `User`: username, hashed_password, role (admin/user), feed_token
- `CalendarSource`: user_id, name, source_type, credentials
- `OAuthToken`: user_id, provider, encrypted tokens
- `GlobalSettings`: key-value pairs for base_url, public_domain, etc.
- `ApplicationLog`: level, message, source, details, timestamp

## Environment Variables

- `SESSION_SECRET`: **Required** - Encryption key for passwords and session security
- `ADMIN_USERNAME`: Admin login (default: "admin")
- `ADMIN_PASSWORD`: Admin password (default: "admin123")
- `HOST`: Server host (default: "0.0.0.0")
- `PORT`: Server port (default: 5000)

## Key Technical Decisions

1. **Multi-user with per-user feeds**: Each user has isolated calendar sources and unique ICS feed
2. **SQLite database**: Simple, file-based, no external service needed
3. **Custom OAuth**: Admin sets client credentials, users connect their own accounts
4. **APScheduler**: Lightweight async scheduler for background sync
5. **Fernet encryption**: AES-128 encryption for stored passwords and tokens
6. **No Replit dependencies**: Can be deployed on any Linux system with Python 3.11+
7. **Database-backed sessions**: User sessions stored in SQLite, persist across server restarts

## Running the App

### Development (Replit)
The app runs on port 5000 via the "Start application" workflow.

### Production (Standard Linux)
```bash
# With virtual environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py

# With Gunicorn (recommended for production)
gunicorn -w 4 -b 0.0.0.0:5000 main:app -k uvicorn.workers.UvicornWorker
```

See DEPLOY.md for full deployment instructions including Docker, systemd, and nginx configuration.
