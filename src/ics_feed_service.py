import httpx
from datetime import datetime, timedelta, timezone
from typing import List
from icalendar import Calendar
from dateutil import parser as date_parser

# Try to import recurring-ical-events library
try:
    import recurring_ical_events
    RECURRING_SUPPORT = True
    print("✓ recurring-ical-events library loaded successfully")
except ImportError as e:
    RECURRING_SUPPORT = False
    print(f"✗ recurring-ical-events library NOT available: {e}")
    print("  Recurring events will NOT be expanded. Install with: pip install recurring-ical-events")


def normalize_ics_url(url: str) -> str:
    if url.startswith('webcal://'):
        return url.replace('webcal://', 'https://')
    elif url.startswith('webcals://'):
        return url.replace('webcals://', 'https://')
    return url


async def fetch_ics_feed(url: str) -> List[dict]:
    https_url = normalize_ics_url(url)
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(https_url, headers={
            "User-Agent": "CalendarAggregator/1.0",
            "Accept": "text/calendar, application/calendar+json, */*"
        })
        response.raise_for_status()
        ics_content = response.text
    
    return parse_ics_content(ics_content)


def parse_ics_content(ics_content: str) -> List[dict]:
    events = []
    
    try:
        cal = Calendar.from_ical(ics_content)
    except Exception as e:
        print(f"Error parsing ICS: {e}")
        return events
    
    now = datetime.utcnow()
    time_min = now - timedelta(days=30)
    time_max = now + timedelta(days=365)
    
    # Use recurring_ical_events to expand recurring events
    if RECURRING_SUPPORT:
        try:
            expanded_events = recurring_ical_events.of(cal).between(time_min, time_max)
            expanded_list = list(expanded_events)
            print(f"✓ ICS Feed: Expanded to {len(expanded_list)} event occurrences (including recurring)")
            expanded_events = expanded_list
        except Exception as e:
            print(f"✗ ICS Feed: Error expanding recurring events: {e}")
            expanded_events = cal.walk()
    else:
        print("✗ ICS Feed: Recurring events will NOT be expanded (library not available)")
        expanded_events = cal.walk()
    
    for component in expanded_events:
        if component.name == "VEVENT":
            try:
                uid = str(component.get('uid', ''))
                summary = str(component.get('summary', ''))
                description = str(component.get('description', '')) if component.get('description') else ''
                location = str(component.get('location', '')) if component.get('location') else ''
                
                dtstart = component.get('dtstart')
                dtend = component.get('dtend')
                
                if not dtstart:
                    continue
                
                start_dt = dtstart.dt
                is_all_day = False

                if isinstance(start_dt, datetime):
                    # Timezone'lu datetime ise UTC'ye çevir
                    if start_dt.tzinfo:
                        start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    # Timezone bilgisi yoksa UTC olarak kabul et
                    else:
                        pass  # Zaten timezone yok, UTC olarak kabul ediliyor
                else:
                    # Date ise all-day event
                    is_all_day = True
                    start_dt = datetime.combine(start_dt, datetime.min.time())

                if dtend:
                    end_dt = dtend.dt
                    if isinstance(end_dt, datetime):
                        # Timezone'lu datetime ise UTC'ye çevir
                        if end_dt.tzinfo:
                            end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
                        else:
                            pass  # Zaten timezone yok, UTC olarak kabul ediliyor
                    else:
                        # Date ise datetime'a çevir
                        end_dt = datetime.combine(end_dt, datetime.min.time())
                else:
                    end_dt = start_dt + timedelta(hours=1)
                
                # Create unique ID for each occurrence of recurring events
                # Use uid + start_datetime to ensure uniqueness
                unique_uid = f"{uid}_{start_dt.isoformat()}" if uid else f"ics_{start_dt.isoformat()}"
                
                events.append({
                    "uid": unique_uid,
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
    
    print(f"ICS Feed: Parsed {len(events)} total events after expansion")
    return events
