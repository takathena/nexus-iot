import os
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from dotenv import load_dotenv

from database import get_db, init_db

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Kredensial login dari environment variable
USERNAME = os.getenv('IOT_USERNAME', 'admin')
PASSWORD = os.getenv('IOT_PASSWORD', 'admin123')

init_db()

# Timezone WIB
WIB = timezone(timedelta(hours=7))
OFFLINE_TIMEOUT = 900  # 15 menit
CHECK_INTERVAL = 60  # Cek setiap 1 menit

def get_wib_time():
    return datetime.now(WIB)

def generate_api_key():
    return secrets.token_hex(32)

def validate_device_api_key(device_id, api_key):
    conn = get_db()
    device = conn.execute(
        'SELECT * FROM devices WHERE device_id = ? AND api_key = ?',
        (device_id, api_key)
    ).fetchone()
    conn.close()
    return device is not None

def update_device_status(device_id, status):
    conn = get_db()
    conn.execute(
        'UPDATE devices SET status = ?, last_seen = ? WHERE device_id = ?',
        (status, get_wib_time(), device_id)
    )
    conn.commit()
    conn.close()

def check_device_status():
    while True:
        try:
            conn = get_db()
            devices = conn.execute('SELECT device_id, last_seen FROM devices').fetchall()
            current_time = get_wib_time()
            for device in devices:
                if device['last_seen']:
                    try:
                        last_seen = datetime.fromisoformat(device['last_seen'])
                        if last_seen.tzinfo is None:
                            last_seen = last_seen.replace(tzinfo=WIB)
                        time_diff = (current_time - last_seen).total_seconds()
                        if time_diff > OFFLINE_TIMEOUT:
                            conn.execute('UPDATE devices SET status = ? WHERE device_id = ?', ('offline', device['device_id']))
                    except:
                        pass
                else:
                    conn.execute('UPDATE devices SET status = ? WHERE device_id = ?', ('offline', device['device_id']))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Checker error: {e}")
        time.sleep(CHECK_INTERVAL)

checker_thread = threading.Thread(target=check_device_status, daemon=True)
checker_thread.start()

# ============ AUTH DECORATOR ============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ============ LOGIN ROUTES ============
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Username atau password salah!')
    
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ============ API ENDPOINTS (TIDAK PERLU LOGIN UNTUK DATA) ============
@app.route('/api/v1/data', methods=['POST'])
def receive_data():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400
        required = ['device_id', 'api_key', 'sensor_type', 'data']
        for field in required:
            if field not in payload:
                return jsonify({'success': False, 'error': f'Missing: {field}'}), 400
        device_id = payload['device_id']
        api_key = payload['api_key']
        sensor_type = payload['sensor_type']
        data = payload['data']
        wifi_ssid = payload.get('wifi_ssid', '')
        uptime_seconds = payload.get('uptime_seconds', 0)
        if not validate_device_api_key(device_id, api_key):
            return jsonify({'success': False, 'error': 'Invalid device_id or api_key'}), 401
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Data must be object'}), 400
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO sensor_data (device_id, sensor_type, data, wifi_ssid, uptime_seconds, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
            (device_id, sensor_type, json.dumps(data), wifi_ssid, uptime_seconds, get_wib_time())
        )
        conn.commit()
        conn.close()
        update_device_status(device_id, 'online')
        return jsonify({'success': True, 'message': 'Data received', 'timestamp': get_wib_time().isoformat()}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/devices', methods=['GET'])
def get_devices():
    conn = get_db()
    devices = conn.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()
    conn.close()
    device_list = []
    for device in devices:
        device_list.append({
            'device_id': device['device_id'],
            'device_name': device['device_name'],
            'device_type': device['device_type'],
            'location': device['location'],
            'latitude': device['latitude'] if 'latitude' in device.keys() else 0,
            'longitude': device['longitude'] if 'longitude' in device.keys() else 0,
            'description': device['description'],
            'status': device['status'],
            'last_seen': device['last_seen'],
            'created_at': device['created_at']
        })
    return jsonify({'success': True, 'devices': device_list}), 200

@app.route('/api/v1/devices', methods=['POST'])
def add_device():
    try:
        payload = request.get_json()
        device_id = payload.get('device_id')
        device_name = payload.get('device_name')
        if not device_id or not device_name:
            return jsonify({'success': False, 'error': 'device_id and device_name required'}), 400
        api_key = generate_api_key()
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO devices (device_id, device_name, device_type, location, description, api_key) VALUES (?, ?, ?, ?, ?, ?)',
                (device_id, device_name, payload.get('device_type', 'ESP32'), payload.get('location', ''), payload.get('description', ''), api_key)
            )
            conn.commit()
        except:
            conn.close()
            return jsonify({'success': False, 'error': 'Device ID already exists'}), 400
        conn.close()
        return jsonify({'success': True, 'device': {'device_id': device_id, 'device_name': device_name, 'api_key': api_key}}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/devices/<device_id>', methods=['GET'])
def get_device_detail(device_id):
    conn = get_db()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    if not device:
        conn.close()
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    latest = conn.execute('SELECT * FROM sensor_data WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1', (device_id,)).fetchone()
    conn.close()
    device_info = {
        'device_id': device['device_id'],
        'device_name': device['device_name'],
        'device_type': device['device_type'],
        'location': device['location'],
        'status': device['status'],
        'last_seen': device['last_seen'],
        'latest_data': None
    }
    if latest:
        device_info['latest_data'] = {
            'sensor_type': latest['sensor_type'],
            'data': json.loads(latest['data']),
            'wifi_ssid': latest['wifi_ssid'] if 'wifi_ssid' in latest.keys() else '',
            'uptime_seconds': latest['uptime_seconds'] if 'uptime_seconds' in latest.keys() else 0,
            'timestamp': latest['timestamp']
        }
    return jsonify({'success': True, 'device': device_info}), 200

@app.route('/api/v1/devices/<device_id>/history', methods=['GET'])
def get_device_history(device_id):
    hours = request.args.get('hours', 3, type=int)
    if hours > 24:
        hours = 24
    since = get_wib_time() - timedelta(hours=hours)
    conn = get_db()
    data = conn.execute('SELECT * FROM sensor_data WHERE device_id = ? AND timestamp >= ? ORDER BY timestamp ASC LIMIT 500', (device_id, since)).fetchall()
    conn.close()
    history = []
    for item in data:
        history.append({
            'sensor_type': item['sensor_type'],
            'data': json.loads(item['data']),
            'wifi_ssid': item['wifi_ssid'] if 'wifi_ssid' in item.keys() else '',
            'uptime_seconds': item['uptime_seconds'] if 'uptime_seconds' in item.keys() else 0,
            'timestamp': item['timestamp']
        })
    return jsonify({'success': True, 'history': history, 'data_count': len(history)}), 200

@app.route('/api/v1/devices/<device_id>', methods=['PUT'])
def update_device(device_id):
    try:
        payload = request.get_json()
        conn = get_db()
        device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
        if not device:
            conn.close()
            return jsonify({'success': False, 'error': 'Device not found'}), 404
        conn.execute(
            'UPDATE devices SET device_name = ?, device_type = ?, location = ?, latitude = ?, longitude = ?, description = ? WHERE device_id = ?',
            (payload.get('device_name', device['device_name']), payload.get('device_type', device['device_type']), payload.get('location', device['location']), payload.get('latitude', device['latitude'] if 'latitude' in device.keys() else 0), payload.get('longitude', device['longitude'] if 'longitude' in device.keys() else 0), payload.get('description', device['description']), device_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/devices/<device_id>', methods=['DELETE'])
def delete_device(device_id):
    conn = get_db()
    conn.execute('DELETE FROM sensor_data WHERE device_id = ?', (device_id,))
    conn.execute('DELETE FROM alerts WHERE device_id = ?', (device_id,))
    conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/v1/dashboard', methods=['GET'])
def get_dashboard_data():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as c FROM devices').fetchone()['c']
    online = conn.execute("SELECT COUNT(*) as c FROM devices WHERE status = 'online'").fetchone()['c']
    devices = conn.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()
    device_list = []
    for device in devices:
        latest = conn.execute('SELECT wifi_ssid, uptime_seconds FROM sensor_data WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1', (device['device_id'],)).fetchone()
        device_list.append({
            'device_id': device['device_id'],
            'device_name': device['device_name'],
            'device_type': device['device_type'],
            'location': device['location'],
            'latitude': device['latitude'] if 'latitude' in device.keys() else 0,
            'longitude': device['longitude'] if 'longitude' in device.keys() else 0,
            'status': device['status'],
            'last_seen': device['last_seen'],
            'latest_wifi_ssid': latest['wifi_ssid'] if latest and 'wifi_ssid' in latest.keys() else '',
            'latest_uptime_seconds': latest['uptime_seconds'] if latest and 'uptime_seconds' in latest.keys() else 0
        })
    conn.close()
    return jsonify({'success': True, 'summary': {'total_devices': total, 'online_devices': online, 'offline_devices': total - online}, 'devices': device_list}), 200

# ============ WEB ROUTES (DENGAN LOGIN) ============
@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/mobile')
@login_required
def mobile_dashboard():
    return render_template('mobile.html')

@app.route('/device/<device_id>')
@login_required
def device_detail(device_id):
    return render_template('device_detail.html', device_id=device_id)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)