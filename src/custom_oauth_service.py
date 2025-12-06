import httpx
from datetime import datetime, timedelta
from urllib.parse import urlencode
from sqlalchemy.orm import Session

from .models import OAuthSettings, OAuthToken
from .crypto import encrypt_password, decrypt_password


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MICROSOFT_CALENDAR_SCOPE = "Calendars.Read offline_access"


def get_oauth_settings(db: Session, provider: str) -> OAuthSettings:
    return db.query(OAuthSettings).filter(OAuthSettings.provider == provider).first()


def save_oauth_settings(db: Session, provider: str, client_id: str, client_secret: str, tenant_id: str = None) -> OAuthSettings:
    settings = get_oauth_settings(db, provider)
    
    if not settings:
        settings = OAuthSettings(provider=provider)
        db.add(settings)
    
    settings.client_id = client_id
    if client_secret:
        settings.encrypted_client_secret = encrypt_password(client_secret)
    if tenant_id is not None:
        settings.tenant_id = tenant_id
    settings.is_configured = bool(client_id and (client_secret or settings.encrypted_client_secret))
    settings.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(settings)
    return settings


def get_oauth_token(db: Session, provider: str, user_id: int = None) -> OAuthToken:
    query = db.query(OAuthToken).filter(OAuthToken.provider == provider)
    query = query.filter(OAuthToken.user_id == user_id)
    return query.first()


def save_oauth_token(db: Session, provider: str, access_token: str, refresh_token: str = None, expires_in: int = None, user_id: int = None):
    token = get_oauth_token(db, provider, user_id=user_id)
    
    if not token:
        token = OAuthToken(provider=provider, user_id=user_id)
        db.add(token)
    
    token.encrypted_access_token = encrypt_password(access_token)
    if refresh_token:
        token.encrypted_refresh_token = encrypt_password(refresh_token)
    if expires_in:
        token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    token.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(token)
    return token


def delete_oauth_token(db: Session, provider: str, user_id: int = None):
    token = get_oauth_token(db, provider, user_id=user_id)
    if token:
        db.delete(token)
        db.commit()


def get_decrypted_client_secret(settings: OAuthSettings) -> str:
    if settings and settings.encrypted_client_secret:
        return decrypt_password(settings.encrypted_client_secret)
    return None


def get_decrypted_access_token(token: OAuthToken) -> str:
    if token and token.encrypted_access_token:
        return decrypt_password(token.encrypted_access_token)
    return None


def get_decrypted_refresh_token(token: OAuthToken) -> str:
    if token and token.encrypted_refresh_token:
        return decrypt_password(token.encrypted_refresh_token)
    return None


def build_google_auth_url(client_id: str, redirect_uri: str, state: str = None) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_CALENDAR_SCOPE,
        "access_type": "offline",
        "prompt": "consent"
    }
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def build_microsoft_auth_url(client_id: str, redirect_uri: str, state: str = None, tenant_id: str = None) -> str:
    tenant = tenant_id if tenant_id else "consumers"
    auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": MICROSOFT_CALENDAR_SCOPE,
        "response_mode": "query"
    }
    if state:
        params["state"] = state
    print(f"Microsoft Auth URL: {auth_url} with tenant: {tenant}")
    return f"{auth_url}?{urlencode(params)}"


async def exchange_google_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        })
        response.raise_for_status()
        return response.json()


async def exchange_microsoft_code(code: str, client_id: str, client_secret: str, redirect_uri: str, tenant_id: str = None) -> dict:
    tenant = tenant_id if tenant_id else "consumers"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        })
        response.raise_for_status()
        return response.json()


async def refresh_google_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token"
        })
        response.raise_for_status()
        return response.json()


async def refresh_microsoft_token(refresh_token: str, client_id: str, client_secret: str, tenant_id: str = None) -> dict:
    tenant = tenant_id if tenant_id else "consumers"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token"
        })
        response.raise_for_status()
        return response.json()


async def get_valid_google_token(db: Session, user_id: int = None) -> str:
    settings = get_oauth_settings(db, "google")
    token = get_oauth_token(db, "google", user_id=user_id)
    
    if not settings or not token:
        return None
    
    if token.expires_at and token.expires_at < datetime.utcnow():
        refresh_token = get_decrypted_refresh_token(token)
        client_secret = get_decrypted_client_secret(settings)
        
        if refresh_token and client_secret:
            try:
                new_tokens = await refresh_google_token(refresh_token, settings.client_id, client_secret)
                save_oauth_token(
                    db, "google",
                    new_tokens["access_token"],
                    new_tokens.get("refresh_token", refresh_token),
                    new_tokens.get("expires_in"),
                    user_id=user_id
                )
                return new_tokens["access_token"]
            except Exception:
                return None
    
    return get_decrypted_access_token(token)


async def get_valid_microsoft_token(db: Session, user_id: int = None) -> str:
    settings = get_oauth_settings(db, "outlook")
    token = get_oauth_token(db, "outlook", user_id=user_id)
    
    if not settings or not token:
        return None
    
    if token.expires_at and token.expires_at < datetime.utcnow():
        refresh_token = get_decrypted_refresh_token(token)
        client_secret = get_decrypted_client_secret(settings)
        
        if refresh_token and client_secret:
            try:
                new_tokens = await refresh_microsoft_token(refresh_token, settings.client_id, client_secret, tenant_id=settings.tenant_id)
                save_oauth_token(
                    db, "outlook",
                    new_tokens["access_token"],
                    new_tokens.get("refresh_token", refresh_token),
                    new_tokens.get("expires_in"),
                    user_id=user_id
                )
                return new_tokens["access_token"]
            except Exception:
                return None
    
    return get_decrypted_access_token(token)


async def get_google_user_email(access_token: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("email", "")
    except Exception:
        return ""


async def get_microsoft_user_email(access_token: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("mail") or data.get("userPrincipalName", "")
    except Exception:
        return ""


async def list_google_calendars_custom(access_token: str) -> list:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        data = response.json()
        return [{"id": cal["id"], "summary": cal.get("summary", cal["id"])} for cal in data.get("items", [])]


async def list_microsoft_calendars_custom(access_token: str) -> list:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.microsoft.com/v1.0/me/calendars",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        data = response.json()
        return [{"id": cal["id"], "name": cal.get("name", "Calendar")} for cal in data.get("value", [])]


async def fetch_google_events_custom(access_token: str, calendar_id: str = "primary") -> list:
    async with httpx.AsyncClient() as client:
        time_min = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
        time_max = (datetime.utcnow() + timedelta(days=365)).isoformat() + "Z"
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": 500,
            "singleEvents": "true",
            "orderBy": "startTime"
        }
        print(f"Fetching Google events for calendar {calendar_id}, timeMin={time_min}, timeMax={time_max}")
        response = await client.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        print(f"Google API returned {len(items)} events")
        return items


async def fetch_microsoft_events_custom(access_token: str, calendar_id: str = None) -> list:
    async with httpx.AsyncClient() as client:
        if calendar_id:
            url = f"https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/events"
        else:
            url = "https://graph.microsoft.com/v1.0/me/calendar/events"
        
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$top": 250}
        )
        response.raise_for_status()
        return response.json().get("value", [])
