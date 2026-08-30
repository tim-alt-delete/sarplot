# sarplot

A terminal dashboard for Linux system metrics, built with
[Textual](https://textual.textualize.io/). It combines a live process viewer
with a browser for historical metrics recorded by
[sysstat](https://github.com/sysstat/sysstat) (`sar`).

## Features

- **Processes** - a sortable, filterable process table with in-place updates,
  plus terminate / kill / renice actions behind confirmation prompts.
- **Live** - continuously sampled plots of CPU (total or per-core), memory and
  swap, and network throughput.
- **History** - browse any sysstat archive: pick a day, a time window, a metric
  and which series to overlay. Covers CPU, memory, swap, load, I/O, block
  devices, network and paging.
- **System** - host, kernel, CPU, memory, filesystem and network overview.

Without sysstat installed the History tab explains how to enable it; every
other tab works regardless.

## Install

```bash
git clone https://github.com/tim/sarplot
cd sarplot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then run:

```bash
sarplot
```

`python -m sarplot` works too.

## Usage

```
sarplot [-f PATH] [-s HH:MM:SS] [-e HH:MM:SS] [-r SECONDS] [-t TAB]

  -f, --file PATH       sysstat archive to open, e.g. /var/log/sysstat/sa30
                        (default: the most recent archive found)
  -s, --start HH:MM:SS  start of the historical time window
  -e, --end HH:MM:SS    end of the historical time window
  -r, --refresh SECONDS process list refresh interval (default: 2.0)
  -t, --tab TAB         processes | live | history | system
  -V, --version         print the version and exit
```

Open yesterday's CPU history for the morning:

```bash
sarplot --tab history --file /var/log/sysstat/sa29 --start 08:00 --end 12:00
```

## Keys

| Key | Action |
| --- | --- |
| `q` | Quit |
| `d` | Toggle light / dark theme |
| `F5` | Force the active tab to refresh |
| `Tab` / `Shift+Tab` | Move between tabs and controls |

In the **Processes** tab:

| Key | Action |
| --- | --- |
| `/` | Focus the filter box (`Escape` clears it) |
| `c` `m` `p` `t` | Sort by CPU%, MEM%, PID, TIME+ |
| `i` | Reverse the sort order |
| `k` | Send `SIGTERM` (asks first) |
| `K` | Send `SIGKILL` (asks first) |
| `n` | Renice |

Clicking a column header also sorts by it; clicking again reverses.

Signalling a process you do not own requires running as root. sarplot reports
a permission error rather than failing silently.

## Enabling sar history

Historical metrics come from sysstat archives, normally written every 10
minutes to `/var/log/sysstat/saDD` (Debian/Ubuntu) or `/var/log/sa/saDD`
(RHEL/Alma/Fedora), where `DD` is the day of the month. sarplot searches both.

**RHEL / Alma / Rocky / Fedora**

```bash
sudo dnf install -y sysstat
sudo systemctl enable --now sysstat-collect.timer
```

**Debian / Ubuntu**

```bash
sudo apt install -y sysstat
sudo sed -i 's/ENABLED=.*/ENABLED="true"/' /etc/default/sysstat
sudo systemctl enable --now sysstat
```

Collection starts on the next interval, so a fresh install has no history for
a few minutes.

## Development

```bash
pip install -e ".[dev]"
pytest          # 149 tests
ruff check .
ruff format .
```

The tests in `tests/test_sar.py` run against fixtures in `tests/fixtures/`,
which are real `sadf -j` output captured from sysstat 12.7.7 rather than
hand-written approximations. Regenerate them against another sysstat version
with:

```bash
/usr/libexec/sysstat/sadc -S ALL 1 12 /tmp/sa_sample   # collect
sadf -j /tmp/sa_sample -- -u                           # inspect
```

`tests/test_app.py` drives the real Textual app through `run_test()`, so it
exercises mounting, tab switching, sorting, filtering and the confirmation
modals end to end.

## Requirements

- Python 3.10+
- Linux (process and system views rely on `/proc`; `sar` history is
  Linux-only)
- `sysstat` for the History tab only

## License

MIT - see [LICENSE](LICENSE).
