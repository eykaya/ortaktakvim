import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from .database import SessionLocal
from .models import User, UserRole, UserSession


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_secret() -> str:
    return os.environ.get("SESSION_SECRET", "default-secret-change-me")


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(password, hashed)
    except Exception:
        return False


def create_default_admin(db: Session):
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if not admin:
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        admin = User(
            username=admin_username,
            hashed_password=hash_password(admin_password),
            role=UserRole.ADMIN,
            is_active=True,
            feed_token=secrets.token_hex(32)
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return admin


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None


def get_current_user_from_session(request: Request, db: Session) -> Optional[User]:
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        return None
    
    session = db.query(UserSession).filter(
        UserSession.session_token == session_token,
        UserSession.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        return None
    
    user = db.query(User).filter(User.id == session.user_id, User.is_active == True).first()
    return user


def create_session(request: Request, user: User, db: Session = None) -> str:
    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    
    try:
        session_token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:512]
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(session)
        db.commit()
        
        return session_token
    finally:
        if close_db:
            db.close()


def destroy_session(request: Request, session_token: str, db: Session = None):
    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    
    try:
        db.query(UserSession).filter(UserSession.session_token == session_token).delete()
        db.commit()
    finally:
        if close_db:
            db.close()


def cleanup_expired_sessions(db: Session):
    db.query(UserSession).filter(UserSession.expires_at < datetime.utcnow()).delete()
    db.commit()


def require_auth(request: Request, db: Session = None) -> Optional[User]:
    if db is None:
        db = SessionLocal()
        try:
            return get_current_user_from_session(request, db)
        finally:
            db.close()
    return get_current_user_from_session(request, db)


def require_admin(request: Request, db: Session = None) -> Optional[User]:
    user = require_auth(request, db)
    if user and user.role == UserRole.ADMIN:
        return user
    return None


def get_current_user(request: Request) -> User:
    db = SessionLocal()
    try:
        user = get_current_user_from_session(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user
    finally:
        db.close()


def is_admin(user: User) -> bool:
    return user and user.role == UserRole.ADMIN
