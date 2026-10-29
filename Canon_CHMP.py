"""Odczyt Canon CHMP: POST -> GET na tym samym polaczeniu TCP.
Python 3, bez dodatkowych bibliotek. Nie zmienia ustawien plotera.
"""
import argparse
import datetime
import html
import concurrent.futures
import io
import ipaddress
import json
import pathlib
import re
import socket
import subprocess
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
    code = int(status.split()[1])
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


def summarize(data, log):
    root = ET.fromstring(data)
    log.write('\n=== PODSUMOWANIE LICZNIKOW ===\n')
    response = root.find('.//ivec:response', NS)
    if response is not None:
        log.write(f'Odpowiedz Canon: {response.text}\n')
        if response.text != 'OK':
            log.write('Ploter nie potwierdzil poprawnego odczytu; sprawdz XML powyzej.\n')
    node = root.find('.//ivec:total_sheets_a4', NS)
    if node is not None and node.text:
        count = int(node.text)
        log.write(f'Licznik A4: {count}\nPowierzchnia wyliczona A4 * 0.06237: {count * 0.06237:.5f} m2\n')
    inks = root.findall('.//ivec:ink_accumulated_info/ivec:item', NS)
    for item in inks:
        log.write('Zuzycie atramentu, wartosc surowa: ' +
                  str(item.findtext('ivec:color', namespaces=NS)) + ' = ' +
                  str(item.findtext('ivec:amount', namespaces=NS)) + '\n')
    media = root.findall('.//ivec:medium_accumulated_info/ivec:item', NS)
    for item in media:
        log.write(f'Medium {item.get("number")}: ' +
                  str(item.findtext('ivec:custom_papertype', namespaces=NS)) +
                  '; area_square (surowe) = ' +
                  str(item.findtext('ivec:area_square', namespaces=NS)) + '\n')
    if node is None and not inks and not media:
        log.write('Brak oczekiwanych pol licznikow. Zachowano pelna odpowiedz.\n')
    log.write('Jednostki amount i area_square nie sa zakladane bez potwierdzenia dla tego modelu.\n')


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


def save_report(path, rows):
    def clean(text):
        return ' '.join(str(text).split())
    width = max([len('Opis')] + [len(clean(label)) for label, _ in rows])
    table = (f'{"Opis":<{width}} | Wartość\n' + '-' * (width + 45) + '\n' +
             '\n'.join(f'{clean(label):<{width}} | {clean(value)}' for label, value in rows))
    raw = path.read_text(encoding='utf-8')
    path.write_text('CANON — RAPORT\n\n' + table + '\n\n' + REPORT_NOTE +
                    '\n\n=== PEŁNY ZAPIS KOMUNIKACJI ===\n' + raw, encoding='utf-8-sig')
    html_path = path.with_suffix('.html')
    body_rows = ''.join('<tr><td>' + html.escape(str(label)) + '</td><td>' +
                        html.escape(str(value)) + '</td></tr>' for label, value in rows)
    html_path.write_text('<!doctype html><html lang="pl"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Canon — raport</title><style>body{font:16px system-ui;max-width:1100px;'
        'margin:32px auto;padding:0 16px;color:#182638}table{border-collapse:collapse;width:100%}'
        'td,th{padding:12px;text-align:left;border-bottom:1px solid #d9e1e9;overflow-wrap:anywhere}'
        'th{background:#dce8f6}tr:nth-child(even){background:#f4f7fa}td:first-child{width:45%}'
        'p{line-height:1.6}@media print{body{margin:0;font-size:11px}td,th{padding:6px}}</style>'
        '<h1>Canon — liczniki i informacje</h1><table><thead><tr><th>Opis</th><th>Wartość</th>'
        '</tr></thead><tbody>' + body_rows + '</tbody></table><p>' + html.escape(REPORT_NOTE) +
        '</p></html>', encoding='utf-8')
    return html_path


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


def identify(ip, port, version):
    try:
        # Szybki test portu ogranicza czas oczekiwania na nieaktywne adresy.
        with socket.create_connection((ip, port), timeout=0.7):
            pass
        root = ET.fromstring(query(ip, port, version, 4, 'GetCapability', 'device', io.StringIO()))
        def field(name):
            return root.findtext('.//ivec:' + name, default='', namespaces=NS).strip()
        if field('response') == 'OK' and field('manufacturer').lower() == 'canon' and 'counter' in field('service').split(','):
            return (ip, field('model') or 'Canon', field('product_serialnumber'))
    except (OSError, ValueError, RuntimeError, ET.ParseError):
        pass
    return None


def select_printer(port, version, subnet=None):
    try:
        networks = [ipaddress.ip_network(subnet, strict=False)] if subnet else local_networks()
    except (OSError, ValueError, subprocess.SubprocessError):
        networks = []
    if not networks:
        print('Nie udało się wykryć sieci lokalnej.')
    addresses = set()
    for network in networks:
        if network.version != 4 or network.num_addresses > 1024:
            print(f'Pomijam duży zakres {network}. Użyj --subnet, np. 192.168.0.0/24, aby zawęzić wyszukiwanie.')
            continue
        print(f'Wyszukiwanie urządzeń Canon w {network}...')
        addresses.update(str(ip) for ip in network.hosts())
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(identify, ip, port, version) for ip in sorted(addresses, key=ipaddress.ip_address)]
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            device = future.result()
            if device:
                found.append(device)
                print(f'Znaleziono: {device[1]} — {device[0]} — {device[2]}')
            if completed % 64 == 0:
                print(f'Sprawdzono {completed}/{len(addresses)} adresów...')
    found.sort(key=lambda item: ipaddress.ip_address(item[0]))
    print('\nDla której maszyny pobrać dane? Możesz wybrać kilka.')
    for number, (ip, model, serial) in enumerate(found, 1):
        print(f'{number}. {model} | {ip} | numer seryjny: {serial or "brak"}')
    if not found:
        print('Nie znaleziono urządzeń Canon obsługujących ten odczyt CHMP.')
    print('Podaj numery, np. 1,3,4; A — wszystkie; R — wpisz IP ręcznie; Q — zakończ')
    while True:
        choice = input('Wybierz maszyny: ').strip().lower()
        if choice == 'q':
            return []
        if choice == 'r':
            try:
                return [str(ipaddress.ip_address(input('Adres IP plotera: ').strip()))]
            except ValueError:
                print('Niepoprawny adres IP.')
        elif choice == 'a' and found:
            return [item[0] for item in found]
        else:
            tokens = re.split(r'[,;\s]+', choice)
            if tokens and all(token.isdigit() and 1 <= int(token) <= len(found) for token in tokens):
                # Usuń powtórzenia, zachowując kolejność wskazaną przez użytkownika.
                return list(dict.fromkeys(found[int(token) - 1][0] for token in tokens))
            print('Podaj poprawne numery z listy, np. 1,3. Nie wybrano żadnej maszyny.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', help='Bezpośredni odczyt podanego IP, bez wyszukiwania')
    parser.add_argument('--subnet', help='Zakres wyszukiwania IPv4, np. 192.168.0.0/24')
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--version', default='1.3.0', choices=['1.3.0', '1.0.0'])
    parser.add_argument('--timeout', type=float, default=20)
    args = parser.parse_args()
    if args.ip:
        try:
            selected = [str(ipaddress.ip_address(args.ip))]
        except ValueError:
            parser.error('Niepoprawny adres IP')
    else:
        selected = select_printer(args.port, args.version, args.subnet)
    failures = 0
    for number, ip in enumerate(selected, 1):
        print(f'\n=== Wybrana maszyna {number}/{len(selected)}: {ip} ===')
        args.ip = ip
        try:
            failures += read_printer(args)
        except OSError as exc:
            failures += 1
            print(f'Błąd zapisu raportu dla {ip}: {exc}')
    if selected:
        print(f'\nZakończono. Wybrane maszyny: {len(selected)}; odczyty z błędem: {failures}.')
    return 1 if failures else 0


def read_printer(args, report_paths=None):
    # Pliki powstają dopiero tutaj, wyłącznie dla wskazanych adresów.
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    safe_ip = re.sub(r'[^a-zA-Z0-9_.-]', '_', args.ip)
    path = pathlib.Path.cwd() / f'Canon_CHMP_{safe_ip}_{stamp}.txt'
    failed = False
    model = None
    counter = device = None
    errors = []
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    with path.open('w', encoding='utf-8') as log:
        log.write(f'CANON CHMP - {datetime.datetime.now().astimezone().isoformat()}\n'
                  f'Adres: {args.ip}:{args.port}\nCHMP: {args.version}\n')
        # Dwie niezalezne transakcje, tak jak w pcap: licznik oraz identyfikacja.
        for operation, service in [('GetStatus', 'counter'), ('GetCapability', 'device')]:
            try:
                print(f'Odczyt {operation}/{service}...')
                data = query(args.ip, args.port, args.version, args.timeout, operation, service, log)
                root = ET.fromstring(data)
                if service == 'counter':
                    counter = root
                else:
                    device = root
                    model = root.findtext('.//ivec:model', namespaces=NS)
                if root.findtext('.//ivec:response', namespaces=NS) != 'OK':
                    raise RuntimeError('Ploter nie potwierdził odczytu: ' + str(root.findtext('.//ivec:response', namespaces=NS)))
            except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
                failed = True
                errors.append((operation + '/' + service, exc))
                log.write(f'\nBLAD {operation}/{service}: {exc}\n')
                log.flush()
                print(f'Blad: {exc}')
    if model:
        safe_model = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', model).strip(' .')[:80]
        if safe_model:
            target = path.with_name(f'Canon_CHMP_{safe_model}_{safe_ip}_{stamp}.txt')
            path.rename(target)
            path = target
    html_path = save_report(path, report_rows(counter, device, f'{args.ip}:{args.port}', timestamp, errors))
    if report_paths is not None:
        report_paths.extend([path.resolve(), html_path.resolve()])
    print(f'Zapisano raport tekstowy i pelna komunikacje: {path}')
    print(f'Zapisano czytelna tabele HTML: {html_path}')
    if failed:
        print('Co najmniej jeden odczyt nie powiodl sie. Szczegoly znajduja sie w logu.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
