# Canon Plotery — kolektory komputerowy i NAS

Odczyt identyfikacji, liczników papieru i atramentu ploterów Canon przez sieć lokalną. Dwie wersje mają różne sposoby pracy:

| Wersja | Zastosowanie | Start | Wyniki |
| --- | --- | --- | --- |
| [Komputer](desktop/README.md) | Interaktywny odczyt na Windows; Linux z jawnym IP/CIDR | `Canon_plotery.cmd` lub Python | TXT, HTML, log, dla CPCA również BIN |
| [NAS](nas/README.md) | Bezobsługowy jednorazowy skan i raport zbiorczy | Kontener Python lub CLI | Manifest JSON, TXT, surowe XML/BIN i logi |

Python 3.10+ i biblioteki standardowe; nie trzeba instalować pakietów pip.
Oryginalny `Canon_CHMP.py` w katalogu głównym pozostaje starszym, samodzielnym czytnikiem CHMP. Nowy uruchamiacz Windows to `desktop/Canon_plotery.cmd` (nie odzyskana kopia dawnego Canon_CHMP.cmd).
Katalog `apk/` z dotychczasowymi wydaniami Android pozostaje bez zmian.

## Protokoły i potwierdzone działanie

- **CHMP, TCP 80:** GetCapability/device i GetStatus/counter; HTTP POST przekazuje żądanie odczytu, następnie GET odbiera odpowiedź. Nie są wysyłane zadania drukowania ani zmiany konfiguracji.
- **CPCA, UDP 47545:** inicjalizacja sesji, identyfikacja modelu i pobranie tekstowego raportu statusowego. Lokalna implementacja oznacza iPF785 jako sprawdzony; pozostałe iPF w wersji NAS są eksperymentalne.
- Pilotaż NAS 12.11.2026: Synology **DS223j**, Realtek RTD1619B, 1 GB RAM, DSM **7.4.1-90080 Update 1**, Container Manager **24.0.2-1706**. Pełny skan /24: 254 adresy, dwa udane odczyty **TX-3000 i TM-610M przez CHMP**, zero częściowych. Raport TX-3000 miał status identyfikacji i liczników OK. To nie potwierdza obsługi wszystkich modeli ani CPCA na NAS.
- Wersja NAS próbuje CHMP 1.3.0, 1.0.0, 1.4.0; wersja komputerowa w auto: 1.3.0 i 1.0.0. Nie są to identyczne algorytmy.

## Znaczenie wyników

Ekwiwalent A4 i powierzchnia A4 × 0,06237 m² są odrębnymi polami raportu; druga wartość jest przeliczeniem. Nie traktuj jej jako niezależnego licznika powierzchni. Jednostki `amount` i `area_square` mogą pozostać surowe. Nie uznawaj ich automatycznie za ml/m². Ewentualne przeliczenia modelowe w kodzie wymagają porównania z raportem danego plotera.
Brak odpowiedzi lub brak pola nie oznacza zera. Wykrywane są urządzenia odpowiadające na obsługiwane protokoły; skan nie gwarantuje odnalezienia każdego urządzenia, zwłaszcza uśpionego, odłączonego lub odfiltrowanego przez zaporę/VLAN.
Przed użyciem rozliczeniowym porównaj model, numer seryjny, liczniki i jednostki z urządzeniem. Nie ma tu automatycznego importu do Princity.

## Prywatność i utrzymanie

Raporty mogą zawierać numery seryjne, IP i informacje eksploatacyjne. Nie publikuj raportów, logów ani haseł w GitHubie. Przykłady używają dokumentacyjnej sieci 192.0.2.0/24 — zastąp ją własnym zatwierdzonym zakresem.
Wersja repozytoryjna NAS różni się od pilotażu konfiguracją SMTP: adresy są pobierane ze zmiennych środowiskowych, poczta pozostaje opcjonalna.
Wdrożenie nie aktualizuje DSM, nie instaluje systemowego Pythona i nie wymaga uprzywilejowanego kontenera.

## Sprawdzenie lokalne

```sh
python -B -m unittest discover -s tests -v
python -B desktop/Canon_plotery.py --help
python -B nas/app/canon_collector.py --help
```

Testy używają odpowiedzi syntetycznych i nie łączą się z siecią ani SMTP. Nie zastępują pilotażu urządzeń. Instrukcje instalacji i utrzymania znajdują się w README obu wersji.
