"""KIS adapter scaffolding kept isolated from broker-neutral boundaries."""

from .adapter import KISMarketDataAdapter
from .auth import KISAuthMaterial, KISAuthProvider
from .config import KISSettings, Settings, load_kis_settings, load_settings, settings
from .mappers import (
    EVENT_TYPE_BY_CHANNEL,
    KISSubscriptionBinding,
    KIS_TR_ID_BY_CHANNEL_AND_MARKET,
    resolve_event_type,
    resolve_market,
    resolve_subscription_binding,
)
from .realtime import KISRealtimeClient, KISRealtimeSubscriptionMessage

__all__ = [
    "EVENT_TYPE_BY_CHANNEL",
    "KISAuthMaterial",
    "KISAuthProvider",
    "KISMarketDataAdapter",
    "KISSettings",
    "KISRealtimeClient",
    "KISRealtimeSubscriptionMessage",
    "KISSubscriptionBinding",
    "KIS_TR_ID_BY_CHANNEL_AND_MARKET",
    "Settings",
    "load_kis_settings",
    "load_settings",
    "resolve_event_type",
    "resolve_market",
    "resolve_subscription_binding",
    "settings",
]
