from typing import Optional
from sqlalchemy.orm import Session

from .models import GlobalSettings


DEFAULT_SETTINGS = {
    'base_url': 'http://localhost:5000',
    'public_domain': '',
    'app_name': 'Calendar Aggregator',
    'sync_interval_minutes': '10',
    'log_retention_days': '30'
}


def get_setting(db: Session, key: str, default: str = None) -> Optional[str]:
    setting = db.query(GlobalSettings).filter(GlobalSettings.setting_key == key).first()
    if setting:
        return setting.setting_value
    return default if default is not None else DEFAULT_SETTINGS.get(key)


def set_setting(db: Session, key: str, value: str) -> GlobalSettings:
    setting = db.query(GlobalSettings).filter(GlobalSettings.setting_key == key).first()
    if setting:
        setting.setting_value = value
    else:
        setting = GlobalSettings(setting_key=key, setting_value=value)
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def get_all_settings(db: Session) -> dict:
    settings = db.query(GlobalSettings).all()
    result = DEFAULT_SETTINGS.copy()
    for setting in settings:
        result[setting.setting_key] = setting.setting_value
    return result


def get_base_url(db: Session) -> str:
    return get_setting(db, 'base_url', 'http://localhost:5000')


def get_public_domain(db: Session) -> str:
    return get_setting(db, 'public_domain', '')


def get_app_name(db: Session) -> str:
    return get_setting(db, 'app_name', 'Calendar Aggregator')


def initialize_default_settings(db: Session):
    for key, value in DEFAULT_SETTINGS.items():
        existing = db.query(GlobalSettings).filter(GlobalSettings.setting_key == key).first()
        if not existing:
            setting = GlobalSettings(setting_key=key, setting_value=value)
            db.add(setting)
    db.commit()
