import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from .models import ApplicationLog


class DatabaseLogHandler(logging.Handler):
    def __init__(self, get_db_session):
        super().__init__()
        self.get_db_session = get_db_session

    def emit(self, record):
        try:
            db = self.get_db_session()
            try:
                log_entry = ApplicationLog(
                    level=record.levelname,
                    message=record.getMessage(),
                    source=record.name,
                    details=getattr(record, 'details', None)
                )
                db.add(log_entry)
                db.commit()
            finally:
                db.close()
        except Exception:
            pass


def add_log(db: Session, level: str, message: str, source: str = None, details: str = None):
    log_entry = ApplicationLog(
        level=level.upper(),
        message=message,
        source=source,
        details=details
    )
    db.add(log_entry)
    db.commit()
    return log_entry


def get_logs(db: Session, limit: int = 100, level: str = None, 
             source: str = None, hours: int = None) -> List[ApplicationLog]:
    query = db.query(ApplicationLog)
    
    if level:
        query = query.filter(ApplicationLog.level == level.upper())
    
    if source:
        query = query.filter(ApplicationLog.source.ilike(f"%{source}%"))
    
    if hours:
        since = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(ApplicationLog.created_at >= since)
    
    return query.order_by(ApplicationLog.created_at.desc()).limit(limit).all()


def clear_old_logs(db: Session, days: int = 30):
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = db.query(ApplicationLog).filter(ApplicationLog.created_at < cutoff).delete()
    db.commit()
    return deleted


def log_info(db: Session, message: str, source: str = None, details: str = None):
    return add_log(db, "INFO", message, source, details)


def log_warning(db: Session, message: str, source: str = None, details: str = None):
    return add_log(db, "WARNING", message, source, details)


def log_error(db: Session, message: str, source: str = None, details: str = None):
    return add_log(db, "ERROR", message, source, details)


def log_debug(db: Session, message: str, source: str = None, details: str = None):
    return add_log(db, "DEBUG", message, source, details)
