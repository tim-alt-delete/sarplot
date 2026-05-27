# Install sar / sysstat

Alma10
```bash
sudo dnf install -y sysstat
sudo systemctl start sysstat.service
sudo systemctl enable --now sysstat-collect.timer
```

Logs: Usually in /var/log/sa/saDD (DD = day of month).