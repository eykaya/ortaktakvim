import os
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


async def get_outlook_access_token() -> Optional[str]:
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
                f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=outlook",
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
        print(f"Error getting Outlook access token: {e}")
    return None


async def list_outlook_calendars(access_token: str) -> List[Dict[str, Any]]:
    calendars = []
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me/calendars",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                for calendar in data.get("value", []):
                    calendars.append({
                        "id": calendar["id"],
                        "summary": calendar.get("name", "Untitled"),
                        "primary": calendar.get("isDefaultCalendar", False)
                    })
    except Exception as e:
        print(f"Error listing Outlook calendars: {e}")
    
    return calendars


async def fetch_outlook_calendar_events(
    access_token: str,
    calendar_id: str = None,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    
    if time_min is None:
        time_min = datetime.utcnow() - timedelta(days=30)
    if time_max is None:
        time_max = datetime.utcnow() + timedelta(days=180)
    
    events = []
    
    endpoint = "https://graph.microsoft.com/v1.0/me/calendar/events"
    if calendar_id:
        endpoint = f"https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/events"
    
    params = {
        "$filter": f"start/dateTime ge '{time_min.isoformat()}Z' and end/dateTime le '{time_max.isoformat()}Z'",
        "$orderby": "start/dateTime",
        "$top": 500
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                endpoint,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Prefer": 'outlook.timezone="UTC"'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                for event in data.get("value", []):
                    start = event.get("start", {})
                    end = event.get("end", {})
                    
                    is_all_day = event.get("isAllDay", False)
                    
                    start_str = start.get("dateTime", "")
                    end_str = end.get("dateTime", "")
                    
                    if start_str:
                        start_dt = datetime.fromisoformat(start_str.replace("Z", ""))
                    else:
                        continue
                    
                    if end_str:
                        end_dt = datetime.fromisoformat(end_str.replace("Z", ""))
                    else:
                        end_dt = start_dt + timedelta(hours=1)
                    
                    events.append({
                        "uid": event["id"],
                        "summary": event.get("subject", ""),
                        "description": event.get("bodyPreview", ""),
                        "location": event.get("location", {}).get("displayName", ""),
                        "start": start_dt,
                        "end": end_dt,
                        "is_all_day": is_all_day
                    })
    except Exception as e:
        print(f"Error fetching Outlook events: {e}")
    
    return events
