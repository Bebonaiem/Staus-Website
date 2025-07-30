import threading
import time
from app import create_app
from app.core import check_services
from app.models import get_db_connection

app = create_app()

def run_background_checker():
    with app.app_context():
        print("Initial service check will run in 5 seconds...")
        time.sleep(5)
        while True:
            print(f"[{time.ctime()}] Running periodic service check...")
            try:
                check_services()
            except Exception as e:
                print(f"Error in checker thread: {e}")
            
            # Get sleep interval from DB
            sleep_interval = 60 # Default value
            try:
                conn = get_db_connection()
                interval_row = conn.execute("SELECT value FROM settings WHERE key = 'check_interval_seconds'").fetchone()
                conn.close()
                if interval_row and interval_row['value']:
                    sleep_interval = int(interval_row['value'])
            except Exception as e:
                print(f"Could not read interval from DB, defaulting to {sleep_interval}s. Error: {e}")
            
            print(f"Checker sleeping for {sleep_interval} seconds...")
            time.sleep(sleep_interval)

if __name__ == '__main__':
    checker_thread = threading.Thread(target=run_background_checker, daemon=True)
    checker_thread.start()
    app.run(host='0.0.0.0', port=80, debug=True)