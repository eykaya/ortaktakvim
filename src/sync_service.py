from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from dateutil import parser as date_parser

from .models import CalendarSource, Event, SourceType
from .caldav_service import fetch_caldav_events
from .ics_feed_service import fetch_ics_feed
from .custom_oauth_service import (
    get_valid_google_token, get_valid_microsoft_token,
    fetch_google_events_custom, fetch_microsoft_events_custom
)


def parse_google_events(raw_events: List[dict]) -> List[dict]:
    events = []
    for item in raw_events:
        start = item.get("start", {})
        end = item.get("end", {})
        
        is_all_day = "date" in start
        
        if is_all_day:
            start_dt = date_parser.parse(start.get("date"))
            end_dt = date_parser.parse(end.get("date"))
        else:
            start_dt = date_parser.parse(start.get("dateTime", start.get("date", "")))
            end_dt = date_parser.parse(end.get("dateTime", end.get("date", "")))
        
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)
        
        events.append({
            "uid": item.get("id", ""),
            "summary": item.get("summary", ""),
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "start": start_dt,
            "end": end_dt,
            "is_all_day": is_all_day
        })
    
    return events


def parse_microsoft_events(raw_events: List[dict]) -> List[dict]:
    events = []
    for item in raw_events:
        start = item.get("start", {})
        end = item.get("end", {})
        
        is_all_day = item.get("isAllDay", False)
        
        start_dt = date_parser.parse(start.get("dateTime", ""))
        end_dt = date_parser.parse(end.get("dateTime", ""))
        
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)
        
        body = item.get("body", {})
        description = body.get("content", "") if body.get("contentType") == "text" else ""
        
        location = item.get("location", {})
        location_str = location.get("displayName", "") if isinstance(location, dict) else ""
        
        events.append({
            "uid": item.get("id", ""),
            "summary": item.get("subject", ""),
            "description": description,
            "location": location_str,
            "start": start_dt,
            "end": end_dt,
            "is_all_day": is_all_day
        })
    
    return events


async def sync_calendar_source(db: Session, source: CalendarSource, user_id: int = None) -> tuple[bool, str]:
    try:
        events_data = []
        source_user_id = user_id if user_id is not None else source.user_id
        
        if source.source_type == SourceType.GOOGLE_CALENDAR:
            access_token = await get_valid_google_token(db, user_id=source_user_id)
            if not access_token:
                return False, "Could not get Google access token. Please configure and connect Google in Settings."
            
            calendar_id = str(source.google_calendar_id) if source.google_calendar_id else "primary"
            raw_events = await fetch_google_events_custom(access_token, calendar_id)
            events_data = parse_google_events(raw_events)
        
        elif source.source_type == SourceType.OUTLOOK_OAUTH:
            access_token = await get_valid_microsoft_token(db, user_id=source_user_id)
            if not access_token:
                return False, "Could not get Outlook access token. Please configure and connect Outlook in Settings."
            
            calendar_id = str(source.outlook_calendar_id) if source.outlook_calendar_id else None
            raw_events = await fetch_microsoft_events_custom(access_token, calendar_id)
            events_data = parse_microsoft_events(raw_events)
        
        elif source.source_type == SourceType.ICS_FEED:
            ics_url = str(source.caldav_url) if source.caldav_url else ""
            if not ics_url:
                return False, "ICS feed URL is required."
            
            events_data = await fetch_ics_feed(ics_url)
        
        elif source.source_type in [SourceType.CALDAV, SourceType.OUTLOOK, SourceType.ICLOUD]:
            caldav_url = str(source.caldav_url) if source.caldav_url else ""
            username = str(source.username) if source.username else ""
            encrypted_pwd = str(source.encrypted_password) if source.encrypted_password else ""
            
            if not caldav_url or not username:
                return False, "CalDAV URL and username are required."
            
            events_data = fetch_caldav_events(
                caldav_url=caldav_url,
                username=username,
                encrypted_password=encrypted_pwd
            )
        
        else:
            return False, f"Unknown source type: {source.source_type}"
        
        db.query(Event).filter(Event.source_id == source.id).delete()
        
        for event_data in events_data:
            event = Event(
                source_id=source.id,
                original_uid=event_data["uid"],
                start_datetime=event_data["start"],
                end_datetime=event_data["end"],
                original_summary=event_data.get("summary", ""),
                original_description=event_data.get("description", ""),
                original_location=event_data.get("location", ""),
                is_all_day=event_data.get("is_all_day", False),
                last_synced_at=datetime.utcnow()
            )
            db.add(event)
        
        source.last_sync_at = datetime.utcnow()
        source.last_sync_status = "success"
        source.last_sync_error = None
        db.commit()
        
        return True, f"Successfully synced {len(events_data)} events."
    
    except Exception as e:
        source.last_sync_at = datetime.utcnow()
        source.last_sync_status = "error"
        source.last_sync_error = str(e)
        db.commit()
        return False, str(e)


async def sync_all_sources(db: Session, user_id: int = None) -> dict:
    query = db.query(CalendarSource).filter(CalendarSource.is_enabled == True)
    if user_id is not None:
        query = query.filter(CalendarSource.user_id == user_id)
    sources = query.all()
    results = {}
    
    for source in sources:
        success, message = await sync_calendar_source(db, source, user_id=source.user_id)
        results[str(source.name)] = {"success": success, "message": message}
    
    return results
