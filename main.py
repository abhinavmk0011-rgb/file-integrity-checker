import hashlib
import os
import json
import shutil
import difflib
import stat
import datetime
import fnmatch

BASELINE_FILE = "baseline.json"
SNAP_DIR = ".snapshots"
LOG_FILE = "integrity_log.txt"
MAX_SNAPSHOT = 1024 * 1024
MAX_DIFF_LINES = 40
DEFAULT_EXCLUDES = [".git", "__pycache__", "*.pyc", ".snapshots", "baseline.json", "integrity_log.txt"]

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

banner = r"""
 _____ _ _        ___     _            _ _
|  ___(_) | ___  |_ _|_ _| |_ ___  __ _(_) |_ _   _
| |_  | | |/ _ \  | || '_ \ __/ _ \/ _` | | __| | | |
|  _| | | |  __/  | || | | ||  __/ (_| | | |_| |_| |
|_|   |_|_|\___| |___|_| |_|\__\___|\__, |_|\__|\__, |
     ____ _               _        |___/       |___/
    / ___| |__   ___  ___| | _____ _ __
   | |   | '_ \ / _ \/ __| |/ / _ \ '__|
   | |___| | | |  __/ (__|   <  __/ |
    \____|_| |_|\___|\___|_|\_\___|_|
"""

BASELINE_ABS = os.path.abspath(BASELINE_FILE)
SNAP_ABS = os.path.abspath(SNAP_DIR)


def calculate_hash(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4096):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_text(path):
    try:
        with open(path, "rb") as f:
            return b"\0" not in f.read(2048)
    except OSError:
        return False


def snap_path(path):
    return os.path.join(SNAP_DIR, hashlib.sha256(path.encode()).hexdigest())


def is_excluded(name, patterns):
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def collect_files(target, patterns):
    if os.path.isfile(target):
        return [target]
    found = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs
                   if not is_excluded(d, patterns)
                   and os.path.abspath(os.path.join(root, d)) != SNAP_ABS]
        for name in files:
            if is_excluded(name, patterns):
                continue
            full = os.path.abspath(os.path.join(root, name))
            if full == BASELINE_ABS or os.path.islink(full):
                continue
            found.append(full)
    return found


def file_meta(path):
    st = os.stat(path)
    return {"size": st.st_size, "mode": stat.filemode(st.st_mode), "mtime": st.st_mtime}


def read_lines(path):
    with open(path, "r", errors="replace") as f:
        return f.read().splitlines()


def show_diff(path):
    snap = snap_path(path)
    if not os.path.exists(snap):
        print("    (no text snapshot available - binary or large file)")
        return
    try:
        old = read_lines(snap)
        new = read_lines(path)
    except OSError:
        print("    (could not read file to compare)")
        return
    diff = list(difflib.unified_diff(old, new, fromfile="baseline",
                                     tofile="current", lineterm="", n=1))
    for i, line in enumerate(diff):
        if i >= MAX_DIFF_LINES:
            print(f"    ... ({len(diff) - MAX_DIFF_LINES} more diff lines)")
            break
        if line.startswith(("---", "+++")):
            print(f"    {CYAN}{line}{RESET}")
        elif line.startswith("@@"):
            print(f"    {YELLOW}{line}{RESET}")
        elif line.startswith("+"):
            print(f"    {GREEN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"    {RED}{line}{RESET}")
        else:
            print(f"    {line}")


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def create_baseline():
    target = input("Enter file or folder to protect: ").strip()
    target = os.path.abspath(os.path.expanduser(target))
    if not os.path.exists(target):
        print("Path not found.")
        return

    extra = input("Extra exclude patterns, comma separated (or press Enter to skip): ").strip()
    patterns = DEFAULT_EXCLUDES + [p.strip() for p in extra.split(",") if p.strip()]

    shutil.rmtree(SNAP_DIR, ignore_errors=True)
    os.makedirs(SNAP_DIR)

    print("Scanning...")
    files_data = {}
    skipped = 0
    for path in collect_files(target, patterns):
        try:
            files_data[path] = {"hash": calculate_hash(path), **file_meta(path)}
            if os.path.getsize(path) <= MAX_SNAPSHOT and is_text(path):
                shutil.copyfile(path, snap_path(path))
        except OSError:
            skipped += 1

    with open(BASELINE_FILE, "w") as f:
        json.dump({
            "target": target,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "excludes": patterns,
            "files": files_data,
        }, f, indent=2)

    msg = f"Baseline created for {target}: {len(files_data)} files recorded, {skipped} skipped."
    print(msg)
    log(f"[{datetime.datetime.now()}] {msg}")


def check_integrity():
    if not os.path.exists(BASELINE_FILE):
        print("No baseline found. Create one first.")
        return

    with open(BASELINE_FILE) as f:
        data = json.load(f)
    target = data["target"]
    old_files = data["files"]
    patterns = data.get("excludes", DEFAULT_EXCLUDES)

    if not os.path.exists(target):
        print(f"Baseline target no longer exists: {target}")
        return

    print(f"Checking: {target}  (baseline from {data.get('created', 'unknown')})")
    new_files = {}
    for path in collect_files(target, patterns):
        try:
            new_files[path] = {"hash": calculate_hash(path), **file_meta(path)}
        except OSError:
            continue

    modified = [p for p in new_files if p in old_files and new_files[p]["hash"] != old_files[p]["hash"]]
    perm_only = [p for p in new_files
                 if p in old_files and p not in modified
                 and new_files[p]["mode"] != old_files[p]["mode"]]
    added = [p for p in new_files if p not in old_files]
    deleted = [p for p in old_files if p not in new_files]
    unchanged = len(new_files) - len(modified) - len(perm_only) - len(added)

    timestamp = datetime.datetime.now().isoformat(timespec="seconds")

    if not (modified or added or deleted or perm_only):
        print(f"\n{GREEN}All {len(new_files)} files are unchanged.{RESET}")
        log(f"[{timestamp}] Check on {target}: all {len(new_files)} files unchanged.")
        return

    for p in modified:
        print(f"\n{RED}[MODIFIED]{RESET} {p}  ({old_files[p]['size']} -> {new_files[p]['size']} bytes)")
        show_diff(p)
    for p in perm_only:
        print(f"\n{YELLOW}[PERMISSIONS CHANGED]{RESET} {p}  "
              f"({old_files[p]['mode']} -> {new_files[p]['mode']})")
    for p in added:
        print(f"\n{YELLOW}[NEW FILE]{RESET} {p}")
    for p in deleted:
        print(f"\n{RED}[DELETED]{RESET} {p}")

    summary = (f"{len(modified)} modified, {len(perm_only)} permission-changed, "
               f"{len(added)} new, {len(deleted)} deleted, {unchanged} unchanged")
    print(f"\n{BOLD}Summary: {summary}.{RESET}")
    log(f"[{timestamp}] Check on {target}: {summary}.")


def view_log():
    if not os.path.exists(LOG_FILE):
        print("No log entries yet.")
        return
    with open(LOG_FILE) as f:
        content = f.read().strip()
    print(content if content else "Log is empty.")


print(banner)

while True:
    print("\n--- File integrity checker ---")
    print("1. Create baseline (file or folder)")
    print("2. Check integrity")
    print("3. View log history")
    print("4. Exit")

    choice = input("Enter your choice: ").strip()

    if choice == "1":
        create_baseline()
    elif choice == "2":
        check_integrity()
    elif choice == "3":
        view_log()
    elif choice == "4":
        print("Exiting...")
        break
    else:
        print("invalid choice.")
