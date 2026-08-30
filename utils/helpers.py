def format_bytes(num):
    for unit in ["B", "K", "M", "G", "T", "P"]:
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
