"""
NEXUS IoT - AI Chat via OpenAI-compatible endpoint (Hermes/OpenRouter)
"""
import os
import json
import logging
import requests
from datetime import timedelta
from flask import Blueprint, request, jsonify

from app.auth import login_required
from app.database import get_db_context, get_wib_time
from app.extensions import limiter

logger = logging.getLogger('nexus')
chat_bp = Blueprint('chat', __name__, url_prefix='/api/v1/chat')

# ============ CONFIG (dari .env) ============
LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'http://localhost:8000/v1')
LLM_API_KEY  = os.getenv('LLM_API_KEY', 'sk-no-key')
LLM_MODEL    = os.getenv('LLM_MODEL', 'nvidia/nemotron-3-super-120b-a12b:free')
LLM_TIMEOUT  = int(os.getenv('LLM_TIMEOUT', 120))

CHAT_URL = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"


# ============================================================
# TOOLS
# ============================================================
def tool_get_present_today():
    now = get_wib_time()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT COALESCE(c.nama, 'Tidak dikenal') AS nama, a.uid,
                   MIN(a.timestamp) AS check_in
            FROM attendance a
            LEFT JOIN cardholders c ON a.uid = c.uid
            WHERE a.timestamp >= ? AND a.timestamp < ?
            GROUP BY a.uid
            ORDER BY check_in ASC
        ''', (today, tomorrow)).fetchall()
    return {
        'tanggal': today.strftime('%Y-%m-%d'),
        'jumlah': len(rows),
        'karyawan': [{
            'nama': r['nama'], 'uid': r['uid'],
            'jam_masuk': str(r['check_in']).split('.')[0].split(' ')[-1]
        } for r in rows]
    }


def tool_get_absent_today():
    now = get_wib_time()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT c.nama, c.uid FROM cardholders c
            WHERE NOT EXISTS (
                SELECT 1 FROM attendance a
                WHERE a.uid = c.uid
                  AND a.timestamp >= ? AND a.timestamp < ?
            )
            ORDER BY c.nama ASC
        ''', (today, tomorrow)).fetchall()
        total = conn.execute('SELECT COUNT(*) FROM cardholders').fetchone()[0]
    return {
        'tanggal': today.strftime('%Y-%m-%d'),
        'total_terdaftar': total,
        'jumlah_tidak_masuk': len(rows),
        'karyawan': [{'nama': r['nama'], 'uid': r['uid']} for r in rows]
    }


def tool_get_attendance_range(start_date: str, end_date: str):
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT DATE(a.timestamp) AS day,
                   COALESCE(c.nama, 'Tidak dikenal') AS nama,
                   a.uid, MIN(a.timestamp) AS check_in,
                   MAX(a.timestamp) AS check_out, COUNT(*) AS taps
            FROM attendance a
            LEFT JOIN cardholders c ON a.uid = c.uid
            WHERE DATE(a.timestamp) BETWEEN ? AND ?
            GROUP BY day, a.uid
            ORDER BY day DESC, check_in ASC LIMIT 500
        ''', (start_date, end_date)).fetchall()
    return {
        'periode': f"{start_date} s/d {end_date}",
        'jumlah': len(rows),
        'data': [{
            'tanggal': r['day'], 'nama': r['nama'], 'uid': r['uid'],
            'check_in': str(r['check_in']).split('.')[0],
            'check_out': str(r['check_out']).split('.')[0],
            'total_taps': r['taps'],
        } for r in rows]
    }


def tool_get_devices_status():
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT device_id, device_name, device_type, location, status, last_seen
            FROM devices ORDER BY device_name
        ''').fetchall()
    return {
        'total': len(rows),
        'devices': [{
            'device_id': r['device_id'], 'nama': r['device_name'],
            'tipe': r['device_type'], 'lokasi': r['location'],
            'status': r['status'],
            'terakhir_aktif': str(r['last_seen']).split('.')[0] if r['last_seen'] else None,
        } for r in rows]
    }


def tool_get_active_alerts():
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT a.severity, a.alert_type, a.message, a.value,
                   a.created_at, d.device_name
            FROM alerts a LEFT JOIN devices d ON a.device_id = d.device_id
            WHERE a.is_active = 1 AND a.alert_type != 'uid'
            ORDER BY CASE a.severity
                WHEN 'danger' THEN 1 WHEN 'warning' THEN 2
                WHEN 'info' THEN 3 ELSE 4 END, a.created_at DESC
            LIMIT 50
        ''').fetchall()
    return {
        'total': len(rows),
        'alerts': [{
            'severity': r['severity'], 'tipe': r['alert_type'],
            'pesan': r['message'], 'nilai': r['value'],
            'device': r['device_name'],
            'waktu': str(r['created_at']).split('.')[0],
        } for r in rows]
    }


def tool_get_device_history(device_id: str, hours: int = 24):
    hours = max(1, min(int(hours), 168))
    since = get_wib_time() - timedelta(hours=hours)
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT data, timestamp FROM sensor_data
            WHERE device_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT 100
        ''', (device_id, since)).fetchall()
    return {
        'device_id': device_id, 'periode_jam': hours, 'jumlah_data': len(rows),
        'data': [{
            'timestamp': str(r['timestamp']).split('.')[0],
            'sensor': json.loads(r['data']) if r['data'] else {}
        } for r in rows]
    }


def tool_get_cardholders():
    with get_db_context() as conn:
        rows = conn.execute(
            'SELECT uid, nama, created_at FROM cardholders ORDER BY nama'
        ).fetchall()
    return {
        'total': len(rows),
        'karyawan': [{
            'nama': r['nama'], 'uid': r['uid'],
            'terdaftar_sejak': str(r['created_at']).split('.')[0]
        } for r in rows]
    }


# ============================================================
# TOOL SCHEMA
# ============================================================
TOOLS = [
    {"type": "function", "function": {
        "name": "get_present_today",
        "description": "Daftar karyawan yang SUDAH absen/masuk hari ini.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_absent_today",
        "description": "Daftar karyawan terdaftar yang BELUM absen hari ini (tidak masuk/bolos).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_attendance_range",
        "description": "Laporan absensi rentang tanggal tertentu.",
        "parameters": {"type": "object", "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["start_date", "end_date"]}}},
    {"type": "function", "function": {
        "name": "get_devices_status",
        "description": "Status semua perangkat IoT (online/offline/alert).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_active_alerts",
        "description": "Daftar alert yang sedang aktif.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_device_history",
        "description": "Riwayat sensor sebuah device N jam terakhir.",
        "parameters": {"type": "object", "properties": {
            "device_id": {"type": "string"},
            "hours": {"type": "integer", "description": "default 24"}},
            "required": ["device_id"]}}},
    {"type": "function", "function": {
        "name": "get_cardholders",
        "description": "Semua karyawan yang terdaftar di sistem.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

TOOL_MAP = {
    'get_present_today': tool_get_present_today,
    'get_absent_today': tool_get_absent_today,
    'get_attendance_range': tool_get_attendance_range,
    'get_devices_status': tool_get_devices_status,
    'get_active_alerts': tool_get_active_alerts,
    'get_device_history': tool_get_device_history,
    'get_cardholders': tool_get_cardholders,
}


SYSTEM_PROMPT = """Kamu adalah NEXUS AI, asisten IoT monitoring.
Jawab SINGKAT, RAMAH, dalam Bahasa Indonesia.

ATURAN:
1. JANGAN mengarang data. Panggil tool dulu.
2. "siapa tidak masuk" → get_absent_today
3. "siapa hadir" → get_present_today
4. "status device" → get_devices_status
5. "alert" → get_active_alerts
6. Data kosong → bilang "tidak ada".
7. Format daftar pakai bullet atau nomor.
8. Jangan sebut nama tool ke user.

Hari ini: {today}"""


# ============================================================
# ENDPOINT
# ============================================================
@chat_bp.route('', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def chat():
    payload = request.get_json(silent=True) or {}
    messages = payload.get('messages', [])
    if not isinstance(messages, list) or not messages:
        return jsonify({'success': False, 'error': 'messages wajib diisi'}), 400
    messages = messages[-10:]

    today_str = get_wib_time().strftime('%A, %d %B %Y')
    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=today_str)}
    ] + messages

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LLM_API_KEY}',
    }

    try:
        # Round 1
        r1 = requests.post(CHAT_URL, headers=headers, json={
            "model": LLM_MODEL,
            "messages": full_messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.2,
        }, timeout=LLM_TIMEOUT)
        r1.raise_for_status()
        resp1 = r1.json()

        choice = (resp1.get('choices') or [{}])[0]
        assistant_msg = choice.get('message', {}) or {}
        tool_calls = assistant_msg.get('tool_calls') or []
        tools_used = []

        if tool_calls:
            full_messages.append({
                "role": "assistant",
                "content": assistant_msg.get('content') or "",
                "tool_calls": tool_calls,
            })

            for call in tool_calls:
                fn_name = (call.get('function') or {}).get('name', '')
                raw_args = (call.get('function') or {}).get('arguments', '{}')
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception:
                    args = {}

                fn = TOOL_MAP.get(fn_name)
                if fn:
                    try:
                        result = fn(**args)
                    except Exception as e:
                        logger.error(f"Tool {fn_name} error: {e}", exc_info=True)
                        result = {'error': str(e)}
                else:
                    result = {'error': f'Tool {fn_name} tidak dikenal'}

                tools_used.append({'tool': fn_name, 'args': args})

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": call.get('id', ''),
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Round 2
            r2 = requests.post(CHAT_URL, headers=headers, json={
                "model": LLM_MODEL,
                "messages": full_messages,
                "temperature": 0.3,
            }, timeout=LLM_TIMEOUT)
            r2.raise_for_status()
            resp2 = r2.json()
            final_text = (resp2.get('choices') or [{}])[0].get('message', {}).get('content', '')
        else:
            final_text = assistant_msg.get('content', '')

        return jsonify({
            'success': True,
            'reply': final_text or '(kosong)',
            'tools_used': tools_used,
        }), 200

    except requests.exceptions.ConnectionError:
        return jsonify({'success': False,
                        'error': f'Tidak bisa konek ke LLM endpoint ({LLM_BASE_URL}).'}), 503
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'LLM timeout.'}), 504
    except requests.exceptions.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else str(e)
        logger.error(f"LLM HTTP error: {e} | body={body}")
        return jsonify({'success': False, 'error': f'LLM error: {e.response.status_code if e.response else "?"}'}), 502
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


@chat_bp.route('/health', methods=['GET'])
@login_required
def chat_health():
    try:
        r = requests.get(
            f"{LLM_BASE_URL.rstrip('/')}/models",
            headers={'Authorization': f'Bearer {LLM_API_KEY}'},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        models = [m.get('id') for m in data.get('data', [])]
        return jsonify({
            'success': True,
            'upstream_ok': True,
            'model': LLM_MODEL,
            'available_models': models[:20],
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'upstream_ok': False,
            'error': f'Upstream offline: {type(e).__name__}',
        }), 503