# Kolektor na komputer

## Instalacja i pliki

Zainstaluj Python 3.10+; na Windows potrzebny jest launcher `py`, a do automatycznego wykrywania sieci Windows PowerShell. Skopiuj `Canon_plotery.py` i `Canon_plotery.cmd` do jednego zapisywalnego katalogu. Brak zależności pip. `.cmd` uruchamia Pythona, przekazuje parametry i czeka na naciśnięcie klawisza po zakończeniu; do harmonogramu używaj bezpośrednio Pythona.
Windows jest środowiskiem interaktywnego wykrywania. Na Linuxie używaj jawnego `--ip` lub `--subnet`; automatyczne wykrywanie tej wersji wywołuje PowerShell.

## Uruchamianie

```bat
Canon_plotery.cmd
py -3 Canon_plotery.py --ip 192.0.2.10
py -3 Canon_plotery.py --ip 192.0.2.10 192.0.2.11 --protocol chmp
py -3 Canon_plotery.py --subnet 192.0.2.0/24
py -3 Canon_plotery.py --subnet 192.0.2.0/24 --scan-only
py -3 Canon_plotery.py --ip 192.0.2.20 --protocol cpca
```

Na Linuxie zamień `py -3` na `python3`. Jawne IP pomija wyszukiwanie i wybór. Bez `--ip` program wyszukuje urządzenia, po czym pyta o wybór: numery oddzielone przecinkami, A (wszystkie), R (ręczny adres), Q (koniec). `--scan-only` kończy po odkryciu, bez raportów odczytu.

## Parametry

| Parametr | Znaczenie / domyślnie |
| --- | --- |
| `--ip IP [IP ...]` | Jeden lub kilka IPv4; nie łączyć z `--subnet` |
| `--subnet CIDR` | Jedna podsieć IPv4, najwyżej 1024 adresy |
| `--scan-only` | Tylko wykrywanie; nie łączyć z `--ip` |
| `--protocol auto/chmp/cpca` | auto: CHMP, potem CPCA |
| `--version auto/1.3.0/1.0.0` | Wersja żądania CHMP; auto próbuje obie |
| `--chmp-port` / `--cpca-port` | 80 TCP / 47545 UDP |
| `--timeout` | 10 sekund; dozwolone >0 do 120 |
| `--retries` | Dodatkowe próby UDP: 2, zakres 0–10 |
| `--encoding` | Tekst CPCA: cp1250 |
| `--output` | Domyślnie `raporty_Canon` obok skryptu |

W tej wersji CPCA jest ograniczone do iPF785. Wersja komputerowa nie ma wszystkich rozszerzeń kolektora NAS (np. CHMP 1.4.0 i eksperymentalnej listy iPF).

## Raporty i błędy

Raport TXT i HTML zawiera odczytane pola, log zapisuje komunikację; CPCA zachowuje surowy BIN. Nazwy uwzględniają czas i urządzenie. Przy błędzie może powstać osobny plik błędu. Sprawdź pliki, a nie tylko obecność katalogu.
Kod wyjścia: 0 — brak błędów (również rezygnacja z wyboru), 1 — błąd odczytu/wykonania, 2 — błąd argumentów, 130 — przerwanie/anulowanie wejścia. `--scan-only` z brakiem urządzeń może zakończyć się kodem 0.
Ta wersja nie wysyła e-maili. Do zbiorczych raportów i nieinteraktywnego skanu użyj wersji NAS.

## Weryfikacja i diagnostyka

Zacznij od jednego IP i `--protocol chmp`, porównaj wynik z panelem plotera, dopiero potem skanuj sieć. Brak CHMP nie dowodzi awarii: model może używać CPCA albo odczyt może blokować zapora. Nie wymagaj otwartego TCP 80 od urządzenia obsługiwanego tylko przez UDP.
Wyników nie przeliczaj automatycznie na ml/m²; zasady interpretacji opisuje główny README.
Przed aktualizacją zachowaj poprzednie skrypty i raporty. Wycofanie polega na przywróceniu tych plików.
