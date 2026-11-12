# Wersja na NAS (Synology / Linux)

Ta wersja jest do pracy bez nadzoru. NAS raz skanuje sieć, zbiera liczniki ze wszystkich znalezionych ploterów, zapisuje komplet raportów do folderu z datą i kończy pracę. **To nie jest serwer, który działa cały czas.** Każde uruchomienie to jeden skan.

## Z czego się składa

W katalogu `app/` są trzy pliki. Muszą leżeć razem, nawet jeśli nie używasz poczty:

- `canon_collector.py` to program główny, który skanuje i zapisuje wyniki;
- `canon_protocols.py` odpowiada za rozmowę z ploterami przez CHMP i CPCA;
- `canon_mailer.py` składa raport TXT i, jeśli tego chcesz, wysyła go mailem.

Wystarczy Python 3.10+ ze standardowymi bibliotekami. Kontener nie jest konieczny, możesz uruchomić skrypt bezpośrednio, tylko wtedy podaj podsieć (CIDR). **Nie podmieniaj Pythona, który jest w DSM.**

## Przygotowanie Synology, krok po kroku

1. **Sprawdź, co masz.** Model NAS-a, wersja DSM, ilość RAM, czy Container Manager jest dostępny i w jakiej wersji. Nie zgaduj tego po samej nazwie modelu.
2. **Zrób kopię bezpieczeństwa.** Wyeksportuj konfigurację DSM i zapisz ją poza NAS-em. To kopia ustawień, nie danych, więc upewnij się też, że ważne dane mają aktualną kopię. Jeśli kolektor był już zainstalowany, zachowaj poprzednią wersję.
3. **Sprawdź adres sieci LAN.** Odczytaj IP i maskę interfejsu LAN NAS-a. Nie zakładaj, że to /24. Nie skanuj też wewnętrznej sieci kontenerów (bridge), bo plotery są w LAN-ie.
4. **Przygotuj foldery.** W wybranym udziale utwórz `CanonCollector/apps` na kod i `CanonCollector/reports` na wyniki. Nadaj uprawnienia (ACL) tylko tym, którzy ich potrzebują. Bez `chmod 777`.
5. **Wgraj pliki.** Skopiuj trzy pliki z `app/` do `apps` na NAS-ie.

W moim pilotażu udział nazywał się `/volume1/WF_Serwis/CanonCollector`. Ścieżki i adresy niżej to tylko przykłady. Nie instaluj ani nie aktualizuj pakietów DSM bez zgody administratora.

## Tworzenie kontenera w DSM

Użyj oficjalnego obrazu `python`. W pilotażu był to już wcześniej pobrany `python:latest`. Według zmiennej obrazu miał wersję 3.15.2, ale nie sprawdzałem tego osobno przez `python --version`.

Uwaga: `latest` zmienia się z czasem. Jeśli chcesz mieć powtarzalne wdrożenie, zapisz dokładną wersję i identyfikator (digest) obrazu, który przetestowałeś, i nie aktualizuj go automatycznie. Nowy obraz musi też obsługiwać procesor Twojego NAS-a.

| Ustawienie | Wartość |
| --- | --- |
| Sieć | bridge. Podsieć LAN podajesz jako parametr |
| Publikowane porty | Żadne. Kontener tylko łączy się na zewnątrz |
| Folder kodu | `/volume1/UDZIAL/CanonCollector/apps` → `/app`, tylko do odczytu |
| Folder raportów | `/volume1/UDZIAL/CanonCollector/reports` → `/reports`, odczyt i zapis |
| Wysokie uprawnienia (privileged) | Wyłączone |
| Automatyczny restart | Wyłączony, bo to zadanie jednorazowe |

Wyłączone „privileged” nie oznacza jeszcze, że w środku kontenera nie działa root. Na produkcji ustal UID/GID konta, pod którym kolektor ma działać, ustaw pod nie ACL folderu i sprawdź, czy raporty się zapisują. W pilotażu przez interfejs graficzny nie potwierdziłem pracy na nieuprzywilejowanym UID. Nie montuj `docker.sock`, katalogów systemowych ani całego udziału.

**Pierwsza próba: jeden ploter, tylko CHMP**

```text
python3 -B -u /app/canon_collector.py --chmp-only --subnet 192.0.2.10/32 --output /reports --workers 1 --timeout 5
```

**Gdy to działa: pełny skan, CHMP i CPCA**

```text
python3 -B -u /app/canon_collector.py --subnet 192.0.2.0/24 --output /reports --workers 4 --timeout 3 --retries 1
```

Podstaw własne adresy w miejsce przykładowych.

Kilka słów o CPCA:

- Domyślnie skrypt próbuje CPCA z całą rodziną iPF, ale poza iPF785 jest to eksperymentalne.
- Żeby ograniczyć się do sprawdzonego modelu, dodaj `--cpca-model iPF785`. Opcję można powtórzyć, żeby podać kilka modeli.
- `--chmp-only` całkowicie wyłącza CPCA, nawet gdy CHMP zawiedzie.

Zapora i routing muszą przepuszczać ruch wychodzący z NAS-a do ploterów (TCP 80 i UDP 47545) oraz odpowiedzi. Niczego nie trzeba otwierać od strony Internetu. Nie zmieniaj ustawień zapory na ślepo.

## Alternatywa: Compose

Plik `compose.yaml` to szablon dla tych, którzy wolą konfigurację z pliku niż kreator w DSM. Przed użyciem uzupełnij w nim obraz i ścieżki. Nie uruchamiaj jednocześnie kontenera z kreatora i projektu Compose do tego samego skanu.

Szablon dodatkowo zabezpiecza kontener: odbiera zbędne uprawnienia (capabilities), blokuje ich podnoszenie i nie pozwala pisać po systemie plików kontenera. Zapisywalny zostaje tylko `/reports`. To dodatkowa opcja, a nie odtworzona i przetestowana konfiguracja z pilotażu.

## Wszystkie opcje

| Opcja | Co robi (wartość domyślna) |
| --- | --- |
| `--subnet CIDR` | Podsieć do skanowania. Można podać kilka razy, każda do 1024 adresów, a powtórzone adresy są pomijane |
| `--output PATH` | Gdzie zapisać wyniki: `~/canon-collector-data`. W kontenerze ustaw `/reports` |
| `--workers` | Ile adresów sprawdzać naraz: 4, zakres 1–24 |
| `--timeout` | Ile sekund czekać na odpowiedź: 5, dozwolone od powyżej 0 do 120 |
| `--retries` | Ile razy ponowić zapytanie CPCA: 2, zakres 0–10 |
| `--chmp-only` | Wyłącza CPCA. Domyślnie nieaktywna |
| `--cpca-model MODEL` | Które modele próbować przez CPCA. Domyślnie wszystkie iPF, eksperymentalne poza iPF785 |
| `--email` | Wysyła raport mailem po skanie. Domyślnie wyłączona |

**Zawsze podawaj `--subnet` na Synology.** Bez tej opcji skrypt próbuje sam wykryć sieć poleceniem `ip -j -4 addr show up`, ale:

- DSM może nie obsługiwać przełącznika `-j`;
- w kontenerze skrypt zobaczy sieć wewnętrzną kontenerów, a nie Twój LAN.

Jak ustalić podsieć? `ip -4 addr show` poda adres z prefiksem (np. `192.0.2.5/24`). Podsieć wyliczysz z tego w Pythonie: `ipaddress.ip_interface('ADRES/PREFIKS').network`. Tutaj nie używa się PowerShellowego `Get-NetIPConfiguration`. Jeśli plotery są w innych VLAN-ach, najpierw upewnij się, że NAS ma do nich trasę, i podaj ich zakresy wprost.

## Uruchamianie i wyniki

Kolejny skan uruchomisz w **Container Manager → Kontener → (nazwa) → Uruchom**. Nie odpalaj dwóch kopii jednocześnie.

Każdy skan tworzy nowy folder nazwany datą i godziną w UTC, w formacie `YYYYMMDDTHHMMSS_mikrosekundyZ/`:

```text
manifest.json                  # podsumowanie całego skanu
Canon_<czas>.txt               # zbiorczy raport do czytania
<IP>/result.json               # wynik dla jednego plotera
<IP>/communication.log         # zapis komunikacji
<IP>/device_<wersja>.xml       # CHMP
<IP>/counter_<wersja>.xml      # CHMP
<IP>/status.bin                # CPCA
<IP>/status.txt                # CPCA
```

Nie każdy ploter dostanie wszystkie pliki, bo zależy to od protokołu i od tego, co się udało odczytać. Adresy, na których nie potwierdzono plotera, są tylko w manifeście i nie mają własnych katalogów. Dla znalezionych urządzeń zachowywane są surowe odpowiedzi. Raport zbiorczy może zawierać częściowe dane, więc patrz na statusy i błędy, a nie tylko na liczby.

Kody wyjścia:

- `0`: co najmniej jeden udany odczyt i żadnego częściowego. Uwaga: to nie znaczy, że znaleziono wszystkie plotery.
- `1`: były wyniki częściowe, nic się nie udało albo zawiódł raport lub wysyłka maila.
- `2`: złe parametry.

Program może też przerwać nieobsłużony wyjątek, dlatego zachowuj logi.

**Ile to trwa?** W pilotażu skan /24 zajął około 13 minut. Najwięcej czasu schodzi na czekanie, aż puste adresy nie odpowiedzą. Sam odczyt ploterów jest szybki. To obserwacja, a nie limit. Na koniec sprawdź w logu `Checked 254/254`, podsumowanie i czy zapisał się plik TXT.

## Harmonogram i powiadomienia

Repozytorium **nie włącza harmonogramu**. W pilotażu skany uruchamiałem ręcznie. Automatyzację ustaw dopiero wtedy, gdy wiesz, o której ma działać, pod jakim kontem i jak uruchamiać kontener. W Harmonogramie zadań DSM:

- podawaj pełne ścieżki;
- zabezpiecz się przed dwoma skanami naraz;
- nie używaj automatycznego restartu kontenera zamiast harmonogramu.

Pomyśl też o sprzątaniu, bo stare raporty nie są usuwane same.

**Alert „Nieoczekiwane zatrzymanie kontenera”.** Kontener po skanie się zatrzymuje i tak ma być. DSM może jednak zgłosić to jako problem, mimo że raport jest kompletny. Zanim się zaniepokoisz, sprawdź log i kod wyjścia.

Jeśli świadomie chcesz wyciszyć ten alert, utwórz własną regułę powiadomień obejmującą wszystkie zdarzenia **poza tym jednym** i przypisz ją do profilu odbiorców e-mail zamiast niemodyfikowalnej reguły „All”. Pamiętaj o dwóch rzeczach:

- wyciszysz w ten sposób też prawdziwe awarie innych kontenerów;
- powiadomienia push przez konto Synology mogą przychodzić nadal.

Nie wyłączaj wszystkich powiadomień NAS-a.

## Wysyłka raportu mailem (opcjonalnie)

Domyślnie raporty zostają na NAS-ie. Jeśli chcesz je dostawać mailem, ustaw przed użyciem `--email`:

```text
CANON_SMTP_SENDER=collector@example.com
CANON_SMTP_RECIPIENT=reports@example.com
CANON_SMTP_HOST=smtp.example.com
CANON_SMTP_PASSWORD_FILE=/run/secrets/canon-smtp-password
```

Połączenie idzie przez SMTP_SSL na porcie 465 i sprawdza certyfikat serwera. Nie wyłączaj tego sprawdzania.

**Hasło:**

- trzymaj je w osobnym pliku, poza repozytorium i poza folderem z raportami;
- ustaw prawa 600 albo odpowiednie ACL;
- zamontuj w kontenerze tylko ten jeden plik, tylko do odczytu;
- nigdy nie wpisuj hasła w polecenie, obraz ani `compose.yaml`.

Jeśli nie ustawisz `CANON_SMTP_PASSWORD_FILE`, skrypt poszuka hasła w `~/.canon-smtp-password`, więc katalog domowy (HOME) konta musi być ustawiony poprawnie.

Mail idzie z konta nadawcy do **jednego** adresata. Wysyłki maili nie testowałem w pilotażu NAS. Dlatego najpierw przejrzyj wygenerowany TXT, upewnij się, że adresat jest właściwy, i dopiero wtedy zrób próbną wysyłkę. Powiadomienia DSM to osobna sprawa, niezwiązana z pocztą kolektora.

## Aktualizacja i powrót do poprzedniej wersji

1. Upewnij się, że żaden skan nie trwa.
2. Zachowaj obecne trzy pliki, konfigurację kontenera i identyfikator obrazu.
3. Podmień wszystkie trzy moduły naraz, nie pojedynczo.
4. Przetestuj na jednym adresie IP.

Jeśli coś nie działa, przywróć stare pliki i konfigurację. Nie trzeba do tego przywracać całego DSM. Raportów nie usuwaj, a obrazu nie kasuj, jeśli korzystają z niego inne aplikacje.

Pamiętaj, że nowa wersja na GitHubie sama nie trafi na NAS. Pliki trzeba podmienić ręcznie.
