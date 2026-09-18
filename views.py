"""
NEXUS IoT - Web Views
"""
from flask import Blueprint, render_template
from auth import login_required

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')


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