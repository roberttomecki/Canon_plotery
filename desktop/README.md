# Wersja na komputer

Ta wersja nadaje się do szybkiego odczytu na bieżąco: odpalasz, wybierasz ploter z listy i po chwili masz raport. Najlepiej działa na Windows.

## Czego potrzebujesz

- **Python 3.10 lub nowszy.** Na Windows musi być dostępne polecenie `py`, które instaluje się razem z Pythonem.
- **Windows PowerShell**, jeśli chcesz, żeby skrypt sam wykrył Twoją sieć.
- Dwa pliki, `Canon_plotery.py` i `Canon_plotery.cmd`, w jednym katalogu, w którym masz prawo zapisu. Nic więcej nie trzeba instalować.

Plik `.cmd` to wygodny skrót. Uruchamia Pythona, przekazuje mu parametry i na końcu czeka na naciśnięcie klawisza, żeby okno nie zamknęło się samo. Jeśli chcesz wpiąć odczyt w harmonogram zadań, wywołuj bezpośrednio Pythona, bez `.cmd`.

**Linux:** działa, ale automatyczne wykrywanie sieci korzysta z PowerShella. Dlatego na Linuksie zawsze podawaj `--ip` albo `--subnet`.

## Jak uruchomić

Najprościej kliknij dwukrotnie `Canon_plotery.cmd`. Skrypt sam poszuka ploterów i pokaże listę. Wtedy możesz wpisać:

- numery ploterów, oddzielone przecinkami;
- `A`, żeby odczytać wszystkie;
- `R`, żeby wpisać adres ręcznie;
- `Q`, żeby zakończyć.

Jeśli znasz adres plotera, możesz pominąć wyszukiwanie:

```bat
Canon_plotery.cmd
py -3 Canon_plotery.py --ip 192.0.2.10
py -3 Canon_plotery.py --ip 192.0.2.10 192.0.2.11 --protocol chmp
py -3 Canon_plotery.py --subnet 192.0.2.0/24
py -3 Canon_plotery.py --subnet 192.0.2.0/24 --scan-only
py -3 Canon_plotery.py --ip 192.0.2.20 --protocol cpca
```

Na Linuksie zamiast `py -3` wpisz `python3`. Opcja `--scan-only` tylko pokazuje, co jest w sieci, bez odczytu liczników.

## Wszystkie opcje

| Opcja | Co robi (wartość domyślna) |
| --- | --- |
| `--ip IP [IP ...]` | Jeden lub kilka adresów IPv4. Nie łącz z `--subnet` |
| `--subnet CIDR` | Jedna podsieć IPv4, maksymalnie 1024 adresy |
| `--scan-only` | Samo wyszukiwanie, bez odczytu. Nie łącz z `--ip` |
| `--protocol auto/chmp/cpca` | `auto` najpierw próbuje CHMP, potem CPCA |
| `--version auto/1.3.0/1.0.0` | Wersja zapytania CHMP. `auto` próbuje obu |
| `--chmp-port` / `--cpca-port` | 80 (TCP) / 47545 (UDP) |
| `--timeout` | Ile sekund czekać na odpowiedź: 10, dozwolone od powyżej 0 do 120 |
| `--retries` | Ile razy ponowić zapytanie UDP: 2, zakres 0–10 |
| `--encoding` | Kodowanie tekstu z CPCA: cp1250 |
| `--output` | Gdzie zapisać raporty, domyślnie `raporty_Canon` obok skryptu |

Ta wersja obsługuje przez CPCA tylko **iPF785**. Nie ma też niektórych nowości z wersji NAS, na przykład CHMP 1.4.0 i eksperymentalnej obsługi innych iPF.

## Co dostajesz

Dla każdego plotera powstaje:

- raport **TXT** i **HTML** z odczytanymi wartościami;
- **log** z całą komunikacją;
- przy CPCA dodatkowo surowa odpowiedź **BIN**.

Nazwy plików zawierają datę, godzinę i urządzenie. Jeśli coś pójdzie nie tak, może powstać osobny plik z opisem błędu. Dlatego otwórz pliki i sprawdź ich treść, bo sam katalog z raportami jeszcze nie znaczy, że odczyt się udał.

Kody wyjścia przydają się, jeśli uruchamiasz skrypt z innego programu:

- `0`: bez błędów. Ten kod jest też wtedy, gdy zrezygnowałeś z wyboru albo `--scan-only` niczego nie znalazł.
- `1`: błąd odczytu lub wykonania.
- `2`: złe parametry.
- `130`: przerwane przez użytkownika.

Ta wersja nie wysyła maili. Jeśli potrzebujesz zbiorczego raportu albo skanu bez Twojego udziału, użyj [wersji NAS](../nas/README.md).

## Gdy coś nie działa

**Zacznij od jednego plotera.** Uruchom `--ip <adres> --protocol chmp` i porównaj wynik z tym, co widać na panelu urządzenia. Dopiero kiedy to się zgadza, skanuj całą sieć.

Jeśli CHMP nie odpowiada, to jeszcze nie znaczy, że coś jest zepsute. Ploter może używać CPCA (UDP) albo ruch może blokować zapora. Ploter obsługiwany tylko przez UDP nie musi mieć otwartego portu 80.

Nie przeliczaj wyników automatycznie na ml czy m². Dlaczego, wyjaśnia [główny README](../README.md#jak-czytać-wyniki).

**Aktualizacja:** zanim podmienisz skrypty, zachowaj stare wersje i dotychczasowe raporty. Jeśli nowa wersja sprawi kłopot, po prostu przywróć stare pliki.
