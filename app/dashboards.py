"""
NEXUS IoT - Dashboard & Analytics Management (Multi-User)
"""
import re
import json
import logging

from flask import Blueprint, request, jsonify, session

from app.auth import login_required, ensure_user_dashboard
from app.database import get_db_context, get_wib_time
from app.utils import safe_json_loads
from app.extensions import limiter
from app.config import get_config

logger = logging.getLogger('nexus')

dashboards_bp = Blueprint('dashboards', __name__, url_prefix='/api/v1')

SLUG_RE = re.compile(r'^[a-z0-9\-]+$')
VALID_WIDGET_TYPES = {
    'line_chart', 'bar_chart', 'area_chart',
    'doughnut_chart', 'pie_chart', 'polar_area', 'radar_chart',
    'horizontal_bar', 'stacked_bar', 'stacked_area',
}


def _get_user_id():
    return session.get('user_id')


def _validate_slug(slug):
    return bool(slug) and SLUG_RE.match(slug) and len(slug) <= 64


def _owns_dashboard(conn, dashboard_id, user_id):
    if not user_id:
        return False
    row = conn.execute(
        'SELECT id FROM dashboards WHERE id = ? AND user_id = ?',
        (dashboard_id, user_id)
    ).fetchone()
    return row is not None


def _owns_widget(conn, widget_id, user_id):
    if not user_id:
        return False
    row = conn.execute('''
        SELECT w.id FROM widgets w
        JOIN dashboards d ON w.dashboard_id = d.id
        WHERE w.id = ? AND d.user_id = ?
    ''', (widget_id, user_id)).fetchone()
    return row is not None


def _owns_tab(conn, tab_id, user_id):
    if not user_id:
        return False
    row = conn.execute('''
        SELECT t.id FROM analytics_tabs t
        JOIN dashboards d ON t.dashboard_id = d.id
        WHERE t.id = ? AND d.user_id = ?
    ''', (tab_id, user_id)).fetchone()
    return row is not None


# ==========================================
# DASHBOARDS
# ==========================================
@dashboards_bp.route('/dashboards', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def list_dashboards():
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid, re-login'}), 401

    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT d.*, COUNT(w.id) AS widget_count
            FROM dashboards d
            LEFT JOIN widgets w ON w.dashboard_id = d.id
            WHERE d.user_id = ?
            GROUP BY d.id
            ORDER BY d.is_default DESC, d.created_at ASC
        ''', (user_id,)).fetchall()

    # Auto-create kalau kosong
    if not rows:
        username = session.get('username', 'user')
        try:
            ensure_user_dashboard(user_id, username)
            with get_db_context() as conn:
                rows = conn.execute('''
                    SELECT d.*, COUNT(w.id) AS widget_count
                    FROM dashboards d
                    LEFT JOIN widgets w ON w.dashboard_id = d.id
                    WHERE d.user_id = ?
                    GROUP BY d.id
                    ORDER BY d.is_default DESC, d.created_at ASC
                ''', (user_id,)).fetchall()
        except Exception as e:
            logger.error(f"Auto-create dashboard failed: {e}")

    return jsonify({'success': True, 'dashboards': [dict(r) for r in rows]}), 200


@dashboards_bp.route('/dashboards', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def create_dashboard():
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    slug_input = (data.get('slug') or '').strip().lower().replace(' ', '-')

    if not name:
        return jsonify({'success': False, 'error': 'Nama dashboard wajib diisi'}), 400

    if slug_input and not _validate_slug(slug_input):
        return jsonify({'success': False, 'error': 'Slug hanya huruf kecil, angka, dan dash'}), 400

    # Auto-generate slug dari nama kalau kosong
    if not slug_input:
        slug_input = re.sub(r'[^a-z0-9\-]+', '-', name.lower()).strip('-') or 'dashboard'

    with get_db_context() as conn:
        exists = conn.execute(
            'SELECT id FROM dashboards WHERE slug = ? AND user_id = ?',
            (slug_input, user_id)
        ).fetchone()

        if exists:
            # Append suffix
            i = 2
            base = slug_input
            while exists:
                slug_input = f"{base}-{i}"
                i += 1
                exists = conn.execute(
                    'SELECT id FROM dashboards WHERE slug = ? AND user_id = ?',
                    (slug_input, user_id)
                ).fetchone()

        cur = conn.execute('''
            INSERT INTO dashboards
            (slug, name, description, icon, is_default, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
        ''', (
            slug_input, name,
            data.get('description', ''),
            data.get('icon', 'fa-chart-line'),
            user_id,
            get_wib_time(), get_wib_time()
        ))
        conn.commit()
        new_id = cur.lastrowid

    logger.info(f"Dashboard created: id={new_id} user={user_id} slug={slug_input}")
    return jsonify({'success': True, 'id': new_id, 'slug': slug_input}), 201


@dashboards_bp.route('/dashboards/<int:dashboard_id>', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_dashboard_detail(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        dash = conn.execute('SELECT * FROM dashboards WHERE id = ?', (dashboard_id,)).fetchone()

        widgets = conn.execute('''
            SELECT * FROM widgets WHERE dashboard_id = ?
            ORDER BY grid_y ASC, grid_x ASC
        ''', (dashboard_id,)).fetchall()

    widget_list = []
    for w in widgets:
        wd = dict(w)
        wd['config'] = safe_json_loads(wd['config'])
        widget_list.append(wd)

    return jsonify({'success': True, 'dashboard': dict(dash), 'widgets': widget_list}), 200


@dashboards_bp.route('/dashboards/slug/<slug>', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_dashboard_by_slug(slug):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        dash = conn.execute(
            'SELECT * FROM dashboards WHERE slug = ? AND user_id = ?',
            (slug, user_id)
        ).fetchone()

        if not dash:
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        widgets = conn.execute('''
            SELECT * FROM widgets WHERE dashboard_id = ?
            ORDER BY grid_y ASC, grid_x ASC
        ''', (dash['id'],)).fetchall()

    widget_list = []
    for w in widgets:
        wd = dict(w)
        wd['config'] = safe_json_loads(wd['config'])
        widget_list.append(wd)

    return jsonify({'success': True, 'dashboard': dict(dash), 'widgets': widget_list}), 200


@dashboards_bp.route('/dashboards/<int:dashboard_id>', methods=['PUT'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def update_dashboard(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        conn.execute('''
            UPDATE dashboards SET
                name = COALESCE(?, name),
                description = COALESCE(?, description),
                icon = COALESCE(?, icon),
                updated_at = ?
            WHERE id = ?
        ''', (
            data.get('name'),
            data.get('description'),
            data.get('icon'),
            get_wib_time(),
            dashboard_id
        ))
        conn.commit()

    return jsonify({'success': True}), 200


@dashboards_bp.route('/dashboards/<int:dashboard_id>/set-default', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def set_default_dashboard(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        now = get_wib_time()
        conn.execute(
            'UPDATE dashboards SET is_default = 0, updated_at = ? WHERE user_id = ? AND is_default = 1',
            (now, user_id)
        )
        conn.execute(
            'UPDATE dashboards SET is_default = 1, updated_at = ? WHERE id = ?',
            (now, dashboard_id)
        )
        conn.commit()

    logger.info(f"Dashboard {dashboard_id} set as default for user {user_id}")
    return jsonify({'success': True}), 200


@dashboards_bp.route('/dashboards/<int:dashboard_id>', methods=['DELETE'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_dashboard(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        dash = conn.execute(
            'SELECT id, is_default FROM dashboards WHERE id = ? AND user_id = ?',
            (dashboard_id, user_id)
        ).fetchone()

        if not dash:
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404
        if dash['is_default']:
            return jsonify({'success': False, 'error': 'Dashboard default tidak bisa dihapus'}), 400

        conn.execute('DELETE FROM widgets WHERE dashboard_id = ?', (dashboard_id,))
        conn.execute('DELETE FROM analytics_tabs WHERE dashboard_id = ?', (dashboard_id,))
        conn.execute('DELETE FROM dashboards WHERE id = ?', (dashboard_id,))
        conn.commit()

    logger.info(f"Dashboard deleted: id={dashboard_id} user={user_id}")
    return jsonify({'success': True}), 200


# ==========================================
# ANALYTICS TABS
# ==========================================
@dashboards_bp.route('/dashboards/<int:dashboard_id>/analytics-tabs', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def list_analytics_tabs(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        rows = conn.execute('''
            SELECT t.*, COUNT(w.id) AS widget_count
            FROM analytics_tabs t
            LEFT JOIN widgets w ON w.analytics_tab_id = t.id
            WHERE t.dashboard_id = ?
            GROUP BY t.id
            ORDER BY t.position ASC, t.id ASC
        ''', (dashboard_id,)).fetchall()

    return jsonify({'success': True, 'tabs': [dict(r) for r in rows]}), 200


@dashboards_bp.route('/dashboards/<int:dashboard_id>/analytics-tabs', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def create_analytics_tab(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Nama tab wajib diisi'}), 400

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        row = conn.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM analytics_tabs WHERE dashboard_id = ?',
            (dashboard_id,)
        ).fetchone()
        next_pos = row['next_pos']

        cur = conn.execute('''
            INSERT INTO analytics_tabs (dashboard_id, name, icon, position, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            dashboard_id, name,
            data.get('icon', 'fa-chart-line'),
            next_pos,
            get_wib_time(), get_wib_time()
        ))
        conn.commit()
        new_id = cur.lastrowid

    return jsonify({
        'success': True,
        'id': new_id, 'name': name,
        'position': next_pos,
        'widget_count': 0,
    }), 201


@dashboards_bp.route('/analytics-tabs/<int:tab_id>', methods=['PUT'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def update_analytics_tab(tab_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}

    with get_db_context() as conn:
        if not _owns_tab(conn, tab_id, user_id):
            return jsonify({'success': False, 'error': 'Tab not found'}), 404

        fields, params = [], []
        for col in ['name', 'icon', 'position']:
            if col in data:
                fields.append(f'{col} = ?')
                params.append(data[col])

        if fields:
            fields.append('updated_at = ?')
            params.append(get_wib_time())
            params.append(tab_id)
            conn.execute(f'UPDATE analytics_tabs SET {", ".join(fields)} WHERE id = ?', params)
            conn.commit()

    return jsonify({'success': True}), 200


@dashboards_bp.route('/analytics-tabs/<int:tab_id>', methods=['DELETE'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_analytics_tab(tab_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        if not _owns_tab(conn, tab_id, user_id):
            return jsonify({'success': False, 'error': 'Tab not found'}), 404

        conn.execute('DELETE FROM widgets WHERE analytics_tab_id = ?', (tab_id,))
        conn.execute('DELETE FROM analytics_tabs WHERE id = ?', (tab_id,))
        conn.commit()

    return jsonify({'success': True}), 200


@dashboards_bp.route('/dashboards/<int:dashboard_id>/analytics-tabs/<int:tab_id>/widgets', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def list_tab_widgets(dashboard_id, tab_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        rows = conn.execute('''
            SELECT * FROM widgets
            WHERE dashboard_id = ? AND analytics_tab_id = ?
            ORDER BY grid_y ASC, grid_x ASC
        ''', (dashboard_id, tab_id)).fetchall()

    widget_list = []
    for w in rows:
        wd = dict(w)
        wd['config'] = safe_json_loads(wd['config'])
        widget_list.append(wd)

    return jsonify({'success': True, 'widgets': widget_list}), 200


# ==========================================
# WIDGETS
# ==========================================
@dashboards_bp.route('/dashboards/<int:dashboard_id>/widgets', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def create_widget(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}

    widget_type = data.get('widget_type', 'line_chart')
    if widget_type not in VALID_WIDGET_TYPES:
        return jsonify({'success': False, 'error': 'widget_type tidak valid'}), 400

    tab_id = data.get('analytics_tab_id')
    try:
        tab_id_int = int(tab_id) if tab_id not in (None, '', 0, '0') else None
    except (ValueError, TypeError):
        tab_id_int = None

    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        cur = conn.execute('''
            INSERT INTO widgets
            (dashboard_id, widget_type, title, device_id, config,
             grid_x, grid_y, grid_w, grid_h, analytics_tab_id,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            dashboard_id,
            widget_type,
            data.get('title', 'Untitled'),
            data.get('device_id'),
            json.dumps(data.get('config', {})),
            int(data.get('grid_x', 0)),
            int(data.get('grid_y', 0)),
            int(data.get('grid_w', 2)),
            int(data.get('grid_h', 2)),
            tab_id_int,
            get_wib_time(), get_wib_time()
        ))
        conn.commit()
        widget_id = cur.lastrowid

    return jsonify({'success': True, 'id': widget_id}), 201


@dashboards_bp.route('/widgets/<int:widget_id>', methods=['PUT'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def update_widget(widget_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}

    with get_db_context() as conn:
        if not _owns_widget(conn, widget_id, user_id):
            return jsonify({'success': False, 'error': 'Widget not found'}), 404

        fields, params = [], []
        for col in ['title', 'device_id', 'widget_type',
                    'grid_x', 'grid_y', 'grid_w', 'grid_h']:
            if col in data:
                fields.append(f'{col} = ?')
                params.append(data[col])

        if 'config' in data:
            fields.append('config = ?')
            params.append(json.dumps(data['config']))

        if fields:
            fields.append('updated_at = ?')
            params.append(get_wib_time())
            params.append(widget_id)
            conn.execute(f'UPDATE widgets SET {", ".join(fields)} WHERE id = ?', params)
            conn.commit()

    return jsonify({'success': True}), 200


@dashboards_bp.route('/widgets/<int:widget_id>', methods=['DELETE'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_widget(widget_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    with get_db_context() as conn:
        if not _owns_widget(conn, widget_id, user_id):
            return jsonify({'success': False, 'error': 'Widget not found'}), 404

        conn.execute('DELETE FROM widgets WHERE id = ?', (widget_id,))
        conn.commit()

    return jsonify({'success': True}), 200


@dashboards_bp.route('/dashboards/<int:dashboard_id>/layout', methods=['PUT'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def save_dashboard_layout(dashboard_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'success': False, 'error': 'Session invalid'}), 401

    data = request.get_json(silent=True) or {}
    layout = data.get('layout', [])

    if not isinstance(layout, list):
        return jsonify({'success': False, 'error': 'layout harus array'}), 400

    updated = 0
    with get_db_context() as conn:
        if not _owns_dashboard(conn, dashboard_id, user_id):
            return jsonify({'success': False, 'error': 'Dashboard not found'}), 404

        now = get_wib_time()
        for item in layout:
            wid = item.get('id')
            if not wid:
                continue
            result = conn.execute('''
                UPDATE widgets
                SET grid_x=?, grid_y=?, grid_w=?, grid_h=?, updated_at=?
                WHERE id = ? AND dashboard_id = ?
            ''', (
                int(item.get('x', 0)),
                int(item.get('y', 0)),
                int(item.get('w', 2)),
                int(item.get('h', 2)),
                now, wid, dashboard_id
            ))
            if result.rowcount > 0:
                updated += 1
        conn.commit()

    return jsonify({'success': True, 'updated': updated}), 200