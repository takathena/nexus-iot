"""Paket A — penerapan izin di UI (desktop, mobile, Kelola Pengguna).

Tes ini memeriksa sumber, bukan tampilan. Penegakan sebenarnya ada di backend
(lihat test_paket_a_permissions.py).
"""
import os
import re
import shutil
import subprocess
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def test_desktop_attendance_nav_and_manage_button_are_gated():
    html = _read('templates', 'dashboard.html')
    assert 'data-section="attendance" data-needs="perm:attendance.view"' in html
    att = _read('templates', 'partials', 'attendance_section.html')
    assert 'data-needs="perm:attendance.manage"' in att


def test_desktop_router_refuses_attendance_without_permission():
    js = _read('static', 'js', 'dashboard.js')
    assert 'canViewAttendance()' in js
    assert 'Anda belum punya izin melihat absensi' in js


def test_desktop_handles_revoked_permission_mid_session():
    js = _read('static', 'js', 'dashboard.js')
    assert "'PERMISSION_DENIED'" in js
    assert 'handleAttendanceDenied' in js
    assert 'stopAttendancePolling();' in js


def test_ui_js_supports_permission_tokens():
    js = _read('static', 'js', 'ui.js')
    assert "'perm:'" in js


def test_mobile_gates_attendance_and_cardholder_actions():
    html = _read('templates', 'mobile.html')
    assert 'data-tab="attendance" data-perm="attendance.view"' in html
    assert 'data-perm="attendance.manage"' in html
    js = _read('static', 'js', 'mobile.js')
    assert 'function hasPerm' in js
    assert "hasPerm('attendance.view')" in js


def test_users_drawer_has_roles_and_attendance_permissions():
    part = _read('templates', 'partials', 'settings_section.html')
    for value in ('value="user"', 'value="moderator"', 'value="admin"'):
        assert value in part
    assert 'id="userPermView"' in part and 'id="userPermManage"' in part
    js = _read('static', 'js', 'users.js')
    assert '/permissions' in js
    assert "'role'" in js or 'payload.role' in js


def test_users_drawer_still_has_no_cancel_button():
    part = _read('templates', 'partials', 'settings_section.html')
    drawer = part[part.index('<aside class="nx-drawer"'):part.index('</aside>')]
    assert 'Batal' not in drawer
    footer = drawer[drawer.index('<footer'):]
    assert len(re.findall(r'<button', footer)) == 1


NODE = shutil.which('node')


def test_ui_js_permission_logic_node():
    if NODE is None:
        import pytest
        pytest.skip('node tidak tersedia')
    script = r"""
const fs = require('fs');
global.window = {};
global.document = { addEventListener() {}, querySelectorAll() { return []; } };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const A = window.NexusUI._allowed;
const cases = [
  ['perm:attendance.view', {isAdmin:false, permissions:['attendance.view']}],
  ['perm:attendance.view', {isAdmin:false, permissions:[]}],
  ['perm:attendance.manage', {isAdmin:false, permissions:['attendance.view']}],
  ['perm:attendance.view', {isAdmin:true, permissions:[]}],
  ['perm:attendance.view admin', {isAdmin:false, permissions:[]}],
];
console.log(JSON.stringify(cases.map(c => A(c[0], c[1]))));
"""
    res = subprocess.run([NODE, '-e', script, os.path.join(ROOT, 'static', 'js', 'ui.js')],
                         capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [True, False, False, True, False]
