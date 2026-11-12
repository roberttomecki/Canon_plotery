# Canon Plotery

Narzędzia do zdalnego odczytu liczników z ploterów Canon w sieci lokalnej. Zamiast chodzić do każdego urządzenia i spisywać liczniki z panelu, uruchamiasz skrypt, a on sam pyta plotery o model, numer seryjny, zużycie papieru i atramentu, a potem zapisuje wszystko w raporcie.

Skrypty **tylko czytają**: nie wysyłają wydruków i nie zmieniają ustawień ploterów.

## Którą wersję wybrać?

Są dwie wersje, każda do czego innego:

| Wersja | Kiedy jej użyć | Jak uruchomić | Co dostajesz |
| --- | --- | --- | --- |
| [Komputer](desktop/README.md) | Chcesz szybko sprawdzić jeden lub kilka ploterów ze swojego komputera z Windows (na Linuksie też działa, ale trzeba podać adres IP lub podsieć) | `Canon_plotery.cmd` albo bezpośrednio Python | Raport TXT i HTML, log, a przy CPCA także surowy plik BIN |
| [NAS](nas/README.md) | Chcesz, żeby NAS sam przeskanował całą sieć i zrobił jeden zbiorczy raport | Kontener z Pythonem albo z linii poleceń | Manifest JSON, raport TXT, surowe odpowiedzi XML/BIN i logi |

Potrzebny jest tylko Python 3.10 lub nowszy. Nie trzeba niczego doinstalowywać przez pip.

Co jeszcze jest w repozytorium:

- `Canon_CHMP.py` w katalogu głównym to starszy, samodzielny czytnik CHMP. Zostawiłem go dla porządku.
- `desktop/Canon_plotery.cmd` to nowy uruchamiacz dla Windows, napisany od zera. To nie jest odzyskana kopia dawnego `Canon_CHMP.cmd`.
- `apk/` zawiera dotychczasowe wersje aplikacji Android „Canon Liczniki” (1.1–1.4), bez zmian.

## Jak to rozmawia z ploterami

Plotery Canon odpowiadają na jeden z dwóch protokołów:

- **CHMP (TCP, port 80)**: nowsze plotery. Skrypt wysyła zapytanie POST (GetCapability/device i GetStatus/counter), a potem odbiera odpowiedź przez GET.
- **CPCA (UDP, port 47545)**: starsze iPF. Skrypt otwiera sesję, pyta o model i pobiera tekstowy raport stanu. Na pewno działa z **iPF785**. Pozostałe modele iPF w wersji NAS są eksperymentalne.

Obie wersje próbują różnych wersji CHMP, ale nie w identyczny sposób:

- NAS próbuje kolejno 1.3.0, 1.0.0 i 1.4.0.
- Komputer w trybie auto próbuje 1.3.0 i 1.0.0.

### Co zostało sprawdzone w praktyce

12.11.2026 zrobiłem pilotaż na NAS-ie Synology **DS223j** (Realtek RTD1619B, 1 GB RAM, DSM **7.4.1-90080 Update 1**, Container Manager **24.0.2-1706**). Wynik pełnego skanu sieci /24:

- sprawdzone 254 adresy;
- dwa udane odczyty przez CHMP: **TX-3000** i **TM-610M**;
- zero odczytów częściowych;
- w raporcie TX-3000 identyfikacja i liczniki miały status OK.

Uczciwie trzeba dodać, że to nie dowodzi obsługi wszystkich modeli. CPCA na NAS-ie też nie zostało jeszcze sprawdzone.

## Jak czytać wyniki

Kilka rzeczy, na które łatwo się nabrać:

- **Ekwiwalent A4 i powierzchnia A4** to dwa osobne pola, ale druga wartość to tylko przeliczenie pierwszej (A4 × 0,06237 m²). Nie traktuj jej jak niezależnego licznika powierzchni.
- **Jednostki `amount` i `area_square`** mogą być surowe, tak jak podał je ploter. Nie zakładaj z góry, że to ml albo m². Jeśli w kodzie jest jakieś przeliczenie dla danego modelu, porównaj je z raportem wydrukowanym przez sam ploter.
- **Brak odpowiedzi albo brak pola to nie zero.** Oznacza tylko, że nie udało się tego odczytać.
- **Skan nie znajdzie wszystkiego.** Wykrywa urządzenia, które odpowiadają na CHMP lub CPCA. Ploter uśpiony, wyłączony albo schowany za zaporą lub w innym VLAN-ie może się nie pokazać.

Jeśli liczniki mają posłużyć do rozliczeń, najpierw porównaj model, numer seryjny, liczniki i jednostki z tym, co pokazuje urządzenie. Nie ma tu automatycznego importu do Princity.

## Prywatność

Raporty i logi zawierają numery seryjne, adresy IP i dane o eksploatacji. **Nie wrzucaj ich na GitHuba**, haseł tym bardziej.

Wszystkie przykłady używają „dokumentacyjnej” sieci 192.0.2.0/24, która nie istnieje naprawdę. Podstaw swój zakres adresów, na skanowanie którego masz zgodę.

Wersja NAS w repozytorium różni się od tej z pilotażu tylko konfiguracją poczty. Adresy e-mail są teraz brane ze zmiennych środowiskowych, a wysyłka jest opcjonalna.

Wdrożenie na NAS-ie nie aktualizuje DSM, nie instaluje systemowego Pythona i nie wymaga kontenera z podwyższonymi uprawnieniami.

## Szybki test na własnym komputerze

```sh
python -B -m unittest discover -s tests -v
python -B desktop/Canon_plotery.py --help
python -B nas/app/canon_collector.py --help
```

Testy działają na spreparowanych odpowiedziach, więc nie łączą się z siecią ani z serwerem pocztowym. Sprawdzają kod, ale nie zastąpią próby na prawdziwych ploterach. Szczegóły instalacji i utrzymania są w README każdej z wersji.
