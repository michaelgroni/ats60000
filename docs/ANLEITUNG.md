# ATS-Mini Fernbedienung – Anleitung für Windows

Dieses Programm steuert Ihr **ATS-Miniradio** über das WLAN – ganz ohne
Kabel und ohne Installation. Sie brauchen keine Computerkenntnisse.

Hinweis: Das Programmfenster lässt sich unter **Ansicht → Sprache** auch
auf Englisch umschalten. Diese Anleitung beschreibt die deutsche
Oberfläche.

## Installation

1. Öffnen Sie die Programmseite auf GitHub:
   [github.com/michaelgroni/ats60000/releases](https://github.com/michaelgroni/ats60000/releases)
2. Laden Sie auf der Seite im Abschnitt **Latest** (neuestes Release)
   die dort angebotene EXE-Datei herunter -- im Beispiel heißt sie
   **ATS-Mini-Remote-0.3.exe**, bei neueren Versionen entsprechend
   **ATS-Mini-Remote-<Versionsnummer>.exe**
   (z. B. in den Ordner *Downloads*).
3. Fertig. Die Datei braucht nicht entpackt zu werden und es muss nichts
   installiert werden. Am besten heben Sie sie an einem festen Ort auf,
   z. B. auf dem Desktop.

### Erste Warnung von Windows

Beim allerersten Start zeigt Windows möglicherweise einen blauen Hinweis:
*„Windows hat Ihren PC geschützt."*

Das ist normal: Windows kennt das Programm noch nicht. Klicken Sie auf
**Weitere Informationen** und dann auf **Trotzdem ausführen**. Das Programm
startet dann ganz normal.

## Vorbereitung am Radio

Das Radio muss mit Ihrem WLAN verbunden sein und die Fernsteuerung
eingeschaltet haben:

1. Am Radio: **Settings → Wi-Fi** → wählen Sie *AP Only*, *AP+Connect*
   oder *Connect*.
2. Am Radio: **Settings → TCP Port** → wählen Sie *Ad hoc*.

## Verbindung herstellen

1. Starten Sie die heruntergeladene Datei (z. B. **ATS-Mini-Remote-0.3.exe**) mit
   Doppelklick.
2. Bei **Host** tragen Sie die Adresse des Radios ein. Das ist meistens
   `atsmini.local`. Alternativ steht die Adresse (eine Zahl wie
   `192.168.1.42`) im Display des Radios, während es mit dem WLAN
   verbunden ist.
3. Bei **Port** steht bereits die richtige Zahl (60000) – bitte nicht
   ändern.
4. Klicken Sie auf **Verbinden**.

Das Programm versucht beim Start auch von selbst, das Radio zu erreichen
(automatischer Verbindungsversuch). Klappt das nicht, passiert nichts
Schlimmes – klicken Sie einfach selbst auf **Verbinden**.

Das Programm zeigt nun unten im Fenster laufend den Zustand des Radios an,
z. B. die Batteriespannung. Die Frequenzanzeige oben hat feste Zellen:
Der Dezimalpunkt bleibt beim Verstellen immer an derselben Stelle,
führende leere Zellen bleiben dunkel.

## Bedienung

### Sendefrequenz einstellen

- **Zahl eintippen:** Geben Sie die Frequenz in das Feld oben ein,
  z. B. `7.2` mit der Einheit *MHz*, und klicken Sie auf **Setzen**.
  Es funktioniert auch `7,2` – Komma oder Punkt sind gleichwertig.
- **Schrittweise:** Mit den Knöpfen **◀** und **▶** neben *Frequenz*
  gehen Sie in kleinen Schritten vorwärts und zurück – wie am
  Steller am Radio.

### Weitere Einstellungen

Jede Zeile (**Schrittweite, Band, Modus, Bandbreite, AGC/Attn**) hat
ebenfalls **◀**- und **▶**-Knöpfe: Damit schalten Sie die Werte hoch und
runter, wie Sie es vom Radio-Menü kennen.

### Lautstärke

Der Schieberegler **Lautstärke** stellt die Radiolautstärke ein. Der
neue Wert wird erst übertragen, wenn Sie den Regler loslassen.

### Rauschsperre

Die **Rauschsperre** (nur bei AM und FM) blendet störendes Rauschen aus,
wenn kaum ein Signal ankommt. Stellen Sie die **Empfindlichkeit** auf dem
Regler ein und aktivieren Sie das Häkchen daneben. Sinkt das Signal zu
weit ab, wird das Radio kurzzeitig stumm; kommt das Signal zurück, ist
die Lautstärke wieder wie vorher. Bei SSB ist die Rauschsperre
ausgegraut – sie funktioniert dort nicht.

### Pegel ablesen (S-Meter)

Rechts sehen Sie eine Anzeige wie ein altes Messgerät mit Zeiger:

- **Pegel**: wie stark das Signal ankommt (in dBµV)
- **S-Wert**: die übliche Kurzwellen-Angabe wie *S9*, auch *S9+20* und
  höher
- **SNR**: wie klar das Signal ist (in dB)

Klicken Sie die kleinen runden Knöpfe an, um zwischen den drei Anzeigen
zu wechseln. Der rote Bereich rechts bedeutet: sehr starkes Signal.

### Spektrum (Übersicht über das ganze Band)

Klicken Sie auf **Sweep starten**, um das gesamte Band einmal abzutasten.
Das Programm zeigt dann ein Bild, in dem Sie auf einen Blick sehen,
wo starke Sender sind:

- Grüne Fläche = momentane Signalstärke
- Fläche in blasserem Grün = frühere Signalspitzen (kann beim letzten
  Durchlauf stärker gewesen sein)

Klicken Sie auf eine Stelle im Bild, um das Radio direkt auf diese
Frequenz zu tunen. Das geht auch, wenn noch kein Sweep gelaufen ist –
das Programm nimmt dann den Bereich des aktuellen Bands. Unter dem Bild
sehen Sie den Fortschritt, während das Programm misst.

### Speicherplätze

Die Tabelle **Speicherplätze** rechts neben den Einstellungen zeigt immer,
was im Radio gespeichert ist:

- **Anzeigen ($)**: listet die gespeicherten Sender des Radios auf
- **Aktuellen Sender speichern (#)**: legt den aktuellen Sender auf einen
  freien Platz
- **Löschen**: entfernt einen Slot (Frequenz 0)

Das Aufrufen eines gespeicherten Senders erfolgt am Radio selbst – dafür
kennt das Fernsteuerprotokoll keinen Befehl.

### Weitere Knöpfe

- **Screenshot**: macht ein Bild des Radiodisplays und kann es als
  Datei speichern
- **Trennen**: beendet die Verbindung zum Radio

### Log (Expertenansicht)

Unter **Ansicht → Log anzeigen** blenden Sie eine Tabelle ein, in der das
Programm alle Kommunikation mit dem Radio mitgeschrieben hat (Zeit,
Quelle, Nachricht). Für die normale Bedienung brauchen Sie sie nicht –
sie hilft bei Problemen.

## Wenn etwas nicht funktioniert

| Problem | Lösung |
|---|---|
| „Nicht verbunden" | Klicken Sie auf **Verbinden** und prüfen Sie, ob die Adresse stimmt. |
| Verbindung kommt nicht zustande | Radio und Computer müssen im gleichen WLAN sein. Prüfen Sie am Radio: **Settings → Wi-Fi** und **Settings → TCP Port → Ad hoc**. |
| Radio reagiert nicht | Schalten Sie das Radio einmal aus und wieder ein, und verbinden Sie erneut. |
| Windows warnt beim Start | Nur beim allerersten Start normal: **Weitere Informationen** → **Trotzdem ausführen**. |

## Programm beenden

Schließen Sie einfach das Fenster. Die Einstellungen am Radio bleiben
erhalten.
