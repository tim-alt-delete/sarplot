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
- **Logs** - a `/var/log` file explorer beside a tailing log pane, with
  filtering or highlight-and-jump search, optional regex, and live following
  that survives log rotation.
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
        [-L PATH] [-D DIR] [--log-lines N]

  -f, --file PATH       sysstat archive to open, e.g. /var/log/sysstat/sa30
                        (default: the most recent archive found)
  -s, --start HH:MM:SS  start of the historical time window
  -e, --end HH:MM:SS    end of the historical time window
  -r, --refresh SECONDS process list refresh interval (default: 2.0)
  -t, --tab TAB         processes | live | history | logs | system
  -L, --log-file PATH   log file to open (default: the system log)
  -D, --log-dir DIR     directory the log explorer is rooted at
                        (default: /var/log)
  --log-lines N         log lines retained in memory (default: 5000)
  -V, --version         print the version and exit
```

Open yesterday's CPU history for the morning:

```bash
sarplot --tab history --file /var/log/sysstat/sa29 --start 08:00 --end 12:00
```

Tail the auth log:

```bash
sarplot --tab logs --log-file /var/log/auth.log
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

In the **Logs** tab:

| Key | Action |
| --- | --- |
| `/` | Focus the search box (`Escape` clears it) |
| `f` | Toggle following (auto-scroll on new lines) |
| `h` | Switch between filter and highlight modes |
| `r` | Toggle regular expressions |
| `a` | Toggle case sensitivity |
| `n` / `N` | Next / previous match (highlight mode) |
| `g` / `G` | Jump to the top / bottom |
| `Ctrl+L` | Clear the pane |

Search filters by default, hiding lines that do not match. Highlight mode
keeps every line and lets you step between matches instead. Queries are
literal substrings unless the regex toggle is on, so `app[42]` matches what
you would expect; an invalid pattern is reported in the status line and the
previous results are kept.

Following polls the file twice a second and handles log rotation, both the
rename-and-recreate kind and in-place truncation. Rotated `.gz`, `.xz` and
`.bz2` archives can be opened and read, though there is nothing to follow.

Most files under `/var/log` are readable only by root; the explorer hides
what it cannot open, along with binary files such as `wtmp` and `lastlog`.

## Planned

**systemd journal support.** On hosts that log only to the journal - the
default for current Debian, Ubuntu and Fedora - there is no `/var/log/syslog`
or `/var/log/messages` to tail, and the Logs tab will say so. Reading the
journal through `journalctl` is scaffolded in
`sarplot/collectors/journal.py` (detection, priority mapping and `-o json`
parsing are implemented and tested) but the streaming half is not yet built.
The remaining work is listed in that module's docstring.

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
pytest          # 287 tests
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
exercises mounting, tab switching, sorting, filtering, log tailing and the
confirmation modals end to end.

The journal fixtures in `tests/fixtures/journal/` are **synthetic**, written
from the documented systemd field schema rather than captured from a live
system. Verify them against a real `journalctl` before relying on them.

## Requirements

- Python 3.10+
- Linux (process and system views rely on `/proc`; `sar` history is
  Linux-only)
- `sysstat` for the History tab only
- Root, to read most files under `/var/log` in the Logs tab

## License

MIT - see [LICENSE](LICENSE).
