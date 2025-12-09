import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


async def get_google_access_token() -> Optional[str]:
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")

    if repl_identity:
        x_replit_token = f"repl {repl_identity}"
    elif web_repl_renewal:
        x_replit_token = f"depl {web_repl_renewal}"
    else:
        return None

    if not hostname:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=google-calendar",
                headers={
                    "Accept": "application/json",
                    "X_REPLIT_TOKEN": x_replit_token
                }
            )
            data = response.json()
            items = data.get("items", [])
            if items:
                settings = items[0].get("settings", {})
                access_token = settings.get("access_token") or settings.get("oauth", {}).get("credentials", {}).get("access_token")
                return access_token
    except Exception as e:
        print(f"Error getting Google access token: {e}")
    return None


def get_google_calendar_service(access_token: str):
    credentials = Credentials(token=access_token)
    service = build("calendar", "v3", credentials=credentials)
    return service


async def list_google_calendars(access_token: str) -> List[Dict[str, Any]]:
    service = get_google_calendar_service(access_token)
    calendars = []
    page_token = None
    
    while True:
        calendar_list = service.calendarList().list(pageToken=page_token).execute()
        for calendar in calendar_list.get("items", []):
            calendars.append({
                "id": calendar["id"],
                "summary": calendar.get("summary", "Untitled"),
                "primary": calendar.get("primary", False)
            })
        page_token = calendar_list.get("nextPageToken")
        if not page_token:
            break
    
    return calendars


async def fetch_google_calendar_events(
    access_token: str,
    calendar_id: str,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    service = get_google_calendar_service(access_token)
    
    if time_min is None:
        time_min = datetime.utcnow() - timedelta(days=30)
    if time_max is None:
        time_max = datetime.utcnow() + timedelta(days=180)
    
    events = []
    page_token = None
    
    while True:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat() + "Z",
            timeMax=time_max.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token
        ).execute()
        
        for event in events_result.get("items", []):
            start = event.get("start", {})
            end = event.get("end", {})
            
            is_all_day = "date" in start
            
            if is_all_day:
                start_dt = datetime.strptime(start["date"], "%Y-%m-%d")
                end_dt = datetime.strptime(end["date"], "%Y-%m-%d")
            else:
                start_str = start.get("dateTime", "")
                end_str = end.get("dateTime", "")
                # Google Calendar API her zaman timezone içerir, UTC'ye çevir
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                # UTC'ye çevir ve timezone bilgisini kaldır (veritabanında naive datetime kullanıyoruz)
                start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
                end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
            
            events.append({
                "uid": event["id"],
                "summary": event.get("summary", ""),
                "description": event.get("description", ""),
                "location": event.get("location", ""),
                "start": start_dt,
                "end": end_dt,
                "is_all_day": is_all_day
            })
        
        page_token = events_result.get("nextPageToken")
        if not page_token:
            break
    
    return events
