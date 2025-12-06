# Calendar Aggregator

A single-user calendar aggregation and publishing app that syncs multiple calendar sources (Google Calendar, Outlook/Office 365, Apple iCloud) and publishes a unified read-only calendar feed.

## Features

- **Multi-source calendar aggregation**: Connect Google Calendar (via OAuth), Outlook, iCloud, or any CalDAV-compatible calendar
- **Per-account masking**: Choose to show full event details or mask events as "Busy" for privacy
- **Unified calendar feed**: Subscribe to one ICS/webcal feed from any calendar client
- **Automatic sync**: Background sync every 10 minutes keeps your unified calendar up-to-date
- **Read-only access**: All calendar integrations use minimum read-only permissions - no write, modify, or email access
- **Secure**: Credentials are encrypted, feed URLs are protected with random tokens

## Setup on Replit

### 1. Environment Variables

The following environment variables are used:

| Variable | Description | Required |
|----------|-------------|----------|
| `ADMIN_USERNAME` | Admin login username | No (default: `admin`) |
| `ADMIN_PASSWORD` | Admin login password | No (default: `admin123`) |
| `SESSION_SECRET` | Secret key for password encryption | **Yes** (must be set in Secrets) |

**Important**:
- `SESSION_SECRET` is **required** for encrypting CalDAV passwords. The app will fail to start without it.
- Change the default admin credentials in production!

### 2. Google Calendar Integration

Google Calendar is connected via Replit's built-in OAuth integration:

1. The integration has already been authorized with read-only calendar permissions
2. When adding a Google Calendar source, your available calendars will be listed
3. No manual API key or OAuth setup required

**Permissions used** (all read-only):
- `calendar.events.readonly` - Read calendar events
- `calendar.calendars.readonly` - Read calendar list
- `calendar.freebusy` - Read free/busy status

### 3. CalDAV Sources (Outlook, iCloud, etc.)

For CalDAV-based calendars, you'll need:

- **CalDAV URL**: The calendar server URL
- **Username**: Usually your email address
- **Password**: An app-specific password (recommended for security)

#### Common CalDAV URLs:

| Provider | CalDAV URL |
|----------|------------|
| Apple iCloud | `https://caldav.icloud.com/` |
| Outlook/Office 365 | `https://outlook.office365.com/caldav/calendar/` |
| Fastmail | `https://caldav.fastmail.com/dav/calendars/user/USERNAME/` |
| Google (CalDAV) | `https://apidata.googleusercontent.com/caldav/v2/calid/events` |

#### Getting App-Specific Passwords:

- **Apple iCloud**: Go to appleid.apple.com > Security > App-Specific Passwords
- **Microsoft/Outlook**: Go to account.microsoft.com > Security > Advanced security options > App passwords
- **Google**: Go to myaccount.google.com > Security > 2-Step Verification > App passwords

## How to Use

### 1. Login

Navigate to your app URL and login with your admin credentials (default: `admin` / `admin123`).

### 2. Add Calendar Sources

1. Click "Add Source" on the dashboard
2. Choose the source type:
   - **Google Calendar**: Uses the authorized OAuth connection
   - **Generic CalDAV / Outlook / iCloud**: Enter CalDAV URL and credentials
3. Set the **Masking** option:
   - **OFF**: Full event details appear in the unified calendar
   - **ON**: Events appear as "Busy" with no details (for privacy)
4. Click "Add Source" - the calendar will sync immediately

### 3. Subscribe to the Unified Calendar

1. On the dashboard, find the **Subscription URLs** section
2. Copy the ICS URL or Webcal URL
3. Add to your calendar client:

#### Google Calendar:
1. Go to calendar.google.com
2. Click the + next to "Other calendars"
3. Select "From URL"
4. Paste the ICS URL

#### Apple Calendar:
1. Go to File > New Calendar Subscription
2. Paste the ICS URL
3. Set refresh interval as desired

#### Outlook:
1. Go to Settings > Calendar > Shared calendars
2. Under "Subscribe from web", paste the ICS URL

### 4. Manual Sync

- Click "Sync" next to any source to sync it immediately
- Click "Sync All" to sync all sources at once
- Background sync runs automatically every 10 minutes

## Masking Behavior

| Masking | Published Calendar Shows |
|---------|-------------------------|
| OFF | Full event title, description, location, and times |
| ON | "Busy" title only, with correct time range (no details) |

In the admin UI, you always see full event details regardless of masking.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard (requires login) |
| `GET /login` | Login page |
| `GET /preview` | Preview unified calendar with masking applied |
| `GET /feed/{token}/calendar.ics` | ICS feed (token required) |
| `GET /health` | Health check endpoint |

## Technical Details

### Technology Stack

- **Backend**: Python 3.11 with FastAPI
- **Database**: SQLite with SQLAlchemy ORM
- **Calendar Libraries**: caldav, icalendar
- **Background Jobs**: APScheduler
- **Templates**: Jinja2

### Data Model

- **CalendarSource**: Stores calendar connection details and masking settings
- **Event**: Stores synced events with original details
- **AppSettings**: Stores the feed token

### Security

- Passwords are encrypted using Fernet (AES-128)
- Session tokens are HTTP-only cookies
- Feed URLs include a random 32-character token
- No credentials are logged

## Limitations

1. **ICS feed only**: A full CalDAV server is not implemented; only ICS/webcal subscriptions are supported
2. **Single user**: This app is designed for personal use, not multi-tenant
3. **Read-only**: Cannot create or modify events on source calendars
4. **Sync delay**: Changes may take up to 10 minutes to appear (or trigger manual sync)

## Troubleshooting

### "Could not get Google access token"
The Google Calendar OAuth connection may have expired. Re-authorize in the Replit Integrations panel.

### CalDAV sync fails
- Verify the CalDAV URL is correct
- Ensure you're using an app-specific password (not your regular password)
- Check that your account has CalDAV access enabled

### Events not showing
- Check that the source is enabled (green checkbox in edit form)
- Verify the sync status shows "Success"
- Try a manual sync
