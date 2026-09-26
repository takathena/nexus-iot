"""
NEXUS IoT - Web Views
"""
from flask import Blueprint, render_template, abort, session
from app.auth import login_required
from app.database import get_db_context

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', dashboard_slug=None)


@views_bp.route('/d/<slug>')
@login_required
def dashboard_by_slug(slug):
    # ✅ FIX Tier 1 #4: filter user_id
    user_id = session.get('user_id')
    if not user_id:
        abort(401)

    with get_db_context() as conn:
        dash = conn.execute(
            'SELECT slug FROM dashboards WHERE slug = ? AND user_id = ?',
            (slug, user_id)
        ).fetchone()
        if not dash:
            abort(404)
    return render_template('dashboard.html', dashboard_slug=slug)


@views_bp.route('/mobile')
@login_required
def mobile_dashboard():
    return render_template('mobile.html')


@views_bp.route('/device/<device_id>')
@login_required
def device_detail(device_id):
    return render_template('device_detail.html', device_id=device_id)


@views_bp.route('/alerts')
@login_required
def alerts_page():
    return render_template('alerts.html')