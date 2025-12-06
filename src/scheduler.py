import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .database import SessionLocal
from .sync_service import sync_all_sources
from .logging_service import add_log


scheduler = AsyncIOScheduler()
_current_interval = 10


async def scheduled_sync():
    db = SessionLocal()
    try:
        add_log(db, "INFO", "Scheduled calendar sync started", source="scheduler")
        results = await sync_all_sources(db)
        
        success_count = sum(1 for r in results.values() if r["success"])
        fail_count = len(results) - success_count
        
        for source_name, result in results.items():
            status = "Success" if result["success"] else "Failed"
            level = "INFO" if result["success"] else "WARNING"
            add_log(db, level, f"Sync {source_name}: {status} - {result['message']}", source="scheduler")
        
        add_log(db, "INFO", f"Scheduled sync completed: {success_count} success, {fail_count} failed", source="scheduler")
    except Exception as e:
        add_log(db, "ERROR", f"Error during scheduled sync: {str(e)}", source="scheduler")
    finally:
        db.close()


def get_sync_interval() -> int:
    db = SessionLocal()
    try:
        from .settings_service import get_setting
        interval_str = get_setting(db, 'sync_interval_minutes', '10')
        return int(interval_str)
    except Exception:
        return 10
    finally:
        db.close()


def start_scheduler():
    global _current_interval
    _current_interval = get_sync_interval()
    
    scheduler.add_job(
        scheduled_sync,
        trigger=IntervalTrigger(minutes=_current_interval),
        id="calendar_sync",
        name="Sync all calendar sources",
        replace_existing=True
    )
    scheduler.start()
    print(f"Scheduler started - syncing every {_current_interval} minutes")


def update_sync_interval(new_interval_minutes: int):
    global _current_interval
    
    if new_interval_minutes < 1:
        new_interval_minutes = 1
    if new_interval_minutes > 1440:
        new_interval_minutes = 1440
    
    _current_interval = new_interval_minutes
    
    scheduler.reschedule_job(
        "calendar_sync",
        trigger=IntervalTrigger(minutes=new_interval_minutes)
    )
    
    print(f"Scheduler updated - now syncing every {new_interval_minutes} minutes")
    
    db = SessionLocal()
    try:
        add_log(db, "INFO", f"Sync interval changed to {new_interval_minutes} minutes", source="scheduler")
    finally:
        db.close()


def get_current_interval() -> int:
    return _current_interval


def get_next_run_time() -> datetime:
    job = scheduler.get_job("calendar_sync")
    if job and job.next_run_time:
        return job.next_run_time
    return None


def trigger_manual_sync():
    asyncio.create_task(scheduled_sync())


def stop_scheduler():
    scheduler.shutdown()
