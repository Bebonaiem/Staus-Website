import requests
import time
# CORRECTED IMPORT LINE
from datetime import datetime, timezone, timedelta 
from app.models import get_db_connection

def send_webhook_alert(service_name, status):
    """Sends a notification to Slack/Discord for status changes."""
    conn = get_db_connection()
    webhook_url_row = conn.execute("SELECT value FROM settings WHERE key = 'slack_webhook_url'").fetchone()
    conn.close()
    
    if not webhook_url_row or not webhook_url_row['value']:
        return

    webhook_url = webhook_url_row['value']
    
    if status == 'Major Outage':
        payload = { "text": f"🚨 *Major Outage Detected* 🚨\nThe service *{service_name}* appears to be down." }
    elif status == 'Operational':
        payload = { "text": f"✅ *Service Recovered* ✅\nThe service *{service_name}* is back to operational." }
    else:
        return

    try:
        requests.post(webhook_url, json=payload, timeout=10)
        print(f"Sent '{status}' alert for {service_name}.")
    except Exception as e:
        print(f"Failed to send webhook alert: {e}")

def get_status(url):
    """Checks a single URL and returns its status and response time."""
    try:
        start_time = time.monotonic()
        r = requests.get(url, timeout=10)
        response_time = int((time.monotonic() - start_time) * 1000)
        
        return ("Operational" if r.status_code < 400 else "Major Outage"), response_time
    except requests.RequestException:
        return "Major Outage", -1

def check_services():
    """The main function to loop through services and update their status, now maintenance-aware."""
    conn = get_db_connection()
    services = conn.execute('SELECT * FROM services').fetchall()
    
    now_utc = datetime.now(timezone.utc)
    active_maintenances_rows = conn.execute(
        """
        SELECT ms.service_id
        FROM scheduled_maintenances sm
        JOIN maintenance_services ms ON sm.id = ms.maintenance_id
        WHERE sm.start_time <= ? AND sm.end_time >= ?
        """,
        (now_utc.strftime('%Y-%m-%d %H:%M:%S'), now_utc.strftime('%Y-%m-%d %H:%M:%S'))
    ).fetchall()
    
    services_in_maintenance = {row['service_id'] for row in active_maintenances_rows}
    
    for service in services:
        previous_status = service['status']
        
        if service['id'] in services_in_maintenance:
            status = "Under Maintenance"
            response_time = -1
        else:
            status, response_time = get_status(service['url'])
        
        conn.execute('INSERT INTO status_history (service_id, status, response_time) VALUES (?, ?, ?)',
                     (service['id'], status, response_time))
        
        if status != previous_status:
            if status == 'Major Outage':
                send_webhook_alert(service['name'], 'Major Outage')
            elif status == 'Operational' and previous_status == 'Major Outage':
                send_webhook_alert(service['name'], 'Operational')
        
        conn.execute("""
            UPDATE services 
            SET status = ?, response_time = ?, last_checked = ?
            WHERE id = ?
        """, (status, response_time, datetime.now(timezone.utc), service['id']))

    # The line that was causing the error is now correct because of the new import
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    conn.execute('DELETE FROM status_history WHERE timestamp < ?', (ninety_days_ago,))

    conn.commit()
    conn.close()