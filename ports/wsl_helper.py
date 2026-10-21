"""WSL helper - runs INSIDE the Linux distribution (stdlib only).

Protocol: JSON Lines on stdin/stdout.
  In:  {"cmd": "signal", "pid": 1234, "sig": 15}
       {"cmd": "ping"}
  Out: {"type": "snapshot", "shell_pid": N, "listeners": [...], "procs": {...}}
       {"type": "ack", "cmd": "signal", "ok": true, "message": "..."}

Listener attribution: parses /proc/net/tcp{,6} for LISTEN sockets, then maps
socket inodes to PIDs by scanning /proc/<pid>/fd (same-user visibility).
Descendants of the session shell are resolved via /proc/<pid>/task/*/children.

Launched by wsl_backend.py as:
  python3 -u -c "$(cat wsl_helper.py)" <shell_pid>
or via a temp file. Emits a snapshot every 1.5s on stdout.
"""

import json
import os
import select
import signal
import sys
import time

INTERVAL = 1.5


def read_file(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError:
        return ""


def parse_proc_net_tcp(path, family):
    """Return {inode: (hex_addr, port)} for LISTEN (0A) sockets."""
    out = {}
    for line in read_file(path).splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10 or parts[3] != "0A":
            continue
        local = parts[1]
        addr_hex, port_hex = local.rsplit(":", 1)
        port = int(port_hex, 16)
        if family == 4:
            b = bytes.fromhex(addr_hex)
            addr = ".".join(str(x) for x in reversed(b))
        else:
            raw = bytes.fromhex(addr_hex)
            # /proc stores 4 little-endian 32-bit words
            words = [raw[i:i + 4][::-1] for i in range(0, 16, 4)]
            packed = b"".join(words)
            import ipaddress
            addr = str(ipaddress.IPv6Address(packed))
        inode = parts[9]
        out[inode] = (addr, port)
    return out


def socket_inodes_for_pid(pid):
    inodes = set()
    fd_dir = f"/proc/{pid}/fd"
    try:
        for fd in os.listdir(fd_dir):
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if target.startswith("socket:["):
                inodes.add(target[8:-1])
    except OSError:
        pass
    return inodes


def proc_name(pid):
    return read_file(f"/proc/{pid}/comm").strip()


def proc_start_time(pid):
    """Process start time in clock ticks since boot (field 22 of stat)."""
    stat = read_file(f"/proc/{pid}/stat")
    try:
        return int(stat.rsplit(")", 1)[1].split()[19])
    except (IndexError, ValueError):
        return 0


def children_of(pid):
    out = []
    task_dir = f"/proc/{pid}/task"
    try:
        for tid in os.listdir(task_dir):
            text = read_file(f"{task_dir}/{tid}/children")
            out.extend(int(x) for x in text.split() if x.isdigit())
    except OSError:
        pass
    return out


def descendants(root_pid):
    seen, stack = set(), [root_pid]
    while stack:
        pid = stack.pop()
        for child in children_of(pid):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    seen.discard(root_pid)
    return seen


def snapshot(shell_pid):
    sockets = {}
    sockets.update(parse_proc_net_tcp("/proc/net/tcp", 4))
    sockets.update(parse_proc_net_tcp("/proc/net/tcp6", 6))
    members = descendants(shell_pid) | {shell_pid}

    # Map inodes to pids we can see.
    inode_owner = {}
    for pid in members:
        for inode in socket_inodes_for_pid(pid):
            inode_owner[inode] = pid

    listeners = []
    for inode, (addr, port) in sockets.items():
        pid = inode_owner.get(inode)
        if pid is None:
            # Socket may belong to a process we can't see or a non-member.
            pid = find_any_owner(inode, members)
        listeners.append({
            "address": addr,
            "port": port,
            "pid": pid,
            "name": proc_name(pid) if pid else "",
            "start": proc_start_time(pid) if pid else 0,
            "session_owned": pid in members if pid else False,
        })
    procs = {str(p): {"name": proc_name(p), "start": proc_start_time(p)}
             for p in members}
    return {"type": "snapshot", "shell_pid": shell_pid,
            "listeners": listeners, "procs": procs}


def find_any_owner(inode, skip):
    """Scan all visible /proc pids for an inode (for external labeling)."""
    try:
        pids = [int(p) for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return None
    for pid in pids:
        if pid in skip:
            continue
        if inode in socket_inodes_for_pid(pid):
            return pid
    return None


def handle_command(cmd):
    if cmd.get("cmd") == "ping":
        return {"type": "ack", "cmd": "ping", "ok": True, "message": "pong"}
    if cmd.get("cmd") == "signal":
        pid = int(cmd.get("pid", 0))
        sig = int(cmd.get("sig", signal.SIGTERM))
        if sig not in (signal.SIGTERM, signal.SIGKILL, signal.SIGINT):
            return {"type": "ack", "cmd": "signal", "ok": False,
                    "message": "refused signal"}
        try:
            os.kill(pid, sig)
            return {"type": "ack", "cmd": "signal", "ok": True,
                    "message": f"sent signal {sig} to {pid}"}
        except ProcessLookupError:
            return {"type": "ack", "cmd": "signal", "ok": False,
                    "message": "process already exited"}
        except PermissionError:
            return {"type": "ack", "cmd": "signal", "ok": False,
                    "message": "permission denied"}
        except OSError as e:
            return {"type": "ack", "cmd": "signal", "ok": False,
                    "message": str(e)}
    return {"type": "ack", "cmd": str(cmd.get("cmd")), "ok": False,
            "message": "unknown command"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"type": "error", "message": "missing shell_pid"}))
        sys.exit(2)
    shell_pid = int(sys.argv[1])
    stdin_fd = sys.stdin.fileno()
    last = 0.0
    while True:
        now = time.monotonic()
        if now - last >= INTERVAL:
            try:
                os.kill(shell_pid, 0)
            except OSError:
                break  # shell gone; helper exits
            print(json.dumps(snapshot(shell_pid)), flush=True)
            last = now
        ready, _, _ = select.select([stdin_fd], [], [], 0.25)
        if ready:
            line = os.read(stdin_fd, 65536)
            if not line:
                break  # coordinator closed stdin
            for chunk in line.decode("utf-8", "replace").splitlines():
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    cmd = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                print(json.dumps(handle_command(cmd)), flush=True)


if __name__ == "__main__":
    main()
