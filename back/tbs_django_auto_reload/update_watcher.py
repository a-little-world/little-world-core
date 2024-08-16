import time
import os
import requests

if __name__ == "__main__":
    FRONTEND_TO_WATCH = ["main_frontend", "admin_panel_frontend"]

    def try_get_timestamp(name):
        try:
            return os.path.getmtime(f"/front/{name}.webpack-stats.json")
        except FileNotFoundError:
            return None

    last_frontend_timestamps = {name: try_get_timestamp(name) for name in FRONTEND_TO_WATCH}

    try:
        time.sleep(4.0)
        while True:
            time.sleep(1.0)
            f = os.path.getmtime("/front/main_frontend.webpack-stats.json")

            changed = False
            new_frontend_timestamps = {name: try_get_timestamp(name) for name in FRONTEND_TO_WATCH}

            for key in new_frontend_timestamps:
                if new_frontend_timestamps[key] != last_frontend_timestamps[key]:
                    print(f"Detected change in {key}")
                    last_frontend_timestamps[key] = new_frontend_timestamps[key]
                    changed = True

            if changed:
                try:
                    requests.get("http://localhost:8000/api/auto-reload/trigger-reload")
                except Exception as e:
                    print(f"Failed to trigger reload: {e}")

    except KeyboardInterrupt:
        pass
