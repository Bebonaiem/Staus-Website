from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from app.models import get_db_connection, User, get_user_row_by_email
from app import bcrypt 
from .forms import (LoginForm, ServiceAddForm, ServiceEditForm, SettingsForm, 
                    IncidentForm, IncidentUpdateForm, MaintenanceForm)
from .core import check_services

main = Blueprint('main', __name__)

def parse_db_times(rows, time_keys=['created_at', 'start_time', 'end_time', 'last_checked', 'timestamp']):
    """Converts timestamp strings from DB into timezone-aware datetime objects."""
    parsed_rows = []
    if not rows:
        return []
    for row in rows:
        row_dict = dict(row)
        for key in time_keys:
            if row_dict.get(key) and isinstance(row_dict[key], str):
                try:
                    if '.' in row_dict[key]:
                         dt_obj = datetime.strptime(row_dict[key], '%Y-%m-%d %H:%M:%S.%f')
                    else:
                         dt_obj = datetime.strptime(row_dict[key], '%Y-%m-%d %H:%M:%S')
                    row_dict[key] = dt_obj.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue
        parsed_rows.append(row_dict)
    return parsed_rows

@main.route('/lang/<language>')
def set_language(language=None):
    if language in ['en', 'es', 'fr', 'de', 'ar', 'ru']:
        session['lang'] = language
    return redirect(request.referrer or url_for('main.index'))

@main.route('/')
def index():
    conn = get_db_connection()
    page_title_row = conn.execute("SELECT value FROM settings WHERE key = 'page_title'").fetchone()
    incidents_rows = conn.execute("SELECT * FROM incidents WHERE status != 'Resolved' OR created_at > date('now', '-7 day') ORDER BY created_at DESC").fetchall()
    
    sixty_days_ago = datetime.utcnow() - timedelta(days=60)
    history_rows = conn.execute(
        """
        SELECT date(timestamp) as day,
               CASE
                   WHEN SUM(CASE WHEN status != 'Operational' THEN 1 ELSE 0 END) > 0 THEN 'outage'
                   ELSE 'operational'
               END as day_status
        FROM status_history
        WHERE timestamp >= ?
        GROUP BY date(timestamp)
        ORDER BY date(timestamp)
        """, (sixty_days_ago,)
    ).fetchall()
    
    interval_row = conn.execute("SELECT value FROM settings WHERE key = 'check_interval_seconds'").fetchone()
    conn.close()
    
    status_timeline = {row['day']: row['day_status'] for row in history_rows}
    incidents = parse_db_times(incidents_rows)
    page_title = page_title_row['value'] if page_title_row else 'System Status'
    check_interval = interval_row['value'] if interval_row else 60
    
    return render_template('index.html', 
                           page_title=page_title, 
                           incidents=incidents,
                           status_timeline=status_timeline,
                           check_interval_seconds=check_interval,
                           datetime=datetime,
                           timedelta=timedelta,
                           year=datetime.now().year)

@main.route('/login', methods=['GET', 'POST'])
def login():
    from app import custom_gettext as _
    if current_user.is_authenticated: return redirect(url_for('main.admin_services'))
    form = LoginForm()
    if form.validate_on_submit():
        user_row = get_user_row_by_email(form.email.data)
        if user_row and bcrypt.check_password_hash(user_row['password'], form.password.data):
            user = User(id=user_row['id'], email=user_row['email'])
            login_user(user)
            return redirect(url_for('main.admin_services'))
        else:
            flash(_('login_failed_message'), 'danger')
    return render_template('login.html', title=_('admin_login_title'), form=form)

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main.route('/api/status')
def api_status():
    from app import custom_gettext as _
    conn = get_db_connection()
    services_rows = conn.execute('SELECT id, name, status, response_time, icon FROM services ORDER BY name').fetchall()
    
    sixty_days_ago = datetime.utcnow() - timedelta(days=60)
    history_rows = conn.execute(
        "SELECT h.service_id, h.status, h.timestamp, h.response_time FROM status_history h WHERE h.timestamp >= ? ORDER BY h.service_id, h.timestamp",
        (sixty_days_ago,)
    ).fetchall()
    conn.close()

    history_by_service = defaultdict(list)
    for row in parse_db_times(history_rows):
        history_by_service[row['service_id']].append({
            'status': row['status'], 
            'timestamp': row['timestamp'].isoformat(), 
            'response_time': row['response_time']
        })
        
    services_list = []
    for s_row in services_rows:
        s_dict = dict(s_row)
        s_dict['status_translated'] = _(s_dict['status'].lower().replace(' ', '_'))
        service_history = history_by_service.get(s_dict['id'], [])
        s_dict['uptime_history'] = service_history

        twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_checks = [h for h in service_history if datetime.fromisoformat(h['timestamp']) > twenty_four_hours_ago]
        if recent_checks:
            operational_checks = sum(1 for h in recent_checks if h['status'] == 'Operational')
            uptime_percentage = (operational_checks / len(recent_checks)) * 100
            s_dict['uptime_24h'] = f"{uptime_percentage:.2f}"
        else:
            s_dict['uptime_24h'] = "100.00" if s_dict['status'] == 'Operational' else "0.00"
        services_list.append(s_dict)

    is_operational = all(s['status'] == 'Operational' for s in services_list) if services_list else True
    
    return jsonify({
        'services': services_list,
        'is_operational': is_operational,
        'all_systems_operational': _('all_systems_operational'),
        'some_systems_issues': _('some_systems_issues')
    })

@main.route('/api/admin/services', methods=['GET'])
@login_required
def api_admin_get_services():
    conn = get_db_connection()
    services = conn.execute('SELECT * FROM services ORDER BY id').fetchall()
    conn.close()
    return jsonify([dict(s) for s in services])

@main.route('/api/admin/services', methods=['POST'])
@login_required
def api_admin_add_service():
    form = ServiceAddForm(request.form)
    if form.validate():
        conn = get_db_connection()
        res = conn.execute('INSERT INTO services (name, url, icon) VALUES (?, ?, ?)',
                     (form.name.data, form.url.data, form.icon.data or 'fa-solid fa-globe'))
        conn.commit()
        new_service_id = res.lastrowid
        check_services()
        new_service = conn.execute('SELECT * FROM services WHERE id = ?', (new_service_id,)).fetchone()
        conn.close()
        return jsonify(dict(new_service)), 201
    return jsonify({'errors': form.errors}), 400

@main.route('/api/admin/services/<int:service_id>', methods=['PUT'])
@login_required
def api_admin_update_service(service_id):
    form = ServiceEditForm(request.form)
    if form.validate():
        conn = get_db_connection()
        conn.execute('UPDATE services SET name = ?, url = ?, icon = ? WHERE id = ?',
                     (form.name.data, form.url.data, form.icon.data, service_id))
        conn.commit()
        updated_service = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
        conn.close()
        return jsonify(dict(updated_service))
    return jsonify({'errors': form.errors}), 400

@main.route('/api/admin/services/<int:service_id>', methods=['DELETE'])
@login_required
def api_admin_delete_service(service_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM services WHERE id = ?', (service_id,))
    conn.execute('DELETE FROM status_history WHERE service_id = ?', (service_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Service deleted successfully'}), 200

@main.route('/admin/services')
@login_required
def admin_services():
    form = ServiceAddForm()
    edit_form = ServiceEditForm()
    return render_template('admin/services_live.html', page='services', form=form, edit_form=edit_form)

@main.route('/admin/incidents', methods=['GET', 'POST'])
@login_required
def admin_incidents():
    conn = get_db_connection()
    form = IncidentForm()
    update_form = IncidentUpdateForm()
    if form.validate_on_submit() and 'report_incident' in request.form:
        res = conn.execute('INSERT INTO incidents (title, status, severity) VALUES (?, ?, ?)', (form.title.data, form.status.data, form.severity.data))
        conn.execute('INSERT INTO incident_updates (incident_id, update_text, status) VALUES (?, ?, ?)', (res.lastrowid, form.update_text.data, form.status.data))
        conn.commit()
        flash('Incident reported.', 'success')
        return redirect(url_for('main.admin_incidents'))
    
    if update_form.validate_on_submit() and 'post_update' in request.form:
        incident_id = request.form.get('incident_id')
        conn.execute('INSERT INTO incident_updates (incident_id, update_text, status) VALUES (?, ?, ?)', (incident_id, update_form.update_text.data, update_form.status.data))
        conn.execute('UPDATE incidents SET status = ? WHERE id = ?', (update_form.status.data, incident_id))
        conn.commit()
        flash('Incident updated.', 'success')
        return redirect(url_for('main.admin_incidents'))

    incidents_raw = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
    incidents = []
    for inc in incidents_raw:
        updates = conn.execute("SELECT * FROM incident_updates WHERE incident_id = ? ORDER BY created_at DESC", (inc['id'],)).fetchall()
        inc_dict = dict(inc)
        inc_dict['updates'] = parse_db_times(updates)
        incidents.append(inc_dict)
    conn.close()
    return render_template('admin/incidents.html', page='incidents', form=form, update_form=update_form, incidents=parse_db_times(incidents))

@main.route('/admin/incidents/delete/<int:incident_id>', methods=['POST'])
@login_required
def admin_delete_incident(incident_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM incidents WHERE id = ?', (incident_id,))
    conn.commit()
    conn.close()
    flash('Incident deleted successfully.', 'success')
    return redirect(url_for('main.admin_incidents'))

@main.route('/admin/maintenances', methods=['GET', 'POST'])
@login_required
def admin_maintenances():
    conn = get_db_connection()
    form = MaintenanceForm()
    services_list = conn.execute("SELECT id, name FROM services ORDER BY name").fetchall()
    form.affected_services.choices = [(s['id'], s['name']) for s in services_list]

    if form.validate_on_submit():
        cursor = conn.cursor()
        cursor.execute('INSERT INTO scheduled_maintenances (title, description, start_time, end_time) VALUES (?, ?, ?, ?)', 
                     (form.title.data, form.description.data, form.start_time.data, form.end_time.data))
        maintenance_id = cursor.lastrowid

        for service_id in form.affected_services.data:
            conn.execute('INSERT INTO maintenance_services (maintenance_id, service_id) VALUES (?, ?)',
                         (maintenance_id, service_id))
        conn.commit()
        flash('Maintenance scheduled successfully.', 'success')
        return redirect(url_for('main.admin_maintenances'))

    maintenances_raw = conn.execute("SELECT * FROM scheduled_maintenances ORDER BY start_time DESC").fetchall()
    maintenances = []
    for maint in maintenances_raw:
        maint_dict = dict(maint)
        affected_services = conn.execute(
            "SELECT s.name FROM services s JOIN maintenance_services ms ON s.id = ms.service_id WHERE ms.maintenance_id = ?", (maint_dict['id'],)
        ).fetchall()
        maint_dict['affected_service_names'] = [s['name'] for s in affected_services]
        maintenances.append(maint_dict)
    conn.close()
    maintenances_parsed = parse_db_times(maintenances)
    
    return render_template('admin/maintenances.html', page='maintenances', form=form, maintenances=maintenances_parsed)

@main.route('/admin/maintenances/delete/<int:maint_id>', methods=['POST'])
@login_required
def admin_delete_maintenance(maint_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM scheduled_maintenances WHERE id = ?', (maint_id,))
    conn.commit()
    conn.close()
    flash('Maintenance deleted successfully.', 'success')
    return redirect(url_for('main.admin_maintenances'))

@main.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    from app import custom_gettext as _
    conn = get_db_connection()
    form = SettingsForm()
    if form.validate_on_submit():
        conn.execute("UPDATE settings SET value = ? WHERE key = 'page_title'", (form.page_title.data,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'slack_webhook_url'", (form.slack_webhook_url.data,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'check_interval_seconds'", (str(form.check_interval_seconds.data),))
        conn.commit()
        flash(_('settings_saved_success'), 'success')
        return redirect(url_for('main.admin_settings'))

    if not form.is_submitted():
        settings_rows = conn.execute("SELECT * FROM settings").fetchall()
        settings_data = {row['key']: row['value'] for row in settings_rows}
        form.process(data=settings_data)
    
    conn.close()
    return render_template('admin/settings.html', form=form, page='settings')