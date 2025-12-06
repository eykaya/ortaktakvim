import os
import secrets
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.database import engine, get_db, Base
from src.models import (
    CalendarSource, Event, AppSettings, SourceType, OAuthSettings, OAuthToken,
    User, UserRole, GlobalSettings, ApplicationLog
)
from src.auth import (
    require_auth, require_admin, get_current_user_from_session,
    authenticate_user, create_session, destroy_session, hash_password,
    create_default_admin, is_admin
)
from src.crypto import encrypt_password
from src.sync_service import sync_calendar_source, sync_all_sources
from src.ics_generator import generate_unified_ics, get_unified_events
from src.scheduler import start_scheduler, stop_scheduler
from src.custom_oauth_service import (
    get_oauth_settings, save_oauth_settings, get_oauth_token, save_oauth_token,
    delete_oauth_token, get_decrypted_client_secret,
    build_google_auth_url, build_microsoft_auth_url,
    exchange_google_code, exchange_microsoft_code,
    get_valid_google_token, get_valid_microsoft_token,
    list_google_calendars_custom, list_microsoft_calendars_custom,
    get_google_user_email, get_microsoft_user_email
)
from src.settings_service import (
    get_setting, set_setting, get_all_settings, get_base_url as get_base_url_setting,
    initialize_default_settings
)
from src.logging_service import get_logs, add_log, clear_old_logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    create_default_admin(db)
    initialize_default_settings(db)
    
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(feed_token=secrets.token_urlsafe(32))
        db.add(settings)
        db.commit()
    db.close()
    
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Calendar Aggregator", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


def get_base_url(request: Request, db: Session = None) -> str:
    if db:
        custom_url = get_setting(db, 'base_url')
        if custom_url and custom_url != 'http://localhost:5000':
            return custom_url.rstrip('/')
    
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost:5000")
    return f"{proto}://{host}"


def get_public_domain(db: Session) -> str:
    return get_setting(db, 'public_domain', '')


def get_feed_token(db: Session, user: User = None) -> str:
    if user and user.feed_token:
        return user.feed_token
    settings = db.query(AppSettings).first()
    if settings:
        return settings.feed_token
    return ""


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    sources = db.query(CalendarSource).filter(
        CalendarSource.user_id == user.id
    ).order_by(CalendarSource.created_at.desc()).all()
    events = get_unified_events(db, apply_masking=True, upcoming_only=True, user_id=user.id)
    
    base_url = get_base_url(request, db)
    public_domain = get_public_domain(db)
    feed_url_base = public_domain if public_domain else base_url
    feed_token = get_feed_token(db, user)
    ics_url = f"{feed_url_base}/feed/{feed_token}/calendar.ics"
    webcal_url = ics_url.replace("https://", "webcal://").replace("http://", "webcal://")
    
    message = request.query_params.get("message")
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "is_admin": is_admin(user),
        "sources": sources,
        "events": events,
        "ics_url": ics_url,
        "webcal_url": webcal_url,
        "message": message
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, db: Session = Depends(get_db), username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(db, username, password)
    if user:
        session_token = create_session(request, user, db)
        add_log(db, "INFO", f"User '{username}' logged in", source="auth")
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=604800
        )
        return response
    
    add_log(db, "WARNING", f"Failed login attempt for user '{username}'", source="auth")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid username or password"
    })


@app.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    session_token = request.cookies.get("session_token")
    if session_token:
        destroy_session(request, session_token, db)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    from src.scheduler import get_current_interval, get_next_run_time
    
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    users = db.query(User).order_by(User.created_at.desc()).all()
    settings = get_all_settings(db)
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    
    next_sync = get_next_run_time()
    current_interval = get_current_interval()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user,
        "is_admin": True,
        "users": users,
        "settings": settings,
        "message": message,
        "error": error,
        "next_sync": next_sync,
        "current_interval": current_interval
    })


@app.post("/admin/users/add")
async def add_user(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
    role: str = Form("user")
):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return RedirectResponse(url="/admin?error=Username already exists", status_code=302)
    
    new_user = User(
        username=username,
        email=email if email else None,
        hashed_password=hash_password(password),
        role=UserRole.ADMIN if role == "admin" else UserRole.USER,
        is_active=True,
        feed_token=secrets.token_hex(32)
    )
    db.add(new_user)
    db.commit()
    
    add_log(db, "INFO", f"Admin '{admin.username}' created user '{username}'", source="admin")
    return RedirectResponse(url="/admin?message=User created successfully", status_code=302)


@app.post("/admin/users/{user_id}/delete")
async def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/admin?error=User not found", status_code=302)
    
    if target_user.id == admin.id:
        return RedirectResponse(url="/admin?error=Cannot delete yourself", status_code=302)
    
    username = target_user.username
    db.delete(target_user)
    db.commit()
    
    add_log(db, "INFO", f"Admin '{admin.username}' deleted user '{username}'", source="admin")
    return RedirectResponse(url="/admin?message=User deleted successfully", status_code=302)


@app.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    new_password: str = Form(...)
):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/admin?error=User not found", status_code=302)
    
    target_user.hashed_password = hash_password(new_password)
    db.commit()
    
    add_log(db, "INFO", f"Admin '{admin.username}' reset password for user '{target_user.username}'", source="admin")
    return RedirectResponse(url="/admin?message=Password reset successfully", status_code=302)


@app.post("/admin/users/{user_id}/toggle-active")
async def toggle_user_active(request: Request, user_id: int, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/admin?error=User not found", status_code=302)
    
    if target_user.id == admin.id:
        return RedirectResponse(url="/admin?error=Cannot deactivate yourself", status_code=302)
    
    target_user.is_active = not target_user.is_active
    db.commit()
    
    status = "activated" if target_user.is_active else "deactivated"
    add_log(db, "INFO", f"Admin '{admin.username}' {status} user '{target_user.username}'", source="admin")
    return RedirectResponse(url=f"/admin?message=User {status} successfully", status_code=302)


@app.post("/admin/settings/general")
async def save_general_settings(
    request: Request,
    db: Session = Depends(get_db),
    base_url: str = Form(""),
    public_domain: str = Form(""),
    app_name: str = Form(""),
    sync_interval: str = Form("10")
):
    from src.scheduler import update_sync_interval
    
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    if base_url:
        set_setting(db, 'base_url', base_url.rstrip('/'))
    if public_domain:
        set_setting(db, 'public_domain', public_domain.rstrip('/'))
    if app_name:
        set_setting(db, 'app_name', app_name)
    if sync_interval:
        try:
            interval_int = int(sync_interval)
            if interval_int < 1:
                interval_int = 1
            if interval_int > 1440:
                interval_int = 1440
            set_setting(db, 'sync_interval_minutes', str(interval_int))
            update_sync_interval(interval_int)
        except ValueError:
            pass
    
    add_log(db, "INFO", f"Admin '{admin.username}' updated general settings", source="admin")
    return RedirectResponse(url="/admin?message=Settings saved successfully", status_code=302)


@app.post("/admin/sync/trigger")
async def trigger_manual_sync(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    add_log(db, "INFO", f"Admin '{admin.username}' triggered manual sync", source="admin")
    
    results = await sync_all_sources(db)
    success_count = sum(1 for r in results.values() if r["success"])
    fail_count = len(results) - success_count
    
    if fail_count == 0:
        message = f"Sync completed: {success_count} source(s) synced successfully"
    else:
        message = f"Sync completed: {success_count} success, {fail_count} failed"
    
    return RedirectResponse(url=f"/admin?message={message}", status_code=302)


@app.get("/admin/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    db: Session = Depends(get_db),
    level: str = Query(None),
    hours: int = Query(24),
    limit: int = Query(100)
):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    logs = get_logs(db, limit=limit, level=level, hours=hours)
    
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "user": admin,
        "is_admin": True,
        "logs": logs,
        "current_level": level,
        "current_hours": hours,
        "current_limit": limit
    })


@app.post("/admin/logs/clear")
async def clear_logs(request: Request, db: Session = Depends(get_db), days: int = Form(30)):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    deleted = clear_old_logs(db, days=days)
    add_log(db, "INFO", f"Admin '{admin.username}' cleared {deleted} old logs", source="admin")
    return RedirectResponse(url="/admin/logs?message=Cleared old logs", status_code=302)


@app.get("/sources/add", response_class=HTMLResponse)
async def add_source_page(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    google_settings = get_oauth_settings(db, "google")
    outlook_settings = get_oauth_settings(db, "outlook")
    
    google_configured = google_settings and google_settings.is_configured
    outlook_configured = outlook_settings and outlook_settings.is_configured
    
    google_calendars = []
    google_connected = False
    google_email = ""
    outlook_calendars = []
    outlook_connected = False
    outlook_email = ""
    
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    
    google_token = get_oauth_token(db, "google", user_id=user.id)
    outlook_token = get_oauth_token(db, "outlook", user_id=user.id)
    
    if google_configured and google_token:
        try:
            access_token = await get_valid_google_token(db, user_id=user.id)
            if access_token:
                google_connected = True
                google_email = await get_google_user_email(access_token)
                google_calendars = await list_google_calendars_custom(access_token)
        except Exception as e:
            print(f"Error fetching Google calendars: {e}")
            error = f"Google error: {e}"
    
    if outlook_configured and outlook_token:
        try:
            access_token = await get_valid_microsoft_token(db, user_id=user.id)
            if access_token:
                outlook_connected = True
                outlook_email = await get_microsoft_user_email(access_token)
                outlook_calendars = await list_microsoft_calendars_custom(access_token)
        except Exception as e:
            print(f"Error fetching Outlook calendars: {e}")
    
    return templates.TemplateResponse("sources_add.html", {
        "request": request,
        "user": user,
        "is_admin": is_admin(user),
        "error": error,
        "message": message,
        "google_configured": google_configured,
        "google_connected": google_connected,
        "google_email": google_email,
        "google_calendars": google_calendars,
        "outlook_configured": outlook_configured,
        "outlook_connected": outlook_connected,
        "outlook_email": outlook_email,
        "outlook_calendars": outlook_calendars
    })


@app.post("/sources/add", response_class=HTMLResponse)
async def add_source(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    source_type: str = Form(...),
    caldav_url: str = Form(None),
    ics_url: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    google_calendar_id: str = Form(None),
    outlook_calendar_id: str = Form(None),
    masking: bool = Form(False)
):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        source_type_enum = SourceType(source_type)
    except ValueError:
        source_type_enum = SourceType.CALDAV
    
    encrypted_pwd = encrypt_password(password) if password else None
    
    url_to_use = ics_url if source_type_enum == SourceType.ICS_FEED else caldav_url
    
    source = CalendarSource(
        user_id=user.id,
        name=name,
        source_type=source_type_enum,
        caldav_url=url_to_use,
        username=username,
        encrypted_password=encrypted_pwd,
        google_calendar_id=google_calendar_id or "primary",
        outlook_calendar_id=outlook_calendar_id,
        masking=masking
    )
    
    db.add(source)
    db.commit()
    
    add_log(db, "INFO", f"User '{user.username}' added calendar source '{name}'", source="calendar")
    success, message = await sync_calendar_source(db, source, user_id=user.id)
    
    return RedirectResponse(
        url=f"/?message=Source added successfully. Sync: {message}",
        status_code=302
    )


@app.get("/sources/{source_id}/edit", response_class=HTMLResponse)
async def edit_source_page(request: Request, source_id: int, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    source = db.query(CalendarSource).filter(
        CalendarSource.id == source_id,
        CalendarSource.user_id == user.id
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return templates.TemplateResponse("sources_edit.html", {
        "request": request,
        "user": user,
        "is_admin": is_admin(user),
        "source": source,
        "error": None
    })


@app.post("/sources/{source_id}/edit", response_class=HTMLResponse)
async def edit_source(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db),
    name: str = Form(...),
    caldav_url: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    google_calendar_id: str = Form(None),
    masking: bool = Form(False),
    is_enabled: bool = Form(False)
):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    source = db.query(CalendarSource).filter(
        CalendarSource.id == source_id,
        CalendarSource.user_id == user.id
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    source.name = name
    source.caldav_url = caldav_url
    source.username = username
    source.google_calendar_id = google_calendar_id or "primary"
    source.masking = masking
    source.is_enabled = is_enabled
    
    if password:
        source.encrypted_password = encrypt_password(password)
    
    db.commit()
    
    return RedirectResponse(url="/?message=Source updated successfully", status_code=302)


@app.post("/sources/{source_id}/delete")
async def delete_source(request: Request, source_id: int, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    source = db.query(CalendarSource).filter(
        CalendarSource.id == source_id,
        CalendarSource.user_id == user.id
    ).first()
    if source:
        db.delete(source)
        db.commit()
    
    return RedirectResponse(url="/?message=Source deleted successfully", status_code=302)


@app.post("/sources/{source_id}/sync")
async def sync_source(request: Request, source_id: int, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    source = db.query(CalendarSource).filter(
        CalendarSource.id == source_id,
        CalendarSource.user_id == user.id
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    success, message = await sync_calendar_source(db, source, user_id=user.id)
    
    return RedirectResponse(
        url=f"/?message=Sync {'completed' if success else 'failed'}: {message}",
        status_code=302
    )


@app.post("/sync-all")
async def sync_all(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    results = await sync_all_sources(db, user_id=user.id)
    
    success_count = sum(1 for r in results.values() if r["success"])
    total_count = len(results)
    
    return RedirectResponse(
        url=f"/?message=Synced {success_count}/{total_count} sources",
        status_code=302
    )


@app.get("/preview", response_class=HTMLResponse)
async def preview(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    events = get_unified_events(db, apply_masking=True, upcoming_only=True, user_id=user.id)
    
    return templates.TemplateResponse("preview.html", {
        "request": request,
        "user": user,
        "is_admin": is_admin(user),
        "events": events
    })


@app.get("/feed/{token}/calendar.ics")
async def ics_feed(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.feed_token == token).first()
    if user:
        ics_content = generate_unified_ics(db, apply_masking=True, user_id=user.id)
    else:
        settings = db.query(AppSettings).first()
        if not settings or settings.feed_token != token:
            raise HTTPException(status_code=403, detail="Invalid feed token")
        ics_content = generate_unified_ics(db, apply_masking=True)
    
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": "attachment; filename=calendar.ics",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )


@app.get("/api/events")
async def api_events(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    events = get_unified_events(db, apply_masking=True, upcoming_only=False, user_id=user.id)
    
    fullcalendar_events = []
    for event in events:
        if event["is_masked"]:
            fc_event = {
                "id": event["id"],
                "title": event["summary"],
                "start": event["start"].isoformat(),
                "end": event["end"].isoformat(),
                "allDay": event["is_all_day"],
                "extendedProps": {
                    "source": event["source_name"],
                    "location": "",
                    "description": "",
                    "isMasked": True
                },
                "backgroundColor": "#e74c3c",
                "borderColor": "#c0392b"
            }
        else:
            fc_event = {
                "id": event["id"],
                "title": event["summary"],
                "start": event["start"].isoformat(),
                "end": event["end"].isoformat(),
                "allDay": event["is_all_day"],
                "extendedProps": {
                    "source": event["source_name"],
                    "location": event["location"],
                    "description": event["description"],
                    "isMasked": False
                },
                "backgroundColor": "#3498db",
                "borderColor": "#2980b9"
            }
        
        fullcalendar_events.append(fc_event)
    
    return fullcalendar_events


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    google_settings = get_oauth_settings(db, "google")
    outlook_settings = get_oauth_settings(db, "outlook")
    google_token = get_oauth_token(db, "google")
    outlook_token = get_oauth_token(db, "outlook")
    
    base_url = get_base_url(request, db)
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "is_admin": True,
        "google_settings": google_settings,
        "outlook_settings": outlook_settings,
        "google_token": google_token,
        "outlook_token": outlook_token,
        "base_url": base_url,
        "message": message,
        "error": error
    })


@app.post("/settings/google")
async def save_google_settings(
    request: Request,
    client_id: str = Form(""),
    client_secret: str = Form(""),
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    if client_id:
        save_oauth_settings(db, "google", client_id, client_secret)
        return RedirectResponse(url="/settings?message=Google settings saved", status_code=302)
    
    return RedirectResponse(url="/settings?error=Client ID is required", status_code=302)


@app.post("/settings/outlook")
async def save_outlook_settings(
    request: Request,
    client_id: str = Form(""),
    client_secret: str = Form(""),
    tenant_id: str = Form(""),
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    if client_id:
        save_oauth_settings(db, "outlook", client_id, client_secret, tenant_id)
        return RedirectResponse(url="/settings?message=Outlook settings saved", status_code=302)
    
    return RedirectResponse(url="/settings?error=Client ID is required", status_code=302)


@app.get("/auth/google")
async def google_auth_start(request: Request, return_to: str = None, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    settings = get_oauth_settings(db, "google")
    if not settings or not settings.is_configured:
        return RedirectResponse(url="/settings?error=Google OAuth not configured", status_code=302)
    
    base_url = get_base_url(request, db)
    redirect_uri = f"{base_url}/auth/google/callback"
    state = f"{user.id}|{return_to or 'settings'}"
    auth_url = build_google_auth_url(settings.client_id, redirect_uri, state=state)
    
    return RedirectResponse(url=auth_url)


@app.get("/auth/google/callback")
async def google_auth_callback(request: Request, code: str = None, error: str = None, state: str = None, db: Session = Depends(get_db)):
    parts = (state or "").split("|")
    user_id = int(parts[0]) if parts and parts[0].isdigit() else None
    return_path = parts[1] if len(parts) > 1 else "settings"
    return_url = "/sources/add" if return_path == "sources_add" else "/settings"
    
    if error:
        return RedirectResponse(url=f"{return_url}?error=Google auth failed: {error}", status_code=302)
    
    if not code:
        return RedirectResponse(url=f"{return_url}?error=No authorization code received", status_code=302)
    
    settings = get_oauth_settings(db, "google")
    if not settings:
        return RedirectResponse(url=f"{return_url}?error=Google OAuth not configured", status_code=302)
    
    base_url = get_base_url(request, db)
    redirect_uri = f"{base_url}/auth/google/callback"
    client_secret = get_decrypted_client_secret(settings)
    
    try:
        tokens = await exchange_google_code(code, settings.client_id, client_secret, redirect_uri)
        save_oauth_token(
            db, "google",
            tokens["access_token"],
            tokens.get("refresh_token"),
            tokens.get("expires_in"),
            user_id=user_id
        )
        return RedirectResponse(url=f"{return_url}?message=Google account connected successfully", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"{return_url}?error=Failed to connect Google: {str(e)}", status_code=302)


@app.get("/auth/google/disconnect")
async def google_auth_disconnect(request: Request, return_to: str = None, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    delete_oauth_token(db, "google", user_id=user.id)
    return_url = "/sources/add" if return_to == "sources_add" else "/settings"
    return RedirectResponse(url=f"{return_url}?message=Google account disconnected", status_code=302)


@app.get("/auth/outlook")
async def outlook_auth_start(request: Request, return_to: str = None, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    settings = get_oauth_settings(db, "outlook")
    if not settings or not settings.is_configured:
        return RedirectResponse(url="/settings?error=Outlook OAuth not configured", status_code=302)
    
    base_url = get_base_url(request, db)
    redirect_uri = f"{base_url}/auth/outlook/callback"
    state = f"{user.id}|{return_to or 'settings'}"
    auth_url = build_microsoft_auth_url(settings.client_id, redirect_uri, state=state, tenant_id=settings.tenant_id)
    
    return RedirectResponse(url=auth_url)


@app.get("/auth/outlook/callback")
async def outlook_auth_callback(request: Request, code: str = None, error: str = None, state: str = None, error_description: str = None, db: Session = Depends(get_db)):
    parts = (state or "").split("|")
    user_id = int(parts[0]) if parts and parts[0].isdigit() else None
    return_path = parts[1] if len(parts) > 1 else "settings"
    return_url = "/sources/add" if return_path == "sources_add" else "/settings"
    
    if error:
        error_msg = error_description if error_description else error
        return RedirectResponse(url=f"{return_url}?error=Outlook auth failed: {error_msg}", status_code=302)
    
    if not code:
        return RedirectResponse(url=f"{return_url}?error=No authorization code received", status_code=302)
    
    settings = get_oauth_settings(db, "outlook")
    if not settings:
        return RedirectResponse(url=f"{return_url}?error=Outlook OAuth not configured", status_code=302)
    
    base_url = get_base_url(request, db)
    redirect_uri = f"{base_url}/auth/outlook/callback"
    client_secret = get_decrypted_client_secret(settings)
    
    try:
        tokens = await exchange_microsoft_code(code, settings.client_id, client_secret, redirect_uri, tenant_id=settings.tenant_id)
        save_oauth_token(
            db, "outlook",
            tokens["access_token"],
            tokens.get("refresh_token"),
            tokens.get("expires_in"),
            user_id=user_id
        )
        return RedirectResponse(url=f"{return_url}?message=Outlook account connected successfully", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"{return_url}?error=Failed to connect Outlook: {str(e)}", status_code=302)


@app.get("/auth/outlook/disconnect")
async def outlook_auth_disconnect(request: Request, return_to: str = None, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    delete_oauth_token(db, "outlook", user_id=user.id)
    return_url = "/sources/add" if return_to == "sources_add" else "/settings"
    return RedirectResponse(url=f"{return_url}?message=Outlook account disconnected", status_code=302)


@app.get("/api/calendars/google")
async def api_google_calendars(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    access_token = await get_valid_google_token(db, user_id=user.id)
    if not access_token:
        raise HTTPException(status_code=400, detail="Google not connected")
    
    try:
        calendars = await list_google_calendars_custom(access_token)
        return {"calendars": calendars}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendars/outlook")
async def api_outlook_calendars(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    access_token = await get_valid_microsoft_token(db, user_id=user.id)
    if not access_token:
        raise HTTPException(status_code=400, detail="Outlook not connected")
    
    try:
        calendars = await list_microsoft_calendars_custom(access_token)
        return {"calendars": calendars}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    base_url = get_base_url(request, db)
    public_domain = get_public_domain(db)
    feed_url_base = public_domain if public_domain else base_url
    ics_url = f"{feed_url_base}/feed/{user.feed_token}/calendar.ics"
    webcal_url = ics_url.replace("https://", "webcal://").replace("http://", "webcal://")
    
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "is_admin": is_admin(user),
        "ics_url": ics_url,
        "webcal_url": webcal_url,
        "message": message,
        "error": error
    })


@app.post("/profile/change-password")
async def change_password(
    request: Request,
    db: Session = Depends(get_db),
    current_password: str = Form(...),
    new_password: str = Form(...)
):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    from src.auth import verify_password
    if not verify_password(current_password, user.hashed_password):
        return RedirectResponse(url="/profile?error=Current password is incorrect", status_code=302)
    
    user.hashed_password = hash_password(new_password)
    db.commit()
    
    return RedirectResponse(url="/profile?message=Password changed successfully", status_code=302)


@app.post("/profile/regenerate-token")
async def regenerate_feed_token(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    user.feed_token = secrets.token_hex(32)
    db.commit()
    
    return RedirectResponse(url="/profile?message=Feed token regenerated successfully", status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/favicon.ico")
async def favicon():
    return Response(content="", media_type="image/x-icon")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
