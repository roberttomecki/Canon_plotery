"""Send a summary of a completed Canon Collector scan."""

import argparse
import os
from email.message import EmailMessage
from getpass import getpass
import json
from pathlib import Path
import smtplib
import ssl
import xml.etree.ElementTree as ET

from canon_protocols import report_rows


SENDER = os.environ.get("CANON_SMTP_SENDER", "")
RECIPIENT = os.environ.get("CANON_SMTP_RECIPIENT", "")
SMTP_HOST = os.environ.get("CANON_SMTP_HOST", "")
SMTP_PORT = 465
PASSWORD_FILE = Path(os.environ.get("CANON_SMTP_PASSWORD_FILE", str(Path.home() / ".canon-smtp-password")))


def build_report(manifest_path):
    scan = json.loads(manifest_path.read_text(encoding="utf-8"))
    devices = scan["devices"]
    collected = sum(device["status"] == "collected" for device in devices)
    partial = sum(device["status"] == "partial" for device in devices)
    lines = [
        f"Skan UTC: {manifest_path.parent.name}",
        f"Podsieci: {', '.join(scan['networks'])}",
        f"Sprawdzone adresy: {len(devices)}",
        f"Udane odczyty: {collected}. Częściowe odczyty: {partial}.",
        "",
    ]
    for device in devices:
        if device["status"] == "not_confirmed":
            continue
        status = "odczyt udany" if device["status"] == "collected" else "odczyt częściowy"
        lines.append(
            f"{device['ip']} | {device.get('model') or '?'} | "
            f"{device.get('protocol') or '?'} | {status}"
        )
    return "\n".join(lines)


def format_chmp(target, device):
    version = device.get("request_version")
    roots = {}
    issues = []
    for kind in ("device", "counter"):
        path = target / f"{kind}_{version}.xml"
        if path.is_file():
            try:
                roots[kind] = ET.parse(path).getroot()
            except ET.ParseError as exc:
                issues.append(f"{path.name}: {exc}")
    try:
        rows = report_rows(roots.get("counter"), roots.get("device"),
                           device["ip"], device.get("started_at", ""), [])
        lines = [f"{label}: {value}" for label, value in rows if value]
    except (ValueError, OverflowError) as exc:
        lines = []
        issues.append(str(exc))
    if issues:
        lines.append("Błąd formatowania CHMP: " + ", ".join(issues))
        for path in sorted(target.glob("*.xml")):
            lines.append(f"--- {path.name} ---\n" + path.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n".join(lines)


def save_report(manifest_path):
    scan = json.loads(manifest_path.read_text(encoding="utf-8"))
    folder = manifest_path.parent
    sections = [build_report(manifest_path)]
    for device in scan["devices"]:
        if device["status"] == "not_confirmed":
            continue
        ip = device["ip"]
        target = folder / ip
        sections.append(f"=== {ip} | {device.get('model') or '?'} ===")
        if device.get("protocol") == "CHMP":
            sections.append(format_chmp(target, device))
        status = target / "status.txt"
        binary = target / "status.bin"
        if status.is_file():
            sections.append(status.read_text(encoding="utf-8-sig"))
        elif binary.is_file():
            sections.append(binary.read_bytes().decode("cp1250", errors="replace"))
        if device["status"] == "partial":
            sections.extend(device.get("errors", []))
    report = folder / f"Canon_{folder.name}.txt"
    report.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return report


def read_password():
    with PASSWORD_FILE.open(encoding="utf-8") as password_file:
        if PASSWORD_FILE.stat().st_mode & 0o077:
            raise ValueError(f"Ustaw uprawnienia 600 dla {PASSWORD_FILE}")
        password = password_file.read().rstrip("\r\n")
    if not password:
        raise ValueError(f"Brak hasła w {PASSWORD_FILE}")
    return password


def send_report(report, password):
    if not all((SENDER, RECIPIENT, SMTP_HOST)):
        raise ValueError("Set CANON_SMTP_SENDER, CANON_SMTP_RECIPIENT and CANON_SMTP_HOST")
    message = EmailMessage()
    message["From"] = SENDER
    message["To"] = RECIPIENT
    message["Subject"] = f"Canon Collector – {report.parent.name}"
    message.set_content("W załączniku znajduje się raport z odczytu ploterów.")
    message.add_attachment(report.read_text(encoding="utf-8"), filename=report.name)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20,
                          context=ssl.create_default_context()) as smtp:
        smtp.login(SENDER, password)
        smtp.send_message(message)
    print(f"Serwer SMTP przyjął raport dla {RECIPIENT}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "canon-collector-data")
    parser.add_argument("--preview", action="store_true", help="Print the report without sending")
    parser.add_argument("--manifest", type=Path, help="Send the TXT report for this specific scan")
    args = parser.parse_args()
    manifest = args.manifest or max(args.data_dir.glob("*/manifest.json"), default=None)
    if manifest is None:
        parser.exit(1, f"Brak zakończonych skanów w {args.data_dir}\n")
    try:
        if args.manifest:
            report = save_report(args.manifest)
            if args.preview:
                print(report.read_text(encoding="utf-8"))
            else:
                send_report(report, read_password())
            return
        body = build_report(manifest)
        if args.preview:
            print(body)
            return
        message = EmailMessage()
        message["From"] = SENDER
        message["To"] = RECIPIENT
        message["Subject"] = "Canon Collector – wynik skanowania"
        message.set_content(body)
        password = getpass(f"Hasło SMTP dla {SENDER}: ")
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20,
                              context=ssl.create_default_context()) as smtp:
            smtp.login(SENDER, password)
            smtp.send_message(message)
    except (OSError, ValueError, KeyError, smtplib.SMTPException) as exc:
        parser.exit(1, f"Błąd raportu lub SMTP: {exc}\n")
    print(f"Serwer SMTP przyjął raport dla {RECIPIENT}.")


if __name__ == "__main__":
    main()
