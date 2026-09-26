"""
NEXUS IoT - Telegram Notification Dispatcher
"""
import time
import logging
import threading
import requests
from datetime import datetime, timedelta, timezone
from queue import Queue, Empty

from app.config import get_config

logger = logging.getLogger('nexus')
WIB = timezone(timedelta(hours=7))

_notify_queue = Queue(maxsize=1000)
_worker_started = False
_worker_lock = threading.Lock()
_recent_notifications = {}
_recent_lock = threading.Lock()
DEDUP_WINDOW_SECONDS = 60

SEVERITY_EMOJI = {'info': 'ℹ️', 'warning': '⚠️', 'danger': '🔥', 'healthy': '✅'}
SEVERITY_LABEL = {'info': 'INFO', 'warning': 'PERINGATAN', 'danger': 'BAHAYA', 'healthy': 'NORMAL'}
ACTION_LABEL = {'created': 'ALERT BARU', 'severity_changed': 'PERUBAHAN SEVERITY', 'cleared': 'ALERT SELESAI'}


def _format_message(event):
    severity = event.get('severity', 'info')
    action = event.get('event', 'created')
    emoji = SEVERITY_EMOJI.get(severity, '🔔')
    sev_label = SEVERITY_LABEL.get(severity, severity.upper())
    action_label = ACTION_LABEL.get(action, action.upper())

    if action == 'cleared':
        title = f"{emoji} *{action_label}*"
    elif action == 'severity_changed':
        old_sev = SEVERITY_LABEL.get(event.get('old_severity', ''), event.get('old_severity', '?'))
        title = f"{emoji} *{action_label}* — {sev_label} (dari {old_sev})"
    else:
        title = f"{emoji} *{action_label}* — {sev_label}"

    lines = [
        title, "",
        f"📟 *Device:* `{event.get('device_id', '-')}`",
        f"🏷️ *Nama:* {event.get('device_name', '-')}",
    ]
    if event.get('location'):
        lines.append(f"📍 *Lokasi:* {event['location']}")
    lines.append(f"🔧 *Sensor:* `{event.get('alert_type', '-')}`")
    lines.append(f"💬 *Pesan:* {event.get('message', '-')}")
    if event.get('value') is not None:
        lines.append(f"📊 *Nilai:* `{event['value']}`")
    lines.append(f"🕐 *Waktu:* {event.get('timestamp', '-')}")
    return "\n".join(lines)


def _send_telegram(event):
    config = get_config()
    if not config.TELEGRAM_ENABLED:
        return False, 'telegram_disabled'

    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False, 'telegram_not_configured'

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': _format_message(event),
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True,
    }

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('ok'):
                    return True, None
                return False, f"telegram_api_error: {data.get('description')}"
            if resp.status_code == 429:
                retry_after = resp.json().get('parameters', {}).get('retry_after', 5)
                time.sleep(retry_after)
                continue
            if 500 <= resp.status_code < 600:
                time.sleep(2 ** attempt)
                continue
            return False, f"telegram_http_{resp.status_code}"
        except requests.exceptions.Timeout:
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)

    return False, 'telegram_max_retries_exceeded'


def _event_hash(event):
    import hashlib
    key = f"{event.get('device_id')}:{event.get('alert_type')}:{event.get('severity')}:{event.get('message')}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()


def _is_duplicate(event):
    h = _event_hash(event)
    now = time.time()
    with _recent_lock:
        expired = [k for k, t in _recent_notifications.items() if now - t > DEDUP_WINDOW_SECONDS]
        for k in expired:
            del _recent_notifications[k]
        if h in _recent_notifications:
            return True
        _recent_notifications[h] = now
        return False


def _should_notify(event):
    config = get_config()
    levels = {'info': 0, 'warning': 1, 'danger': 2}
    if event.get('event') == 'cleared':
        return config.NOTIFY_ON_CLEARED
    severity = event.get('severity', 'info')
    return levels.get(severity, 0) >= levels.get(config.NOTIFY_MIN_SEVERITY, 1)


def _dispatch_worker():
    logger.info("Notification worker started")
    while True:
        try:
            event = _notify_queue.get(timeout=5)
        except Empty:
            continue
        if event is None:
            break
        try:
            _dispatch_one(event)
        except Exception as e:
            logger.error(f"Notification dispatch error: {e}", exc_info=True)
        finally:
            _notify_queue.task_done()


def _dispatch_one(event):
    config = get_config()
    if not config.NOTIFY_ENABLED or not config.TELEGRAM_ENABLED:
        return
    if not _should_notify(event):
        return
    if _is_duplicate(event):
        return

    ok, err = _send_telegram(event)
    if ok:
        logger.info(f"📨 Telegram sent: {event.get('device_id')}/{event.get('alert_type')}")
    else:
        logger.warning(f"Telegram failed: {err}")


def _start_worker_if_needed():
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_dispatch_worker, name='notify-worker', daemon=True)
        t.start()
        _worker_started = True


def notify_alert_event(event):
    config = get_config()
    if not config.NOTIFY_ENABLED or not config.TELEGRAM_ENABLED:
        return
    _start_worker_if_needed()
    try:
        _notify_queue.put_nowait(event)
    except Exception as e:
        logger.warning(f"Notification queue full: {e}")


def send_test_notification():
    event = {
        'event': 'created',
        'device_id': 'TEST-DEVICE',
        'device_name': 'Test Notification',
        'location': 'Test Location',
        'alert_type': 'temperature',
        'severity': 'info',
        'old_severity': None,
        'message': 'Ini pesan test dari NEXUS IoT.',
        'value': 25.5,
        'timestamp': datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB'),
    }
    config = get_config()
    results = {}
    if config.TELEGRAM_ENABLED:
        ok, err = _send_telegram(event)
        results['telegram'] = {'success': ok, 'error': err}
    if not results:
        results['_info'] = {
            'success': False,
            'error': 'Telegram not enabled. Set TELEGRAM_ENABLED=True di .env'
        }
    return results


def get_notification_status():
    config = get_config()
    return {
        'notify_enabled': config.NOTIFY_ENABLED,
        'min_severity': config.NOTIFY_MIN_SEVERITY,
        'notify_on_cleared': config.NOTIFY_ON_CLEARED,
        'telegram': {
            'enabled': config.TELEGRAM_ENABLED,
            'has_token': bool(config.TELEGRAM_BOT_TOKEN),
            'has_chat_id': bool(config.TELEGRAM_CHAT_ID),
        },
    }