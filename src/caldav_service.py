from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import caldav
from icalendar import Calendar as ICalendar

from .crypto import decrypt_password


def fetch_caldav_events(
    caldav_url: str,
    username: str,
    encrypted_password: str,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    password = decrypt_password(encrypted_password)
    
    if time_min is None:
        time_min = datetime.utcnow() - timedelta(days=30)
    if time_max is None:
        time_max = datetime.utcnow() + timedelta(days=180)
    
    events = []
    
    client = caldav.DAVClient(url=caldav_url, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()
    
    for calendar in calendars:
        try:
            calendar_events = calendar.date_search(start=time_min, end=time_max, expand=True)
            
            for event in calendar_events:
                try:
                    ical = ICalendar.from_ical(event.data)
                    for component in ical.walk():
                        if component.name == "VEVENT":
                            uid = str(component.get("uid", ""))
                            summary = str(component.get("summary", ""))
                            description = str(component.get("description", ""))
                            location = str(component.get("location", ""))
                            
                            dtstart = component.get("dtstart")
                            dtend = component.get("dtend")
                            
                            if dtstart:
                                start_dt = dtstart.dt
                                is_all_day = not hasattr(start_dt, 'hour')
                                if is_all_day:
                                    # Date ise datetime'a çevir
                                    start_dt = datetime.combine(start_dt, datetime.min.time())
                                elif hasattr(start_dt, 'tzinfo') and start_dt.tzinfo:
                                    # Timezone'lu datetime ise UTC'ye çevir
                                    start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
                            else:
                                continue

                            if dtend:
                                end_dt = dtend.dt
                                if not hasattr(end_dt, 'hour'):
                                    # Date ise datetime'a çevir
                                    end_dt = datetime.combine(end_dt, datetime.min.time())
                                elif hasattr(end_dt, 'tzinfo') and end_dt.tzinfo:
                                    # Timezone'lu datetime ise UTC'ye çevir
                                    end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
                            else:
                                end_dt = start_dt + timedelta(hours=1)
                            
                            events.append({
                                "uid": uid,
                                "summary": summary,
                                "description": description,
                                "location": location,
                                "start": start_dt,
                                "end": end_dt,
                                "is_all_day": is_all_day
                            })
                except Exception as e:
                    print(f"Error parsing event: {e}")
                    continue
        except Exception as e:
            print(f"Error fetching from calendar: {e}")
            continue
    
    return events


def test_caldav_connection(caldav_url: str, username: str, password: str) -> tuple[bool, str]:
    try:
        client = caldav.DAVClient(url=caldav_url, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()
        return True, f"Connected successfully. Found {len(calendars)} calendar(s)."
    except Exception as e:
        return False, str(e)
