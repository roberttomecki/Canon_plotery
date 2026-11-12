# NAS version (Synology / Linux)

This version is for unattended work. The NAS scans the network once, collects counters from every plotter it finds, saves a full set of reports into a dated folder and exits. **It is not a server that runs all the time.** Each run is one scan.

## What it's made of

The `app/` folder has three files. They must sit together, even if you don't use email:

- `canon_collector.py` is the main program; it scans and saves the results;
- `canon_protocols.py` handles talking to the plotters over CHMP and CPCA;
- `canon_mailer.py` builds the TXT report and, if you want, sends it by email.

Python 3.10+ with the standard library is enough. A container isn't required; you can run the script directly, but then you must give the subnet (CIDR). **Don't replace the Python that ships with DSM.**

## Preparing the Synology, step by step

1. **Check what you have.** NAS model, DSM version, amount of RAM, whether Container Manager is available and which version. Don't guess this from the model name alone.
2. **Make a backup.** Export the DSM configuration and store it off the NAS. That's a backup of settings, not data, so also make sure important data has a current backup. If the collector was already installed, keep the previous version.
3. **Check the LAN network address.** Read the IP and netmask of the NAS's LAN interface. Don't assume it's /24. Also don't scan the internal container network (bridge), because the plotters are on the LAN.
4. **Prepare the folders.** In the chosen shared folder create `CanonCollector/apps` for the code and `CanonCollector/reports` for the results. Grant permissions (ACL) only to those who need them. No `chmod 777`.
5. **Upload the files.** Copy the three files from `app/` into `apps` on the NAS.

In my pilot the shared folder was `/volume1/WF_Serwis/CanonCollector`. The paths and addresses below are only examples. Don't install or update DSM packages without the administrator's approval.

## Creating the container in DSM

Use the official `python` image. In the pilot it was a previously downloaded `python:latest`. According to the image variable it was version 3.15.2, but I didn't check this separately with `python --version`.

Note: `latest` changes over time. If you want a reproducible deployment, write down the exact version and identifier (digest) of the image you tested, and don't update it automatically. A new image must also support your NAS's CPU architecture.

| Setting | Value |
| --- | --- |
| Network | bridge. You pass the LAN subnet as a parameter |
| Published ports | None. The container only makes outgoing connections |
| Code folder | `/volume1/SHARE/CanonCollector/apps` → `/app`, read-only |
| Reports folder | `/volume1/SHARE/CanonCollector/reports` → `/reports`, read/write |
| High privileges (privileged) | Off |
| Auto-restart | Off, because it's a one-off job |

Having "privileged" turned off doesn't by itself mean the container isn't running as root inside. For production, decide the UID/GID of the account the collector should run as, set the folder ACL for it and check that reports get written. In the pilot I didn't confirm, through the GUI, that it ran under an unprivileged UID. Don't mount `docker.sock`, system folders or the whole shared folder.

**First try: one plotter, CHMP only**

```text
python3 -B -u /app/canon_collector.py --chmp-only --subnet 192.0.2.10/32 --output /reports --workers 1 --timeout 5
```

**Once that works: full scan, CHMP and CPCA**

```text
python3 -B -u /app/canon_collector.py --subnet 192.0.2.0/24 --output /reports --workers 4 --timeout 3 --retries 1
```

Replace the example addresses with your own.

A few words about CPCA:

- By default the script tries CPCA with the whole iPF family, but anything other than the iPF785 is experimental.
- To stick to the tested model, add `--cpca-model iPF785`. You can repeat the option to list several models.
- `--chmp-only` turns CPCA off completely, even when CHMP fails.

The firewall and routing must allow outgoing traffic from the NAS to the plotters (TCP 80 and UDP 47545) and the replies. Nothing needs to be opened from the Internet side. Don't change firewall settings blindly.

## Alternative: Compose

`compose.yaml` is a template for those who prefer configuring from a file rather than the DSM wizard. Fill in the image and paths before using it. Don't run the wizard-created container and the Compose project for the same scan at the same time.

The template also hardens the container: it drops unneeded capabilities, blocks privilege escalation and makes the container's filesystem read-only. Only `/reports` stays writable. It's an extra option, not a recreated and tested copy of the pilot setup.

## All options

| Option | What it does (default) |
| --- | --- |
| `--subnet CIDR` | Subnet to scan. Can be given several times, each up to 1024 addresses; duplicate addresses are skipped |
| `--output PATH` | Where to save results: `~/canon-collector-data`. In the container set `/reports` |
| `--workers` | How many addresses to check at once: 4, range 1–24 |
| `--timeout` | How many seconds to wait for a reply: 5, allowed from above 0 up to 120 |
| `--retries` | How many times to retry a CPCA request: 2, range 0–10 |
| `--chmp-only` | Turns CPCA off. Inactive by default |
| `--cpca-model MODEL` | Which models to try over CPCA. By default all iPF, experimental except the iPF785 |
| `--email` | Emails the report after the scan. Off by default |

**Always give `--subnet` on Synology.** Without it the script tries to detect the network itself with `ip -j -4 addr show up`, but:

- DSM may not support the `-j` switch;
- inside the container the script will see the internal container network, not your LAN.

How do you find the subnet? `ip -4 addr show` gives the address with its prefix (e.g. `192.0.2.5/24`). You can compute the subnet from it in Python: `ipaddress.ip_interface('ADDRESS/PREFIX').network`. PowerShell's `Get-NetIPConfiguration` isn't used here. If plotters are in other VLANs, first make sure the NAS has a route to them, and list their ranges explicitly.

## Running it and the results

Start the next scan in **Container Manager → Container → (name) → Start**. Don't run two copies at the same time.

Each scan creates a new folder named with the UTC date and time, in the format `YYYYMMDDTHHMMSS_microsecondsZ/`:

```text
manifest.json                  # summary of the whole scan
Canon_<time>.txt               # combined, human-readable report
<IP>/result.json               # result for a single plotter
<IP>/communication.log         # communication log
<IP>/device_<version>.xml      # CHMP
<IP>/counter_<version>.xml     # CHMP
<IP>/status.bin                # CPCA
<IP>/status.txt                # CPCA
```

Not every plotter gets every file; it depends on the protocol and on what could be read. Addresses where no plotter was confirmed appear only in the manifest and get no folder of their own. Raw responses are kept for devices that were found. The combined report may contain partial data, so look at the statuses and errors, not just the numbers.

Exit codes:

- `0`: at least one successful read and no partial ones. Note: this doesn't mean every plotter was found.
- `1`: there were partial results, nothing succeeded, or the report or email sending failed.
- `2`: invalid parameters.

An unhandled exception can also stop the program, so keep the logs.

**How long does it take?** In the pilot a /24 scan took about 13 minutes. Most of the time is spent waiting for empty addresses to time out; reading the plotters themselves is quick. That's an observation, not a limit. At the end, check the log for `Checked 254/254`, the summary, and that the TXT file was written.

## Scheduling and notifications

The repository **doesn't turn on any schedule**. In the pilot I ran the scans by hand. Only set up automation once you know what time it should run, under which account, and how the container will be started. In DSM Task Scheduler:

- use full paths;
- make sure two scans can't run at once;
- don't use the container's auto-restart as a substitute for a schedule.

Also think about cleanup, because old reports aren't deleted automatically.

**The "Container stopped unexpectedly" alert.** The container stops after the scan, and that's intended. DSM may still report it as a problem even though the report is complete. Before you worry, check the log and the exit code.

If you deliberately want to silence this alert, create your own notification rule that covers all events **except this one**, and assign it to the email recipient profile instead of the built-in "All" rule, which can't be edited. Keep two things in mind:

- this will also silence real failures of other containers;
- push notifications through your Synology account may still come through.

Don't turn off all NAS notifications.

## Emailing the report (optional)

By default reports stay on the NAS. If you want to receive them by email, set these before using `--email`:

```text
CANON_SMTP_SENDER=collector@example.com
CANON_SMTP_RECIPIENT=reports@example.com
CANON_SMTP_HOST=smtp.example.com
CANON_SMTP_PASSWORD_FILE=/run/secrets/canon-smtp-password
```

The connection uses SMTP_SSL on port 465 and verifies the server certificate. Don't turn that verification off.

**Password:**

- keep it in a separate file, outside the repository and outside the reports folder;
- set permissions to 600 or an appropriate ACL;
- mount only that one file into the container, read-only;
- never put the password in a command, an image or `compose.yaml`.

If you don't set `CANON_SMTP_PASSWORD_FILE`, the script looks for the password in `~/.canon-smtp-password`, so the account's home folder (HOME) must be set correctly.

Mail goes from the sender account to **one** recipient. I didn't test sending email in the NAS pilot. So first look over the generated TXT, make sure the recipient is right, and only then do a test send. DSM notifications are a separate matter, unrelated to the collector's email.

## Updating and rolling back

1. Make sure no scan is running.
2. Keep the current three files, the container configuration and the image identifier.
3. Replace all three modules at once, not one by one.
4. Test on a single IP address.

If something doesn't work, put the old files and configuration back. You don't need to restore all of DSM for that. Don't delete reports, and don't remove the image if other applications use it.

Remember that a new version on GitHub doesn't reach the NAS by itself. The files have to be replaced by hand.
