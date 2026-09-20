# ATS-Mini WLAN-Fernbedienung

Desktop-Fernbedienung für das **ATS-Miniradio V1** (ESP32-S3 + SI4732) über WLAN.
Die Anwendung verbindet sich mit dem integrierten TCP-Fernsteuerport der
Firmware (Ad-hoc-Protokoll, Port 60000) – am Radio muss **nichts umgebaut oder
geflasht** werden.

Geschrieben in Python, nur Standardbibliothek (Tkinter für die Oberfläche) –
keine Zusatzpakete nötig.

## Voraussetzungen

* Python 3.10 oder neuer (mit Tkinter; unter Debian/Ubuntu: `python3-tk`)
* ATS-Miniradio mit der Community-Firmware
  [esp32-si4732/ats-mini](https://github.com/esp32-si4732/ats-mini)
  (funktioniert für V1; die offizielle chinesische Firmware unterstützt das
  TCP-Protokoll ebenfalls ab den neueren Versionen)

## Am Radio einstellen

1. `Settings → Wi-Fi` → `AP Only`, `AP+Connect` oder `Connect`
   (im AP-Modus heißt das Netz `ATS-Mini`, ohne Passwort).
2. `Settings → TCP Port` → `Ad hoc`

Das Radio lauscht dann auf TCP-Port **60000** – im WLAN unter
`atsmini.local` bzw. der im Display angezeigten IP-Adresse erreichbar.

## Anwendung starten

```shell
python3 -m ats_mini_remote
```

Dann Host (`atsmini.local` oder IP) und Port 60000 eintragen und auf
**Verbinden** klicken. Beim Verbinden wird der Statusmonitor automatisch
aktiviert; Frequenz, Band, Modus, Signalstärke, SNR und Batteriespannung
aktualisieren sich laufend (etwa alle 50 ms).

Zahlen mit Nachkommastellen (Frequenz, Spannung, Achsenbeschriftung) folgen
dem Dezimaltrenner des Betriebssystem-Locales (also Komma im deutschen
System); die Frequenzeingabe akzeptiert Punkt und Komma.

### Bedienung

* **Frequenz**: Direkteingabe (z. B. `107.9` MHz) oder schrittweise mit
  `◀`/`▶`. Jede eingestellte Frequenz ist ein Vielfaches der aktuellen
  Schrittweite – auch nach Klick ins Spektrum.
* **Schrittweite / Lautstärke / Band / Modus / Bandbreite / AGC/Attn**:
  je eine Zeile mit `◀`/`▶`-Buttons, der aktuelle Wert steht dazwischen.
  Die Lautstärke (0–63) wird als Schieberegler erst beim Loslassen
  gesendet – Ziehen am Regler erzeugt keinen Befehlsburst.
* **S-Meter**: Analoge Zeigerinstrument-Anzeige rechts der Steuerleiste,
  umschaltbar per Radiobutton zwischen Signalstärke (dBµV), S-Wert
  (S1 … S9 mit Bereich +10 … +60 dB darüber) und SNR (dB). Der obere
  Skalenbereich ist rot markiert; die Wertziffer färbt sich dort rot.
* **Spektrum**: Manueller Band-Sweep auf Knopfdruck. Die Zahl der
  Messpunkte wird abhängig von der Bandbreite des eingestellten Bands
  empfohlen (z. B. mehr Punkte im VHF-Band), lässt sich aber frei
  einstellen. Das Programm wählt passend dazu die feinmögliche
  Schrittweite und eine Bandbreite nach Punktabstand, vermisst das Band
  und interpoliert die Fläche lückenlos (grün). Zurückschauen in der
  Zeit: ein blasseres Polygon zeigt den Verlauf aus vorherigem Wert und
  gleitendem Mittelwert (Peak-Hold je Frequenz). Ein Klick ins Spektrum
  stimmt die Frequenz an dieser Stelle an (auf dem Schrittweiten-Raster).
* **Speicherplätze**: Anzeigen (`$`), aktuellen Sender in einen Slot
  schreiben (`#`), Slot löschen (Frequenz 0). Das Aufrufen eines Slots
  erfolgt am Radio selbst – dafür gibt es im Protokoll keinen Befehl.
* **Screenshot**: Fängt das Radio-Display ab (BMP) und zeigt es an;
  speicherbar als Datei.
* **Log**: Rohdaten der Verbindung im unteren Bereich.

## Ohne Radio testen (Mock-Server)

Zum Ausprobieren der Oberfläche ohne Empfangsgerät liegt ein
Protokollnachbau des Radios bei:

```shell
python3 -m ats_mini_remote.mock_receiver
```

Danach in der Anwendung `localhost` als Host verwenden. Der Mock bedient
Bänder (LW/MW/SW/80m/VHF), Modi (FM/AM/LSB/USB), Frequenz-, Lautstärke- und
Speicherbefehle und erzeugt Screenshots.

## Tests

```shell
python3 -m unittest discover -s tests -v
```

## Projektstruktur

```
ats_mini_remote/
├── __init__.py
├── __main__.py        # Einstieg: python3 -m ats_mini_remote
├── app.py             # Tkinter-Oberfläche, Spektrum, S-Meter
├── client.py          # TCP-Client mit Lese-Thread und Send-Guard
├── mock_receiver.py   # Nachbau des Radio-Fernsteuerprotokolls (Demo/Test)
└── protocol.py        # Ad-hoc-Protokoll: Befehle, Status, Sweep-Planung,
                      # S-Wert-Tabelle, Locale-Zahlenformate
tests/                 # Unit- und Integrationstests
```

## Lizenz

[MIT](LICENSE) – Verwendung, Änderung und Weitergabe sind frei,
solange der Copyright-Hinweis erhalten bleibt.

## Hinweise

* Die TCP-Steuerung ist unverschlüsselt und ohne Anmeldung – wie in der
  Firmware-Dokumentation beschrieben nur in vertrauenswürdigen Netzen
  verwenden.
* Detailbeschreibung des Protokolls:
  [Remote control (ats-mini docs)](https://esp32-si4732.github.io/ats-mini/remote.html)
