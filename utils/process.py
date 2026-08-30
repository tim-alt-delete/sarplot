import psutil
from utils.helpers import format_bytes
import sys

PROC_STATES = {
    "running": "R",
    "sleeping": "S",
    "disk-sleep": "D",
    "stopped": "T",
    "tracing-stop": "t",
    "zombie": "Z",
    "dead": "X",
    "wake-kill": "K",
    "waking": "W",
    "parked": "P",
    "idle": "I",
    "locked": "L",
    "waiting": "W",
}

def get_processes():
    processes = []
    for p in psutil.process_iter(['pid']):
        try:
            with p.oneshot():
                pid = p.pid
                username = p.username()
                #priority = p.
                nice = p.nice()

                mem_info = p.memory_info()
                # virtual memory
                vms = format_bytes(mem_info.vms)
                # resident set size
                rss = format_bytes(mem_info.rss)
                # shared memory
                # Does not exist on all platforms, notably macOS, and some BSD systems
                shared = getattr(mem_info, "shared", "")
                status = PROC_STATES.get(p.status(), "")
                cpu_percent = p.cpu_percent()
                mem_percent = p.memory_percent()
                time = p.cpu_times().user + p.cpu_times().system # minutes
                if p.cmdline():
                    command = " ".join(p.cmdline())
                else:
                    command = p.name()
                # prevent very long command lines
                command = command[:120]
                proc_info = {
                    "pid": pid,
                    "username": username,
                    "nice": nice,
                    "vms": vms,
                    "rss": rss,
                    "shared": shared,
                    "status": status,
                    "cpu_percent": cpu_percent,
                    "mem_percent": mem_percent,
                    "time": time,
                    "command": command,
                }

                processes.append(proc_info)

        except (
            psutil.NoSuchProcess, 
            psutil.AccessDenied,
            psutil.ZombieProcess
        ):
            continue
        #TODO: some processes don't get iterated due to permissions issues
        # except Exception as e:
        #     print("Error: e")
        #     sys.exit(1)

    return processes