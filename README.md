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
aktualisieren sich danach halbsekündlich.

### Bedienung

* **Frequenz**: Direkteingabe (z. B. `107.9` MHz oder `107900000` Hz) oder
  Schrittweise mit `▼`/`▲` (entspricht dem Drehencoder)
* **Band / Modus / Schrittweite / Bandbreite / AGC**: Hoch-/runter-Schalten
* **Lautstärke**: Schieberegler (0–63)
* **Speicherplätze**: Anzeigen (`$`), aktuellen Sender in einen Slot
  schreiben (`#`), Slot löschen (Frequenz 0). Das Aufrufen eines Slots erfolgt
  am Radio selbst – dafür gibt es im Protokoll keinen Befehl.
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
├── app.py             # Tkinter-Oberfläche
├── client.py          # TCP-Client mit Lese-Thread
├── mock_receiver.py   # Nachbau des Radio-Fernsteuerprotokolls (Demo/Test)
└── protocol.py        # Ad-hoc-Protokoll: Befehle, Status, Screenshot-Decode
tests/                 # Unit- und Integrationstests
```

## Hinweise

* Die TCP-Steuerung ist unverschlüsselt und ohne Anmeldung – wie in der
  Firmware-Dokumentation beschrieben nur in vertrauenswürdigen Netzen
  verwenden.
* Detailbeschreibung des Protokolls:
  [Remote control (ats-mini docs)](https://esp32-si4732.github.io/ats-mini/remote.html)
