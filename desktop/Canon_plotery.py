"""Canon: odczyt nowych ploterów przez CHMP i iPF785 przez CPCA.
Python 3.10+, wyłącznie biblioteki standardowe.
    py -3 Canon_plotery.py --ip 192.168.88.90
    py -3 Canon_plotery.py --subnet 192.168.88.0/24
"""
import argparse
import codecs
import concurrent.futures
import datetime
import html
import io
import ipaddress
import json
from pathlib import Path
import pathlib
import re
import socket
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


NS = {'ivec': 'http://www.canon.com/ns/cmd/2008/07/common/'}


def headers(reader):
    status = reader.readline(65537)
    if not status or len(status) > 65536:
        raise RuntimeError('Brak poprawnej linii odpowiedzi HTTP')
    lines = [status]
    fields = {}
    for _ in range(200):
        line = reader.readline(65537)
        if not line or len(line) > 65536:
            raise RuntimeError('Niekompletne naglowki HTTP')
        lines.append(line)
        if line in (b'\r\n', b'\n'):
            break
        key, sep, value = line.partition(b':')
        if not sep:
            raise RuntimeError('Niepoprawny naglowek HTTP')
        fields[key.decode('ascii').lower()] = value.decode('latin1').strip()
    else:
        raise RuntimeError('Zbyt wiele naglowkow HTTP')
    tokens = status.split()
    if len(tokens) < 2 or not tokens[0].startswith(b'HTTP/'):
        raise RuntimeError('Niepoprawna linia statusu HTTP')
    code = int(tokens[1])
    return code, fields, b''.join(lines)


def exact(reader, count):
    if not 0 <= count <= 32 * 1024 * 1024:
        raise RuntimeError('Nieprawidlowa lub zbyt duza dlugosc danych')
    data = reader.read(count)
    if len(data) != count:
        raise RuntimeError('Polaczenie zamkniete przed odebraniem danych')
    return data


def body(reader, fields, acknowledgement=False):
    if 'chunked' in fields.get('transfer-encoding', '').lower():
        parts = []
        total = 0
        while True:
            line = reader.readline(1024)
            size = int(line.strip().split(b';', 1)[0], 16)
            if size == 0:
                for _ in range(200):
                    trailer = reader.readline(65537)
                    if trailer in (b'\r\n', b'\n'):
                        return b''.join(parts)
                    if not trailer:
                        raise RuntimeError('Niekompletne zakonczenie chunked')
                raise RuntimeError('Zbyt wiele trailerow HTTP')
            total += size
            if total > 32 * 1024 * 1024:
                raise RuntimeError('Odpowiedz przekracza 32 MB')
            parts.append(exact(reader, size))
            if exact(reader, 2) != b'\r\n':
                raise RuntimeError('Niepoprawny separator chunked')
    if 'content-length' in fields:
        return exact(reader, int(fields['content-length']))
    if acknowledgement:
        # Canon w przechwyceniu potwierdza POST samymi naglowkami,
        # bez Content-Length, po czym czeka na GET.
        return b''
    raise RuntimeError('Wynik GET nie ma Content-Length ani Transfer-Encoding: chunked')


def request(method, ip, port, version, payload=b''):
    host = f'[{ip}]' if ':' in ip else ip
    if port != 80:
        host += f':{port}'
    lines = [f'{method} /canon/ij/command2/port1 HTTP/1.1',
             f'Host: {host}', 'Connection: Keep-Alive']
    if method == 'POST':
        lines += ['Content-Type: application/octet-stream',
                  f'Content-Length: {len(payload)}']
    lines += [f'X-CHMP-Version: {version}']
    if method == 'POST':
        lines += ['X-CHMP-Timeout: 10']
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('ascii') + payload


def query(ip, port, version, timeout, operation, service, log):
    payload = ('<?xml version="1.0" encoding="utf-8"?>\r\n'
        '<cmd xmlns:ivec="http://www.canon.com/ns/cmd/2008/07/common/" '
        'xmlns:vcn="http://www.canon.com/ns/cmd/2008/07/canon/">'
        f'<ivec:contents><ivec:operation>{operation}</ivec:operation>'
        f'<ivec:param_set servicetype="{service}"></ivec:param_set>'
        '</ivec:contents></cmd>').encode('utf-8')
    log.write(f'\n=== {operation}, servicetype={service} ===\n')
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        with sock.makefile('rb') as reader:
            packet = request('POST', ip, port, version, payload)
            log.write('ZADANIE POST:\n' + packet.decode('utf-8') + '\n')
            log.flush()
            sock.sendall(packet)
            code, fields, raw = headers(reader)
            log.write('POTWIERDZENIE POST:\n' + raw.decode('latin1'))
            while 100 <= code < 200:
                code, fields, raw = headers(reader)
                log.write(raw.decode('latin1'))
            post_body = body(reader, fields, acknowledgement=True)
            log.write(post_body.decode('utf-8', errors='replace') + '\n')
            log.flush()
            if code != 200:
                raise RuntimeError(f'POST zakonczony HTTP {code}')
            # Jezeli inny firmware zwraca XML od razu, zachowaj go.
            if post_body.strip().startswith(b'<?xml') or post_body.strip().startswith(b'<cmd'):
                return post_body
            packet = request('GET', ip, port, version)
            log.write('ZADANIE GET:\n' + packet.decode('ascii'))
            log.flush()
            sock.sendall(packet)
            code, fields, raw = headers(reader)
            log.write('ODPOWIEDZ GET:\n' + raw.decode('latin1'))
            while 100 <= code < 200:
                code, fields, raw = headers(reader)
                log.write(raw.decode('latin1'))
            data = body(reader, fields)
            log.write('BODY PO USUNIECIU RAMKOWANIA HTTP:\n')
            log.write(data.decode('utf-8', errors='replace') + '\n')
            log.flush()
            if code != 200:
                raise RuntimeError(f'GET zakonczony HTTP {code}')
            return data


def report_rows(counter, device, ip, timestamp, errors):
    rows = [('Data odczytu', timestamp), ('Adres plotera', ip)]
    def value(root, name):
        return root.findtext('.//ivec:' + name, default='', namespaces=NS) if root is not None else ''
    model = value(device, 'model')
    for tag, label in [('manufacturer', 'Producent'), ('model', 'Model'),
                       ('product_serialnumber', 'Numer seryjny produktu'),
                       ('serialnumber', 'Identyfikator serialnumber'), ('firmver', 'Firmware'),
                       ('service', 'Dostępne usługi'), ('support_data_format', 'Formaty danych'),
                       ('box_num', 'Liczba skrzynek HDD')]:
        if value(device, tag):
            rows.append((label, value(device, tag)))
    for root, label in [(counter, 'Status odczytu liczników'), (device, 'Status identyfikacji')]:
        rows.append((label, value(root, 'response') or 'Brak odpowiedzi'))
    if counter is not None and value(counter, 'response') == 'OK':
        count = value(counter, 'total_sheets_a4')
        if count:
            rows += [('Papier — ekwiwalent A4', f'{int(count):,}'.replace(',', ' ')),
                     ('Papier — powierzchnia z A4', f'{int(count) * 0.06237:.5f}'.replace('.', ',') + ' m²')]
        names = {'GY': 'szary', 'PM': 'jasna magenta', 'M': 'magenta',
                 'MBK': 'czarny matowy', 'PBK': 'czarny fotograficzny',
                 'PC': 'jasny cyjan', 'Y': 'żółty', 'C': 'cyjan'}
        inks = counter.findall('.//ivec:ink_accumulated_info/ivec:item', NS)
        unit = ' ml' if model == 'PRO-4000S' else ' (amount, surowe)'
        total = 0
        for item in inks:
            color, amount = value(item, 'color'), int(value(item, 'amount'))
            total += amount
            rows.append((f'Atrament {color} — {names.get(color, color)}', f'{amount:,}'.replace(',', ' ') + unit))
        if inks:
            rows.append(('Suma odczytanych liczników atramentu', f'{total:,}'.replace(',', ' ') + unit))
        for item in counter.findall('.//ivec:medium_accumulated_info/ivec:item', NS):
            prefix = 'Medium ' + str(item.get('number', '?'))
            rows += [(prefix + ' — typ', value(item, 'papertype')),
                     (prefix + ' — identyfikator', value(item, 'custom_papertype')),
                     (prefix + ' — area_square (surowe)', value(item, 'area_square'))]
    rows.extend(('Błąd ' + operation, str(error)) for operation, error in errors)
    return rows


REPORT_NOTE = ('Dla PRO-4000S jednostkę ml potwierdzono porównaniem z wydrukiem. '
               'CHMP zwraca całkowite wartości atramentu; ich suma nie zastępuje dokładnego INK-TTL. '
               'Dla innych modeli amount pozostaje wartością surową. '
               'Powierzchnia całkowita: A4 × 0,06237 m². Jednostka area_square i nazwy mediów '
               'nie zostały potwierdzone. Brak danych nie oznacza zerowego zużycia.')


def local_networks():
    command = ("Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | "
               "ForEach-Object { $_.IPv4Address | Select-Object IPAddress,PrefixLength } | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, timeout=20, check=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    data = json.loads(result.stdout.strip() or '[]')
    if isinstance(data, dict):
        data = [data]
    networks = set()
    for item in data:
        interface = ipaddress.ip_interface(f"{item['IPAddress']}/{item['PrefixLength']}")
        if interface.version == 4 and interface.ip.is_private and not interface.ip.is_loopback:
            networks.add(interface.network)
    return sorted(networks, key=lambda n: int(n.network_address))


HEADER = struct.Struct('!10H')


MODEL_REQUEST = bytes.fromhex('01ec000000010000006500010420')


STATUS_REQUEST = bytes.fromhex('01ec00000001000002590001011a')


REPORT_SELECTOR = bytes.fromhex('00000065000400090000')


REPORT_PREFIX = bytes.fromhex('0000000065000400090019010a')


MAX_BLOCKS = 2048


MAX_REPORT = 32 * 1024 * 1024


PAGE_DELAY = 0.1


class ProtocolError(Exception):
    pass


def build_packet(operation, sequence, body=b''):
    return HEADER.pack(0xCDCA, 0x1004, operation, sequence, len(body), 0, 0, 0, 0, 0) + body


def parse_packet(packet):
    if len(packet) < HEADER.size:
        raise ProtocolError('Odpowiedź CPCA jest krótsza niż nagłówek 20 B.')
    magic, kind, operation, sequence, length, *tail = HEADER.unpack_from(packet)
    if magic != 0xCDCA or kind != 0x1001:
        raise ProtocolError('Nieprawidłowa sygnatura lub typ odpowiedzi CPCA.')
    if length != len(packet) - HEADER.size:
        raise ProtocolError('Długość odpowiedzi CPCA nie zgadza się z nagłówkiem.')
    return operation, sequence, tail[-1], packet[HEADER.size:]


def parse_model(body):
    prefix = bytes.fromhex('00010000006500010420')
    if len(body) < 15 or body[:10] != prefix:
        raise ProtocolError('Nie rozpoznano odpowiedzi z modelem plotera.')
    value = body[12:]
    if int.from_bytes(body[10:12], 'big') != len(value):
        raise ProtocolError('Nieprawidłowa długość właściwości modelu.')
    if value[:2] != b'\x00\x03' or value[2] != len(value) - 3:
        raise ProtocolError('Nie rozpoznano formatu nazwy modelu.')
    try:
        return value[3:].decode('ascii')
    except UnicodeError as exc:
        raise ProtocolError('Nie rozpoznano kodowania nazwy modelu.') from exc


def parse_block(flags, body, expected_line):
    if len(body) < 19 or body[2:15] != REPORT_PREFIX:
        raise ProtocolError('Nie rozpoznano bloku Status print.')
    cursor = int.from_bytes(body[:2], 'big')
    first, count = struct.unpack_from('!HH', body, 15)
    if flags not in (1, 4) or (flags == 1) != (cursor == 0):
        raise ProtocolError('Nieprawidłowy znacznik końca lub kursor raportu.')
    if first != expected_line:
        raise ProtocolError(f'Nieciągły raport: oczekiwano wiersza {expected_line}, otrzymano {first}.')
    if not count:
        raise ProtocolError('Otrzymano pusty blok raportu.')
    lines = []
    pos = 19
    for _ in range(count):
        if pos >= len(body):
            raise ProtocolError('Ucięta długość wiersza raportu.')
        length = body[pos]
        pos += 1
        if not length or pos + length > len(body) or body[pos + length - 1] != 0:
            raise ProtocolError('Ucięty wiersz raportu lub brak końcowego NUL.')
        lines.append(body[pos:pos + length - 1])
        pos += length
    if pos != len(body):
        raise ProtocolError('Nadmiarowe dane za wierszami raportu.')
    return cursor, lines


class CPCAClient:
    def __init__(self, ip, port=47545, timeout=5.0, retries=2, log=None):
        self.ip = str(ipaddress.IPv4Address(ip))
        if not 1 <= port <= 65535 or not 0 < timeout <= 120 or not 0 <= retries <= 10:
            raise ValueError('Nieprawidłowy port, timeout lub liczba ponowień.')
        self.timeout = timeout
        self.retries = retries
        self.log = log
        self.sequence = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connected UDP accepts datagrams only from this printer and port.
            self.socket.connect((self.ip, port))
        except BaseException:
            self.socket.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.socket.close()

    def record(self, direction, packet):
        if self.log:
            self.log.write(json.dumps({'time': datetime.datetime.now().astimezone().isoformat(),
                                      'direction': direction, 'hex': packet.hex()}) + '\n')
            self.log.flush()

    def exchange(self, operation, body=b''):
        self.sequence += 1
        if self.sequence > 65535:
            raise ProtocolError('Przekroczono limit numerów żądań.')
        packet = build_packet(operation, self.sequence, body)
        for attempt in range(self.retries + 1):
            self.record('TX', packet)
            self.socket.send(packet)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                self.socket.settimeout(max(0.001, deadline - time.monotonic()))
                try:
                    response = self.socket.recv(65535)
                except socket.timeout:
                    break
                self.record('RX', response)
                # Ignore delayed duplicates of earlier transactions.
                if len(response) >= 8:
                    magic, kind, response_op, response_seq = struct.unpack_from('!4H', response)
                    if (magic, kind, response_op, response_seq) != (0xCDCA, 0x1001, operation, self.sequence):
                        continue
                response_op, response_seq, flags, payload = parse_packet(response)
                return flags, payload
        raise TimeoutError(f'Brak odpowiedzi CPCA z {self.ip}; operacja 0x{operation:04x}, '
                           f'numer {self.sequence}, próby: {self.retries + 1}.')

    def initialize(self, allowed_models=None):
        flags, body = self.exchange(1)
        if flags != 1 or body != b'\x10':
            raise ProtocolError('Ploter nie potwierdził inicjalizacji CPCA z przechwyconej sesji.')
        flags, body = self.exchange(1, b'Support CPCA v2 Operations?')
        if flags != 1 or body.strip().lower() != b'yes':
            raise ProtocolError('Ploter nie potwierdził obsługi CPCA v2.')
        flags, body = self.exchange(0x66, MODEL_REQUEST)
        if flags != 1:
            raise ProtocolError('Błąd odczytu modelu plotera.')
        model = parse_model(body)
        # Default remains conservative for existing callers. The collector can
        # opt into other iPF models; all packet validations remain in force.
        allowed = ('iPF785',) if allowed_models is None else allowed_models
        normalized = model.strip().casefold()
        family_allowed = '*' in allowed and re.fullmatch(r'ipf\d+[a-z]*', normalized)
        if not family_allowed and normalized not in {m.strip().casefold() for m in allowed}:
            raise ProtocolError(f'Wykryto model {model}; model spoza listy CPCA.')
        flags, body = self.exchange(0x66, STATUS_REQUEST)
        if flags != 1 or not body.startswith(bytes.fromhex('0001000002590001011a')):
            raise ProtocolError('Nie rozpoznano odpowiedzi na wstępny odczyt statusu.')
        return model

    def read_status(self, progress=None):
        lines = []
        cursor = 0
        seen = set()
        size = 0
        for block in range(1, MAX_BLOCKS + 1):
            body = struct.pack('!HHB', cursor, 480, 1 if block == 1 else 3) + REPORT_SELECTOR
            flags, payload = self.exchange(0x38, body)
            next_cursor, new_lines = parse_block(flags, payload, len(lines))
            if next_cursor and next_cursor in seen:
                raise ProtocolError('Ploter powtórzył kursor kontynuacji raportu.')
            seen.add(next_cursor)
            size += sum(len(line) + 2 for line in new_lines)
            if size > MAX_REPORT:
                raise ProtocolError('Raport przekroczył limit 32 MB.')
            lines.extend(new_lines)
            if progress:
                progress(block, len(lines))
            if next_cursor == 0:
                return b'\r\n'.join(lines) + b'\r\n'
            cursor = next_cursor
            time.sleep(PAGE_DELAY)
        raise ProtocolError('Przekroczono limit bloków raportu.')


def field(root, name):
    return root.findtext('.//ivec:' + name, default='', namespaces=NS).strip()


def chmp_read(ip, args, log, probe_only=False):
    versions = ['1.3.0', '1.0.0'] if args.version == 'auto' else [args.version]
    errors = []
    for version in versions:
        try:
            device = ET.fromstring(query(ip, args.chmp_port, version, min(args.timeout, 3),
                                         'GetCapability', 'device', log))
            services = [s.strip().lower() for s in field(device, 'service').split(',')]
            if field(device, 'response') != 'OK' or field(device, 'manufacturer').lower() != 'canon' or 'counter' not in services:
                raise RuntimeError('Odpowiedź nie potwierdza obsługi odczytu liczników CHMP Canon.')
            result = {'protocol': 'CHMP', 'model': field(device, 'model') or 'Canon',
                      'serial': field(device, 'product_serialnumber'), 'version': version,
                      'device': device}
            if not probe_only:
                counter = ET.fromstring(query(ip, args.chmp_port, version, args.timeout,
                                              'GetStatus', 'counter', log))
                if field(counter, 'response') != 'OK':
                    raise RuntimeError('Ploter nie potwierdził odczytu liczników CHMP.')
                result['counter'] = counter
            return result
        except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
            errors.append(f'CHMP {version}: {exc}')
            log.write('\n' + errors[-1] + '\n')
    raise RuntimeError('; '.join(errors))


def cpca_read(ip, args, log, probe_only=False, progress=None):
    with CPCAClient(ip, args.cpca_port, min(args.timeout, 3), 0 if probe_only else args.retries, log) as client:
        model = client.initialize()
        result = {'protocol': 'CPCA', 'model': model, 'serial': '', 'version': '2'}
        if not probe_only:
            client.timeout = args.timeout
            result['raw'] = client.read_status(progress)
        return result


def fetch(ip, args, log, probe_only=False, progress=None):
    errors = []
    if args.protocol in ('auto', 'chmp'):
        try:
            return chmp_read(ip, args, log, probe_only)
        except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
            errors.append(str(exc))
    if args.protocol in ('auto', 'cpca'):
        try:
            return cpca_read(ip, args, log, probe_only, progress)
        except (OSError, ValueError, RuntimeError, ProtocolError) as exc:
            errors.append('CPCA: ' + str(exc))
            log.write('\n' + errors[-1] + '\n')
    raise RuntimeError(' | '.join(errors))


def report_html(rows, note, text=''):
    cells = ''.join('<tr><td>' + html.escape(str(k)) + '</td><td>' + html.escape(str(v)) + '</td></tr>' for k, v in rows)
    return ('<!doctype html><html lang="pl"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Canon — raport</title><style>body{font:16px system-ui;max-width:1100px;'
            'margin:24px auto;padding:0 16px}table{border-collapse:collapse;width:100%}'
            'td{padding:9px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}'
            'td:first-child{width:45%}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
            'font:13px Consolas,monospace}p{line-height:1.5}</style>'
            '<h1>Canon — raport odczytu</h1><table>' + cells + '</table><p>' + html.escape(note) + '</p>'
            + ('<h2>Pełny Status print</h2><pre>' + html.escape(text) + '</pre>' if text else '') + '</html>')


def write_result(base, result, ip, timestamp, args, log_path):
    protocol = result['protocol']
    text = ''
    if protocol == 'CHMP':
        rows = [('Protokół', 'CHMP ' + result['version'])] + report_rows(
            result['counter'], result['device'], f'{ip}:{args.chmp_port}', timestamp, [])
        note = REPORT_NOTE
    else:
        raw = result['raw']
        Path(str(base) + '.bin').write_bytes(raw)
        text = raw.decode(args.encoding)
        rows = [('Data odczytu', timestamp), ('Adres plotera', f'{ip}:{args.cpca_port}'),
                ('Protokół', 'CPCA v2 / UDP'), ('Model', result['model'])]
        for pattern, label in [(r'\bS/N:([A-Za-z0-9_-]+)', 'Numer seryjny'),
                               (r'\bFirm:([^\s]+)', 'Firmware'),
                               (r'\bLIFE-TTL:(\d+)', 'LIFE-TTL (wartość surowa)'),
                               (r'\bPRINT-COUNT:(\d+)', 'PRINT-COUNT (wartość surowa)')]:
            match = re.search(pattern, text)
            if match:
                rows.append((label, match.group(1)))
        ink = re.search(r'(?ms)^  INK-USE1\r?\n\s+INK\s+TTL:([0-9.]+ml)', text)
        if ink:
            rows.append(('INK-USE1 — INK TTL', ink.group(1)))
        note = ('Odczyt Status print przez CPCA, potwierdzony dla iPF785. Jednostki zachowano jak w raporcie. '
                'LIFE-TTL i PRINT-COUNT pozostają wartościami surowymi; nie są tu interpretowane jako liczba arkuszy.')
    table = '\n'.join(f'{label}: {value}' for label, value in rows)
    txt_path = Path(str(base) + '.txt')
    html_path = Path(str(base) + '.html')
    txt_path.write_bytes(('CANON — RAPORT\r\n\r\n' + table + '\r\n\r\n' + note +
                          ('\r\n\r\n=== STATUS PRINT ===\r\n' + text if text else '') +
                          '\r\n\r\n=== PEŁNY ZAPIS KOMUNIKACJI ===\r\n' +
                          log_path.read_text(encoding='utf-8')).encode('utf-8-sig'))
    html_path.write_text(report_html(rows, note, text), encoding='utf-8')
    return [txt_path, html_path]


def read_target(ip, args):
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    base = args.output.resolve() / f'Canon_{ip}_{stamp}'
    log_path = Path(str(base) + '.log')
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    try:
        with log_path.open('x', encoding='utf-8') as log:
            log.write(f'Canon — {timestamp}\nIP: {ip}\nTryb: {args.protocol}\n')
            result = fetch(ip, args, log, progress=lambda blocks, lines: print(f'CPCA: {blocks} bloków, {lines} wierszy'))
        print(f'Rozpoznano: {result["model"]}; protokół: {result["protocol"]}')
        paths = write_result(base, result, ip, timestamp, args, log_path)
        for path in paths:
            print('Zapisano:', path)
        return 0
    except (OSError, ValueError, RuntimeError, ProtocolError, ET.ParseError) as exc:
        error_path = Path(str(base) + '.error.txt')
        message = f'Nie ukończono odczytu {ip}: {exc}\nLog komunikacji: {log_path}\n'
        try:
            error_path.write_text(message, encoding='utf-8-sig')
        except OSError:
            pass
        print(message, file=sys.stderr)
        return 1


def discover_devices(args):
    networks = [ipaddress.ip_network(args.subnet, strict=False)] if args.subnet else local_networks()
    addresses = set()
    for network in networks:
        if network.version != 4 or network.num_addresses > 1024:
            print(f'Pomijam zakres {network}: limit wynosi 1024 adresy. Podaj mniejszy --subnet albo --ip.')
            continue
        print('Wyszukiwanie w:', network)
        addresses.update(str(ip) for ip in network.hosts())
    probe_args = argparse.Namespace(**vars(args))
    probe_args.timeout = min(args.timeout, 1)
    def probe(ip):
        try:
            device = fetch(ip, probe_args, io.StringIO(), probe_only=True)
            return dict(device, ip=ip)
        except (OSError, ValueError, RuntimeError, ProtocolError, ET.ParseError):
            return None
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(probe, ip) for ip in sorted(addresses, key=ipaddress.ip_address)]
        for future in concurrent.futures.as_completed(futures):
            device = future.result()
            if device:
                found.append(device)
                print(f'Znaleziono {device["model"]}: {device["ip"]} [{device["protocol"]}]')
    return sorted(found, key=lambda d: ipaddress.ip_address(d['ip']))


def choose_devices(found):
    for index, device in enumerate(found, 1):
        print(f'{index}. {device["model"]} | {device["ip"]} | {device["protocol"]}')
    print('Numery, np. 1,3; A — wszystkie; R — wpisz IP; Q — zakończ.')
    while True:
        choice = input('Wybierz plotery: ').strip().lower()
        if choice == 'q':
            return []
        if choice == 'r':
            try:
                return [str(ipaddress.IPv4Address(input('Adres IPv4: ').strip()))]
            except ValueError:
                print('Niepoprawny adres IPv4.')
        elif choice == 'a' and found:
            return [device['ip'] for device in found]
        else:
            tokens = re.split(r'[,;\s]+', choice)
            if tokens and all(token.isdigit() and 1 <= int(token) <= len(found) for token in tokens):
                return list(dict.fromkeys(found[int(token) - 1]['ip'] for token in tokens))
            print('Podaj poprawne numery lub R / Q.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ip', nargs='+', action='extend', help='Jeden lub kilka adresów IPv4; bez wyszukiwania')
    parser.add_argument('--subnet', help='Zakres wyszukiwania, np. 192.168.88.0/24')
    parser.add_argument('--scan-only', action='store_true', help='Tylko wyszukaj i wyświetl urządzenia')
    parser.add_argument('--protocol', choices=['auto', 'chmp', 'cpca'], default='auto')
    parser.add_argument('--version', choices=['auto', '1.3.0', '1.0.0'], default='auto', help='Wersja CHMP')
    parser.add_argument('--chmp-port', type=int, default=80)
    parser.add_argument('--cpca-port', type=int, default=47545)
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--retries', type=int, default=2, help='Dodatkowe próby UDP po braku odpowiedzi')
    parser.add_argument('--encoding', default='cp1250', help='Kodowanie tekstu CPCA')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'raporty_Canon')
    args = parser.parse_args(argv)
    try:
        if args.ip and args.subnet:
            raise ValueError('Wybierz --ip albo --subnet.')
        if args.scan_only and args.ip:
            raise ValueError('--scan-only używaj bez --ip, opcjonalnie z --subnet.')
        if args.ip:
            args.ip = list(dict.fromkeys(str(ipaddress.IPv4Address(ip)) for ip in args.ip))
        if args.subnet:
            net = ipaddress.ip_network(args.subnet, strict=False)
            if net.version != 4 or net.num_addresses > 1024:
                raise ValueError('--subnet musi być zakresem IPv4 do 1024 adresów.')
        codecs.lookup(args.encoding)
        if not 0 < args.timeout <= 120 or not 0 <= args.retries <= 10 or not all(1 <= p <= 65535 for p in (args.chmp_port, args.cpca_port)):
            raise ValueError('Porty: 1–65535; timeout: >0 i <=120; retries: 0–10.')
    except (ValueError, LookupError) as exc:
        parser.error(str(exc))
    try:
        if args.ip:
            selected = args.ip
        else:
            found = discover_devices(args)
            print(f'Znaleziono ploterów: {len(found)}')
            if args.scan_only:
                return 0
            selected = choose_devices(found)
        if not selected:
            return 0
        args.output.mkdir(parents=True, exist_ok=True)
        failures = 0
        for ip in selected:
            print(f'\nOdczyt plotera: {ip}')
            failures += read_target(ip, args)
        print(f'\nZakończono. Plotery: {len(selected)}; odczyty z błędem: {failures}.')
        return 1 if failures else 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Błąd: {exc}', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nAnulowano.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
