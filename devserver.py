"""Restarts app.py whenever a watched source file changes. Dev tool only.

Polling-based on purpose: no watchdog/fswatch dependency, so it works for
every teammate with nothing but the python3 already required to run the app.
"""
import os
import subprocess
import sys
import time

WATCH_FILES = ["app.py", "deals.py", "digest.py", "listing_cards_ui.py"]
POLL_SECONDS = 0.5


def mtimes():
    return {f: os.path.getmtime(f) for f in WATCH_FILES if os.path.exists(f)}


def start():
    return subprocess.Popen([sys.executable, "app.py"])


def main():
    proc = start()
    last = mtimes()
    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = mtimes()
            if current != last:
                print("Change detected, restarting app.py...", flush=True)
                proc.terminate()
                proc.wait()
                last = current
                proc = start()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
