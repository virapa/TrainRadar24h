import json
import logging

from pywebpush import WebPushException, webpush

from ..config import Settings

log = logging.getLogger(__name__)


def send_push(settings: Settings, sub: dict, payload: dict) -> str:
    """Devuelve 'ok', 'gone' (la suscripción ya no existe: borrarla) o 'error'."""
    if not settings.vapid_private_key or not settings.vapid_subject:
        log.warning("Push sin configurar (faltan VAPID_PRIVATE_KEY o VAPID_SUBJECT)")
        return "error"
    try:
        webpush(subscription_info=sub, data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject})
        return "ok"
    except WebPushException as exc:
        code = getattr(exc.response, "status_code", None)
        log.warning("Push falló (%s)", code)
        return "gone" if code in (404, 410) else "error"
    except Exception as exc:
        log.warning("Push falló (%s: %s)", type(exc).__name__, exc)
        return "error"
