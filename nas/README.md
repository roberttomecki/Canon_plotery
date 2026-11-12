# Kolektor NAS / Linux / Synology

## Sposób pracy

`app/canon_collector.py` wykonuje jeden skan, zapisuje datowany zestaw raportów i kończy proces. Nie jest stale działającym serwerem. `canon_protocols.py` dostarcza protokoły, a `canon_mailer.py` generuje TXT i opcjonalnie wysyła e-mail. Wszystkie trzy pliki muszą być razem, także bez SMTP.
Python 3.10+, tylko biblioteki standardowe. Uruchomienie bez kontenera jest możliwe z jawnym CIDR. Nie zastępuj Pythona DSM.

## Przygotowanie Synology

1. Potwierdź model, wersję DSM, RAM, dostępność i wersję Container Manager. Nie zakładaj dostępności po samej nazwie modelu.
2. Wyeksportuj konfigurację DSM i zachowaj poza NAS; to nie jest kopia danych. Sprawdź kopię ważnych danych i zachowaj poprzednią instalację kolektora.
3. Odczytaj IP i maskę interfejsu LAN NAS. Nie zakładaj /24 i nie skanuj sieci mostka kontenera.
4. Ustal folder udziału i jego rzeczywistą ścieżkę. Utwórz `CanonCollector/apps` na kod oraz `CanonCollector/reports` na wyniki. Zastosuj ograniczone ACL, nie chmod 777.
5. Prześlij trzy pliki z `app/` repozytorium do `apps` na NAS.

Pilotaż użytkownika wykorzystywał udział `/volume1/WF_Serwis/CanonCollector`, ale poniższe ścieżki i adresy to przykłady. Nie instaluj ani nie aktualizuj pakietów DSM bez decyzji administratora.

## Kontener w interfejsie DSM

Użyj oficjalnego obrazu `python`. W pilotażu użyto już pobranego `python:latest`; zmienna obrazu deklarowała 3.15.2, nie wykonano osobnego pomiaru `python --version`. Tag latest jest zmienny. Dla powtarzalnego wdrożenia zapisz rzeczywistą wersję i identyfikator/digest przetestowanego obrazu; nie aktualizuj automatycznie. Nowy obraz musi obsługiwać architekturę NAS.

| Ustawienie | Wartość |
| --- | --- |
| Sieć | bridge, jawna podsieć LAN jako parametr |
| Porty publikowane | Brak — tylko połączenia wychodzące |
| Folder kodu | `/volume1/UDZIAL/CanonCollector/apps` → `/app`, tylko odczyt |
| Folder raportów | `/volume1/UDZIAL/CanonCollector/reports` → `/reports`, odczyt/zapis |
| Wysokie uprawnienia / privileged | Wyłączone |
| Automatyczny restart | Wyłączony — zadanie jednorazowe |

Brak privileged nie oznacza automatycznie użytkownika bez root wewnątrz kontenera. Do produkcji ustal UID/GID konta kolektora i ACL folderu; sprawdź zapis raportów pod tym kontem. Pilotaż UI nie potwierdził nieuprzywilejowanego UID. Nie montuj docker.sock, katalogów systemowych ani całego udziału.

Pierwszy test jednego plotera, wyłącznie CHMP:

```text
python3 -B -u /app/canon_collector.py --chmp-only --subnet 192.0.2.10/32 --output /reports --workers 1 --timeout 5
```

Pełny skan CHMP i CPCA:

```text
python3 -B -u /app/canon_collector.py --subnet 192.0.2.0/24 --output /reports --workers 4 --timeout 3 --retries 1
```

Podmień dokumentacyjne adresy na własny zakres. CPCA domyślnie dopuszcza rodzinę iPF: poza iPF785 to obsługa eksperymentalna. Aby ją ograniczyć, dodaj `--cpca-model iPF785` (można powtórzyć opcję dla uzgodnionej listy). `--chmp-only` całkowicie omija inicjalizację CPCA, również po błędach CHMP.
Zapora/trasy muszą umożliwiać ruch wychodzący TCP 80 i UDP 47545 do ploterów oraz odpowiedzi. Nie trzeba wystawiać portów NAS do Internetu. Nie zmieniaj zapory w ciemno.

## Opcjonalny projekt Compose

`compose.yaml` jest szablonem alternatywnym do kreatora GUI. Przed użyciem uzupełnij obraz i ścieżki. Nie wdrażaj równocześnie kontenera GUI i projektu dla tego samego skanu.
Szablon ogranicza capabilities, blokuje eskalację i zapis do systemu plików kontenera, a `/reports` pozostaje zapisywalny. To dodatkowy wariant konfiguracji, nie odtworzony i przetestowany eksport pilotażu DSM.

## Parametry CLI

| Opcja | Domyślnie / zachowanie |
| --- | --- |
| `--subnet CIDR` | Można powtarzać; IPv4, każda podsieć do 1024 adresów; adresy deduplikowane |
| `--output PATH` | `~/canon-collector-data`; w kontenerze ustaw `/reports` |
| `--workers` | 4; zakres 1–24 |
| `--timeout` | 5 sekund na operację, >0 do 120 |
| `--retries` | 2 dodatkowe próby CPCA, zakres 0–10 |
| `--chmp-only` | Wyłącza CPCA; domyślnie nieaktywne |
| `--cpca-model MODEL` | Powtarzalna lista; domyślnie wszystkie iPF, eksperymentalne poza iPF785 |
| `--email` | Wysyłka raportu po skanie; domyślnie wyłączona |

Bez `--subnet` program używa `ip -j -4 addr show up`. DSM może nie obsługiwać `-j`, a kontener wykryje sieć mostka, nie LAN. Dlatego w DSM zawsze stosuj jawny CIDR.
Linuxowy odczyt `ip -4 addr show` dostarcza adres/prefiks; PowerShell `Get-NetIPConfiguration` nie jest tu używany. Adres/prefiks można przeliczyć przez `ipaddress.ip_interface('ADRES/PREFIKS').network`. Dostęp do innych VLAN wymaga osobnego potwierdzenia tras i jawnych zakresów.

## Wyniki i ręczne uruchomienie

`Container Manager → Kontener → nazwa → Uruchom` wykonuje kolejny skan. Nie uruchamiaj równocześnie kopii kontenera.
Każdy skan tworzy `YYYYMMDDTHHMMSS_mikrosekundyZ/` w UTC:

```text
manifest.json
Canon_<czas>.txt
<IP>/result.json
<IP>/communication.log
<IP>/device_<wersja>.xml       # CHMP
<IP>/counter_<wersja>.xml      # CHMP
<IP>/status.bin               # CPCA
<IP>/status.txt               # CPCA
```

Pliki zależą od protokołu i powodzenia operacji. Adresy niepotwierdzone pozostają w manifeście bez osobnych katalogów. Surowe odpowiedzi potwierdzonych urządzeń są zachowywane. Raport zbiorczy może mieć sekcje z częściowymi danymi; sprawdzaj statusy i błędy.
Kod 0: co najmniej jeden udany odczyt i brak częściowych. Nie oznacza znalezienia wszystkich urządzeń. Kod 1: częściowe wyniki, brak udanych odczytów lub błąd raportu/SMTP. Kod 2: argumenty. Nieobsłużony wyjątek również może przerwać program; zachowaj dziennik.
W pilotażu /24 trwało około 13 minut — oczekiwanie na nieaktywne IP dominuje nad odczytami. To obserwacja, nie limit czasu. Sprawdź `Checked 254/254`, podsumowanie i zapis TXT.

## Harmonogram i powiadomienia

Repozytorium nie włącza harmonogramu. W opisanym pilotażu uruchomienia były ręczne. Automatyzację konfiguruj dopiero po ustaleniu godziny, konta wykonania i sposobu uruchomienia kontenera. Harmonogram DSM wymaga pełnych ścieżek i ochrony przed równoległym skanem; nie włączaj automatycznego restartu jako zamiennika harmonogramu. Ustal retencję, bo raporty nie są automatycznie usuwane.
Zatrzymanie po skanie jest oczekiwane. DSM może wysłać alert „Nieoczekiwane zatrzymanie kontenera” mimo kompletnego raportu; najpierw sprawdź dziennik i kod wyjścia.
Jeśli świadomie wyciszasz to zdarzenie: utwórz własną regułę z wszystkimi zdarzeniami oprócz tego jednego i przypisz ją do profilu odbiorców e-mail zamiast niemodyfikowalnej All. Obejmuje to również rzeczywiste awarie innych kontenerów. Osobny kanał konta Synology/push może nadal wysyłać alerty. Nie wyłączaj wszystkich powiadomień NAS.

## Opcjonalna poczta SMTP

Domyślnie raporty pozostają na NAS. Przed `--email` ustaw:

```text
CANON_SMTP_SENDER=collector@example.com
CANON_SMTP_RECIPIENT=reports@example.com
CANON_SMTP_HOST=smtp.example.com
CANON_SMTP_PASSWORD_FILE=/run/secrets/canon-smtp-password
```

SMTP_SSL używa portu 465 i weryfikacji certyfikatu. Nie wyłączaj jej. Hasło trzymaj w osobnym pliku poza repozytorium i udziałem raportów, z prawami 600/odpowiednim ACL; montuj tylko ten plik jako read-only. Nie wpisuj hasła w polecenie, obraz ani Compose. Bez zmiennej ścieżki moduł szuka `~/.canon-smtp-password`, więc HOME konta musi być właściwe.
Kod wysyła z konta nadawcy do jednego ustawionego adresata. Weryfikacja wysyłki nie była częścią pilotażu NAS. Najpierw obejrzyj wygenerowany TXT, potwierdź adresata i dopiero wykonaj uzgodniony test. Ustawienia powiadomień DSM są niezależne od SMTP kolektora.

## Aktualizacja i wycofanie

Zatrzymaj skany, zachowaj poprzednie trzy pliki, konfigurację kontenera i identyfikator obrazu. Podmień moduły jako komplet i przetestuj jeden IP. W razie błędu przywróć pliki/konfigurację; nie przywracaj całego DSM. Zachowaj raporty, nie usuwaj obrazu używanego przez inne aplikacje. Publikacja na GitHubie nie aktualizuje plików na NAS.
