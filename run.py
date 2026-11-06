"""Start the site, clearing up "port already in use" automatically.

Any older copy of this site is stopped first. If another program holds the port,
it's left alone and the site uses the next free port.
"""
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import List, Optional

import uvicorn

BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8030
PORTS_TO_TRY = 20


def is_site_process(args: List[str]) -> bool:
    """True for the command lines that start this site, but not e.g. `nano run.py`."""
    if "app.main:app" in args:
        return True
    return len(args) > 1 and Path(args[0]).name.startswith("python") and Path(args[1]).name == "run.py"


def running_copies() -> List[int]:
    """PIDs of other copies of this site, matched by command line and project folder."""
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    pids = []
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            args = (entry / "cmdline").read_bytes().decode(errors="ignore").split("\0")
            cwd = (entry / "cwd").resolve(strict=True)
        except OSError:
            continue
        if cwd == BASE_DIR and is_site_process(args):
            pids.append(int(entry.name))
    return pids


def send_signal(pids: List[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def stop_running_copies() -> None:
    pids = running_copies()
    if not pids:
        return
    print(f"Stopping the copy of the site that was already running (PID {', '.join(map(str, pids))}).", flush=True)
    send_signal(pids, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while running_copies() and time.monotonic() < deadline:
        time.sleep(0.1)
    send_signal(running_copies(), signal.SIGKILL)


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        # Matches uvicorn, so a recently closed port still counts as free.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def first_free_port(preferred: int) -> Optional[int]:
    for port in range(preferred, preferred + PORTS_TO_TRY):
        if port_is_free(port):
            return port
    return None


def main() -> None:
    os.chdir(BASE_DIR)
    stop_running_copies()

    # A brief wait, because a copy that was just stopped can take a moment to release its port.
    preferred = int(os.environ.get("PORT", DEFAULT_PORT))
    deadline = time.monotonic() + 2
    while not port_is_free(preferred) and time.monotonic() < deadline:
        time.sleep(0.1)

    port = first_free_port(preferred)
    if port is None:
        sys.exit(f"No free port between {preferred} and {preferred + PORTS_TO_TRY - 1}.")
    if port != preferred:
        print(f"Port {preferred} is used by another program, so using {port} instead.", flush=True)

    # app.config reads this for the admin link in alert emails.
    os.environ["PORT"] = str(port)
    print(f"Site:  http://localhost:{port}\nAdmin: http://localhost:{port}/admin", flush=True)
    uvicorn.run("app.main:app", host=HOST, port=port)


if __name__ == "__main__":
    main()
