# Desktop version

This version is for quick, on-the-spot reads: start it, pick a plotter from the list, and a moment later you have a report. It works best on Windows.

## What you need

- **Python 3.10 or newer.** On Windows the `py` command must be available; it's installed along with Python.
- **Windows PowerShell**, if you want the script to detect your network automatically.
- Two files, `Canon_plotery.py` and `Canon_plotery.cmd`, in one folder you can write to. Nothing else needs to be installed.

The `.cmd` file is a convenient shortcut. It starts Python, passes the parameters along and waits for a key press at the end so the window doesn't close by itself. If you want to put the read into Task Scheduler, call Python directly, without the `.cmd`.

**Linux:** it works, but automatic network detection uses PowerShell. So on Linux always give `--ip` or `--subnet`.

## How to run it

The easiest way is to double-click `Canon_plotery.cmd`. The script looks for plotters and shows a list. You can then type:

- plotter numbers, separated by commas;
- `A` to read all of them;
- `R` to enter an address by hand;
- `Q` to quit.

If you know the plotter's address, you can skip the search:

```bat
Canon_plotery.cmd
py -3 Canon_plotery.py --ip 192.0.2.10
py -3 Canon_plotery.py --ip 192.0.2.10 192.0.2.11 --protocol chmp
py -3 Canon_plotery.py --subnet 192.0.2.0/24
py -3 Canon_plotery.py --subnet 192.0.2.0/24 --scan-only
py -3 Canon_plotery.py --ip 192.0.2.20 --protocol cpca
```

On Linux use `python3` instead of `py -3`. The `--scan-only` option just shows what's on the network, without reading counters.

## All options

| Option | What it does (default) |
| --- | --- |
| `--ip IP [IP ...]` | One or more IPv4 addresses. Don't combine with `--subnet` |
| `--subnet CIDR` | One IPv4 subnet, up to 1024 addresses |
| `--scan-only` | Discovery only, no reading. Don't combine with `--ip` |
| `--protocol auto/chmp/cpca` | `auto` tries CHMP first, then CPCA |
| `--version auto/1.3.0/1.0.0` | CHMP request version. `auto` tries both |
| `--chmp-port` / `--cpca-port` | 80 (TCP) / 47545 (UDP) |
| `--timeout` | How many seconds to wait for a reply: 10, allowed from above 0 up to 120 |
| `--retries` | How many times to retry a UDP request: 2, range 0–10 |
| `--encoding` | Text encoding of CPCA responses: cp1250 |
| `--output` | Where to save reports, by default `raporty_Canon` next to the script |

This version supports only the **iPF785** over CPCA. It also lacks some features of the NAS version, such as CHMP 1.4.0 and experimental support for other iPF models.

## What you get

For each plotter you get:

- a **TXT** and **HTML** report with the values read;
- a **log** of the whole communication;
- for CPCA, also the raw **BIN** response.

File names include the date, time and device. If something goes wrong, a separate error file may be created. So open the files and check what's in them; a reports folder alone doesn't mean the read succeeded.

Exit codes come in handy if you run the script from another program:

- `0`: no errors. You also get this code if you cancelled the selection or `--scan-only` found nothing.
- `1`: read or execution error.
- `2`: invalid parameters.
- `130`: interrupted by the user.

This version doesn't send email. If you need a combined report or a scan without your involvement, use the [NAS version](../nas/README.md).

## When something doesn't work

**Start with a single plotter.** Run `--ip <address> --protocol chmp` and compare the result with what the machine's panel shows. Only scan the whole network once that matches.

If CHMP doesn't answer, it doesn't mean something is broken. The plotter may use CPCA (UDP), or a firewall may be blocking the traffic. A plotter that only speaks UDP doesn't need port 80 open.

Don't automatically convert the results to ml or m². The [main README](../README.md#how-to-read-the-results) explains why.

**Updating:** before replacing the scripts, keep the old versions and your existing reports. If the new version causes trouble, simply put the old files back.
