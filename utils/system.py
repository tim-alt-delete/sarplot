import time
import psutil

def get_os_release_info():
    info = {}
    with open("/etc/os-release") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                info[key] = value.strip('"')
    return info


def get_uptime():
    uptime_seconds = time.time() - psutil.boot_time()
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"


def get_network_interfaces():
    # Network Interfaces
    net_info = []
    for iface, addrs in psutil.net_if_addrs().items():
        ips = [a.address for a in addrs if a.family == 2]  # AF_INET
        if ips:
            net_info.append(f"{iface}: {', '.join(ips)}")
    return net_info
    

def get_disk_info():
    # Disks
    disk_info = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disk_info.append(f"{part.device}: {round(usage.total/(1024**3),2)} GB total")
        except PermissionError:
            continue
    return disk_info