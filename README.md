# Canon Plotters

Tools for reading counters from Canon large-format plotters over the local network. Instead of walking up to each machine and writing down the counters from the panel, you run a script. It asks the plotters for their model, serial number, paper and ink usage, and saves everything in a report.

The scripts **only read**. They never send print jobs and never change plotter settings.

## Which version should I use?

There are two versions, each for a different job:

| Version | When to use it | How to run it | What you get |
| --- | --- | --- | --- |
| [Desktop](desktop/README.md) | You want to quickly check one or a few plotters from your Windows PC (Linux works too, but you have to give an IP address or subnet) | `Canon_plotery.cmd` or Python directly | TXT and HTML report, log, plus a raw BIN file for CPCA |
| [NAS](nas/README.md) | You want the NAS to scan the whole network on its own and produce one combined report | Python container or command line | JSON manifest, TXT report, raw XML/BIN responses and logs |

All you need is Python 3.10 or newer. Nothing has to be installed with pip.

Also in the repository:

- `Canon_CHMP.py` in the root folder is the older, standalone CHMP reader. It's kept for reference.
- `desktop/Canon_plotery.cmd` is a new Windows launcher written from scratch. It is not a recovered copy of the old `Canon_CHMP.cmd`.
- `apk/` holds the existing releases of the "Canon Liczniki" Android app (1.1–1.4), unchanged.

## How it talks to the plotters

Canon plotters answer one of two protocols:

- **CHMP (TCP, port 80)**: newer plotters. The script sends a POST request (GetCapability/device and GetStatus/counter), then picks up the response with a GET.
- **CPCA (UDP, port 47545)**: older iPF models. The script opens a session, asks for the model and downloads a text status report. Confirmed working with the **iPF785**. Other iPF models are experimental in the NAS version.

Both versions try several CHMP versions, but not in exactly the same way:

- NAS tries 1.3.0, 1.0.0 and 1.4.0, in that order.
- Desktop in auto mode tries 1.3.0 and 1.0.0.

### What has been tested in practice

On 12 Nov 2026 I ran a pilot on a Synology **DS223j** NAS (Realtek RTD1619B, 1 GB RAM, DSM **7.4.1-90080 Update 1**, Container Manager **24.0.2-1706**). Result of a full /24 network scan:

- 254 addresses checked;
- two successful reads over CHMP: **TX-3000** and **TM-610M**;
- zero partial reads;
- the TX-3000 report had OK status for both identification and counters.

To be fair, this doesn't prove that every model is supported. CPCA on the NAS hasn't been tested yet either.

## How to read the results

A few things that are easy to get wrong:

- **A4 equivalent and A4 area** are two separate fields, but the second one is just a conversion of the first (A4 × 0.06237 m²). Don't treat it as an independent area counter.
- **The `amount` and `area_square` units** may be raw, exactly as the plotter reported them. Don't assume they're ml or m². If the code has a model-specific conversion, compare it against the report printed by the plotter itself.
- **No response or a missing field is not zero.** It only means the value couldn't be read.
- **A scan won't find everything.** It detects devices that answer CHMP or CPCA. A plotter that's asleep, switched off, or hidden behind a firewall or in another VLAN may not show up.

If the counters will be used for billing, first compare the model, serial number, counters and units with what the machine itself shows. There is no automatic import into Princity.

## Privacy

Reports and logs contain serial numbers, IP addresses and usage data. **Don't upload them to GitHub**, and certainly not passwords.

All examples use the "documentation" network 192.0.2.0/24, which doesn't really exist. Replace it with your own address range, one you're allowed to scan.

The only difference between the NAS version in this repository and the pilot version is the mail configuration. Email addresses now come from environment variables, and sending mail is optional.

Deploying on the NAS doesn't update DSM, doesn't install a system Python and doesn't need a privileged container.

## Quick test on your own computer

```sh
python -B -m unittest discover -s tests -v
python -B desktop/Canon_plotery.py --help
python -B nas/app/canon_collector.py --help
```

The tests run on synthetic responses, so they don't touch the network or a mail server. They check the code, but they're no substitute for a trial on real plotters. Installation and maintenance details are in each version's README.
