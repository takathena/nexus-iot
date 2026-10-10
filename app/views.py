"""
NEXUS IoT - Web Views
"""
from flask import Blueprint, render_template, abort, session
from app.auth import login_required
from app.database import get_db_context
from app.dashboards import _find_dashboard_by_slug
from app import workspace as ws

views_bp = Blueprint('views', __name__)


def _default_dashboard(conn, user_id):
    return conn.execute(
        'SELECT id, slug FROM dashboards WHERE user_id = ? '
        'ORDER BY is_default DESC, id ASC LIMIT 1', (user_id,)
    ).fetchone()


@views_bp.route('/')
@login_required
def dashboard():
    user_id = session.get('user_id')
    with get_db_context() as conn:
        d = _default_dashboard(conn, user_id) if user_id else None
        admin = ws.is_admin_user(conn, user_id)
    return render_template('dashboard.html', dashboard_slug=None,
                           dashboard_id=d['id'] if d else '', view_all=False, is_admin=admin)


@views_bp.route('/d/<slug>')
@login_required
def dashboard_by_slug(slug):
    user_id = session.get('user_id')
    if not user_id:
        abort(401)

    with get_db_context() as conn:
        dash = _find_dashboard_by_slug(conn, slug, user_id)
        if not dash:
            abort(404)
        admin = ws.is_admin_user(conn, user_id)
    return render_template('dashboard.html', dashboard_slug=dash['slug'],
                           dashboard_id=dash['id'], view_all=False, is_admin=admin)


@views_bp.route('/all')
@login_required
def dashboard_all():
    """Tampilan admin: semua perangkat dari semua dashboard."""
    user_id = session.get('user_id')
    with get_db_context() as conn:
        if not ws.is_admin_user(conn, user_id):
            abort(404)
        d = _default_dashboard(conn, user_id)
    return render_template('dashboard.html', dashboard_slug=d['slug'] if d else None,
                           dashboard_id='all', view_all=True, is_admin=True)


@views_bp.route('/mobile')
@login_required
def mobile_dashboard():
    user_id = session.get('user_id')
    with get_db_context() as conn:
        d = _default_dashboard(conn, user_id) if user_id else None
    return render_template('mobile.html', dashboard_id=d['id'] if d else '')


@views_bp.route('/device/<device_id>')
@login_required
def device_detail(device_id):
    return render_template('device_detail.html', device_id=device_id)


@views_bp.route('/alerts')
@login_required
def alerts_page():
    return render_template('alerts.html')
