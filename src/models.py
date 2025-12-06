from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .database import Base


class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"


class SourceType(enum.Enum):
    GOOGLE_CALENDAR = "google_calendar"
    OUTLOOK_OAUTH = "outlook_oauth"
    CALDAV = "caldav"
    OUTLOOK = "outlook"
    ICLOUD = "icloud"
    ICS_FEED = "ics_feed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False, unique=True)
    email = Column(String(255), nullable=True)
    hashed_password = Column(Text, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    feed_token = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    calendar_sources = relationship("CalendarSource", back_populates="user", cascade="all, delete-orphan")
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")


class CalendarSource(Base):
    __tablename__ = "calendar_sources"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    source_type = Column(SQLEnum(SourceType), nullable=False)
    caldav_url = Column(String(512), nullable=True)
    username = Column(String(255), nullable=True)
    encrypted_password = Column(Text, nullable=True)
    masking = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), default="pending")
    last_sync_error = Column(Text, nullable=True)
    google_calendar_id = Column(String(255), nullable=True)
    outlook_calendar_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="calendar_sources")
    events = relationship("Event", back_populates="source", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("calendar_sources.id"), nullable=False)
    original_uid = Column(String(512), nullable=False)
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=False)
    original_summary = Column(String(512), nullable=True)
    original_description = Column(Text, nullable=True)
    original_location = Column(String(512), nullable=True)
    is_all_day = Column(Boolean, default=False)
    last_synced_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("CalendarSource", back_populates="events")


class GlobalSettings(Base):
    __tablename__ = "global_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), nullable=False, unique=True)
    setting_value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthSettings(Base):
    __tablename__ = "oauth_settings"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, unique=True)
    client_id = Column(String(255), nullable=True)
    encrypted_client_secret = Column(Text, nullable=True)
    tenant_id = Column(String(255), nullable=True)
    is_configured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    provider = Column(String(50), nullable=False)
    account_email = Column(String(255), nullable=True)
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="oauth_tokens")


class ApplicationLog(Base):
    __tablename__ = "application_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    source = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    feed_token = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
