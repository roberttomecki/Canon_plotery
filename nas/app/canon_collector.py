"""Discover Canon CHMP and iPF CPCA devices and retain complete responses."""
import argparse
import concurrent.futures
import datetime as dt
import ipaddress
import json
import io
from pathlib import Path
import subprocess
import smtplib
import xml.etree.ElementTree as ET

import canon_protocols as protocol
import canon_mailer


def local_networks():
    result = subprocess.run(['ip', '-j', '-4', 'addr', 'show', 'up'],
                            capture_output=True, text=True, check=True, timeout=10)
    networks = set()
    for interface in json.loads(result.stdout):
        if interface.get('ifname') == 'lo':
            continue
        for address in interface.get('addr_info', []):
            if address.get('family') == 'inet' and address.get('scope') == 'global':
                networks.add(str(ipaddress.ip_interface(
                    f"{address['local']}/{address['prefixlen']}").network))
    return sorted(networks)


def collect_one(ip, folder, timeout, retries, cpca_models=('*',), chmp_only=False):
    target = folder / ip
    artifacts = {}
    log = io.StringIO()
    result = {'ip': ip, 'status': 'not_confirmed', 'errors': [],
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        # Keep every CHMP response, including unknown fields and error XML.
        # TM-610M rejects the older versions with HTTP 406.
        for version in ('1.3.0', '1.0.0', '1.4.0'):
            try:
                data = protocol.query(ip, 80, version, timeout,
                                      'GetCapability', 'device', log)
                artifacts[f'device_{version}.xml'] = data
                device = ET.fromstring(data)
                if (protocol.field(device, 'response') != 'OK' or
                        protocol.field(device, 'manufacturer').lower() != 'canon'):
                    raise ValueError('Identification does not confirm Canon CHMP')
                result.update(protocol='CHMP', model=protocol.field(device, 'model'),
                              serial=protocol.field(device, 'product_serialnumber'),
                              request_version=version, status='partial')
                # Probe counter directly: a missing service advertisement must
                # not prevent collection from an otherwise identified Canon.
                data = protocol.query(ip, 80, version, timeout,
                                      'GetStatus', 'counter', log)
                artifacts[f'counter_{version}.xml'] = data
                if protocol.field(ET.fromstring(data), 'response') != 'OK':
                    raise ValueError('Counter response is not OK')
                result['status'] = 'collected'
                return result
            except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
                result['errors'].append(f'CHMP {version}: {exc}')
        if chmp_only:
            return result
        try:
            # Unlike the original scanner, use retries and a full timeout
            # for initialization. No HTTP port precondition for UDP devices.
            with protocol.CPCAClient(ip, 47545, timeout, retries, log) as client:
                model = client.initialize(allowed_models=cpca_models)
                result.update(protocol='CPCA', model=model, status='partial')
                result['compatibility'] = ('tested' if model == 'iPF785'
                                           else 'experimental; validate report against printer')
                data = client.read_status()
            artifacts['status.bin'] = data
            try:
                text = data.decode('cp1250')
                artifacts['status.txt'] = text.encode('utf-8-sig')
            except UnicodeError as exc:
                result['errors'].append(f'Decoding cp1250: {exc}; original bytes retained')
            result['status'] = 'collected'
        except (OSError, ValueError, RuntimeError, protocol.ProtocolError) as exc:
            result['errors'].append(f'CPCA: {exc}')
        return result
    finally:
        result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        # Unconfirmed addresses remain in the scan manifest, without directories.
        if result['status'] != 'not_confirmed':
            target.mkdir()
            for name, data in artifacts.items():
                (target / name).write_bytes(data)
            (target / 'communication.log').write_text(log.getvalue(), encoding='utf-8')
            (target / 'result.json').write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subnet', action='append', help='IPv4 CIDR; repeat for multiple networks')
    parser.add_argument('--output', type=Path, default=Path.home() / 'canon-collector-data')
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--email', action='store_true', help='Send the completed scan as a TXT attachment')
    parser.add_argument('--chmp-only', action='store_true',
                        help='Use CHMP only; never initialize or query CPCA')
    parser.add_argument('--cpca-model', action='append',
                        help='Allowed CPCA model; repeat for a list. Default: all iPF models (experimental except iPF785)')
    args = parser.parse_args()
    if not 0 < args.timeout <= 120 or not 0 <= args.retries <= 10 or not 1 <= args.workers <= 24:
        parser.error('Invalid timeout, retries or workers')
    try:
        networks = [ipaddress.ip_network(value, strict=False)
                    for value in (args.subnet or local_networks())]
        if not networks:
            raise ValueError('No IPv4 networks found; specify --subnet')
        if any(net.version != 4 or net.num_addresses > 1024 for net in networks):
            raise ValueError('Each subnet must be IPv4 with at most 1024 addresses')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    addresses = sorted({str(ip) for net in networks for ip in net.hosts()},
                       key=ipaddress.ip_address)
    folder = args.output / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder.mkdir(parents=True)
    print(f'Networks: {", ".join(map(str, networks))}; addresses: {len(addresses)}', flush=True)
    print(f'Output: {folder}', flush=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(collect_one, ip, folder, args.timeout, args.retries,
                            args.cpca_model or ('*',), args.chmp_only): ip
                for ip in addresses}
        for index, job in enumerate(concurrent.futures.as_completed(jobs), 1):
            result = job.result()
            results.append(result)
            if result['status'] != 'not_confirmed':
                print(f"{result['ip']}: {result.get('model')} / {result.get('protocol')} / {result['status']}", flush=True)
            if index % 16 == 0 or index == len(addresses):
                print(f'Checked {index}/{len(addresses)}', flush=True)
    manifest = {'networks': list(map(str, networks)),
                'devices': sorted(results, key=lambda r: ipaddress.ip_address(r['ip']))}
    manifest_path = folder / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    count = sum(r['status'] == 'collected' for r in results)
    partial = sum(r['status'] == 'partial' for r in results)
    print(f'Collected: {count}; partial: {partial}; manifest: {manifest_path}')
    try:
        report = canon_mailer.save_report(manifest_path)
        print(f'Raport TXT: {report}')
        if args.email:
            canon_mailer.send_report(report, canon_mailer.read_password())
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        print(f'Błąd raportu lub wysyłki: {exc}')
        return 1
    return 1 if partial or not count else 0


if __name__ == '__main__':
    raise SystemExit(main())
