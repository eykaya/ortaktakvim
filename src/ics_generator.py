from datetime import datetime, timezone
from typing import List
from icalendar import Calendar as ICalendar, Event as IEvent
from sqlalchemy.orm import Session
import pytz

from .models import Event, CalendarSource


def generate_unified_ics(db: Session, apply_masking: bool = True, user_id: int = None) -> str:
    cal = ICalendar()
    cal.add("prodid", "-//Calendar Aggregator//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Unified Calendar")
    
    query = db.query(Event).join(CalendarSource).filter(
        CalendarSource.is_enabled == True
    )
    
    if user_id is not None:
        query = query.filter(CalendarSource.user_id == user_id)
    
    events = query.all()
    
    for event in events:
        source = event.source
        
        ievent = IEvent()
        ievent.add("uid", f"{event.original_uid}@calendar-aggregator")
        
        if event.is_all_day:
            # All-day events için sadece tarih kullan
            ievent.add("dtstart", event.start_datetime.date())
            ievent.add("dtend", event.end_datetime.date())
        else:
            # Veritabanında naive datetime olarak UTC saklıyoruz
            # ICS'e yazarken UTC timezone bilgisi ekle
            start_utc = event.start_datetime.replace(tzinfo=pytz.UTC)
            end_utc = event.end_datetime.replace(tzinfo=pytz.UTC)
            ievent.add("dtstart", start_utc)
            ievent.add("dtend", end_utc)
        
        if apply_masking and source.masking:
            ievent.add("summary", "Busy")
        else:
            ievent.add("summary", event.original_summary or "Untitled Event")
            if event.original_description:
                ievent.add("description", event.original_description)
            if event.original_location:
                ievent.add("location", event.original_location)
        
        # TRANSP:OPAQUE ensures events are shown as "busy" (not "free")
        ievent.add("transp", "OPAQUE")
        
        ievent.add("dtstamp", datetime.utcnow())
        
        cal.add_component(ievent)
    
    return cal.to_ical().decode("utf-8")


def get_unified_events(db: Session, apply_masking: bool = True, upcoming_only: bool = False, user_id: int = None) -> List[dict]:
    query = db.query(Event).join(CalendarSource).filter(
        CalendarSource.is_enabled == True
    )

    if user_id is not None:
        query = query.filter(CalendarSource.user_id == user_id)

    if upcoming_only:
        query = query.filter(Event.end_datetime >= datetime.utcnow())

    events = query.order_by(Event.start_datetime).all()

    result = []
    for event in events:
        source = event.source

        # Veritabanında naive datetime olarak UTC saklıyoruz
        # API'ye dönerken UTC timezone bilgisi ekle
        start_utc = event.start_datetime.replace(tzinfo=pytz.UTC)
        end_utc = event.end_datetime.replace(tzinfo=pytz.UTC)

        if apply_masking and source.masking:
            result.append({
                "id": event.id,
                "source_name": source.name,
                "summary": "Busy",
                "description": "",
                "location": "",
                "start": start_utc,
                "end": end_utc,
                "is_all_day": event.is_all_day,
                "is_masked": True
            })
        else:
            result.append({
                "id": event.id,
                "source_name": source.name,
                "summary": event.original_summary or "Untitled Event",
                "description": event.original_description or "",
                "location": event.original_location or "",
                "start": start_utc,
                "end": end_utc,
                "is_all_day": event.is_all_day,
                "is_masked": False
            })

    return result
