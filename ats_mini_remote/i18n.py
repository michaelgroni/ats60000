"""Lokalisierung der Oberflaeche.

Aufbau: Pro Sprache ein Woerterbuch, das Schluessel auf Texte abbildet.
Die Oberflaeche fragt Texte ueber _() ab; fehlt ein Schluessel, faellt
die Anzeige auf Deutsch zurueck. Neue Sprachen lassen sich einfach als
zusaetzliches Woerterbuch in LANGUAGES ergaenzen.
"""

from __future__ import annotations

from typing import Callable

DE = {
    # Verbindung
    "app_title": "ATS-Miniradio V1 – WLAN-Fernbedienung",
    "connection": "Verbindung",
    "host": "Host:",
    "port": "Port:",
    "connect": "Verbinden",
    "disconnect": "Trennen",
    "connected": "Verbunden",
    "disconnected": "Getrennt",
    # Status
    "receiver": "Empfänger",
    "frequency": "Frequenz",
    "band": "Band",
    "mode": "Modus",
    "signal_strength": "Signalstärke",
    "s_value": "S-Wert",
    "snr": "SNR",
    "battery": "Batterie",
    # Steuerung
    "controls": "Steuerung",
    "step_size": "Schrittweite",
    "volume": "Lautstärke",
    "bandwidth": "Bandbreite",
    "agc_attn": "AGC/Attn",
    "agc_on": "AGC ein",
    "squelch": "Rauschsperre",
    "squelch_sens": "Empfindlichkeit",
    # S-Meter
    "metric_rssi": "Signalstärke",
    "metric_s": "S-Wert",
    "metric_snr": "SNR",
    # Speicher
    "memories": "Speicherplätze",
    "slot": "Slot:",
    "save_current": "Aktuellen Sender speichern (#)",
    "clear_slot": "Slot löschen",
    "col_slot": "Slot",
    "col_band": "Band",
    "col_frequency": "Frequenz",
    "col_mode": "Modus",
    # Spektrum
    "spectrum": "Spektrum",
    "points": "Messpunkte:",
    "sweep_start": "Sweep starten",
    "sweep_stop": "Abbrechen",
    "sweep_done": "Fertig",
    "sweep_cancelled": "Abgebrochen",
    # Screenshot
    "display": "Display",
    "screenshot": "Screenshot (C)",
    "save_as": "Speichern…",
    "no_screenshot": "Kein Screenshot",
    "receiving": "Empfange… {percent} %",
    # Log
    "log": "Log",
    "show_log": "Log anzeigen",
    "hide_log": "Log ausblenden",
    "col_time": "Zeit",
    "col_source": "Quelle",
    "col_message": "Nachricht",
    "col_kind": "Art",
    "col_step": "Schritt",
    "col_bw": "BW",
    "col_agc": "AGC",
    "col_vol": "Vol",
    "col_rssi": "RSSI",
    "col_snr": "SNR",
    "col_volt": "U",
    "log_kind_status": "Status",
    # Menue
    "menu_view": "Ansicht",
    "menu_help": "Hilfe",
    "menu_language": "Sprache",
    "menu_website": "Website",
    "menu_about": "Über",
    # Meldungen
    "err_no_host": "Bitte Host angeben",
    "err_invalid_port": "Ungültiger Port",
    "err_connect_failed": "Verbindung fehlgeschlagen",
    "err_invalid_frequency": "Ungültige Frequenzeingabe",
    "err_no_status": "Kein Status vom Empfänger",
    "err_invalid_slot": "Ungültiger Slot",
    "err_no_screenshot": "Kein Screenshot vorhanden",
    "not_connected_cmd": "Nicht verbunden – Befehl ignoriert",
    "not_connected_sweep": "Nicht verbunden – Sweep nicht möglich",
    "not_connected_shot": "Nicht verbunden – Screenshot nicht möglich",
    "no_status_tune": "Kein Status – Frequenzschritt nicht möglich",
    "no_status_sweep": "Kein Status – Sweep nicht möglich",
    "freq_out_of_band": "Frequenz außerhalb des Bands",
    "freq_out_of_band_step": "Frequenz außerhalb des Bands – Schritt ignoriert",
    "band_unknown_sweep": "Band '{band}' unbekannt – Sweep nicht möglich",
    "band_too_narrow": "Band zu schmal für diese Schrittweite – Sweep nicht möglich",
    "connected_with": "Verbunden mit {host}:{port}, Monitor aktiviert",
    "disconnected_log": "Getrennt",
    "connection_lost": "Verbindung getrennt: {reason}",
    "log_source_app": "Programm",
    "log_source_radio": "Radio",
    "screenshot_saved": "Screenshot gespeichert: {filename}",
    "log_sweep_setup_conflict": ("{name} nicht bestätigt ({target}) "
                                 "– Sweep trotzdem fortgesetzt"),
    "log_point_skipped": ("Keine Bestätigung für {freq} kHz "
                          "– Punkt übersprungen"),
    "log_sweep_summary": "Sweep {message}: {points} Punkte",
    "log_sweep_over": ("Sweep über {band}: {lo}–{hi} kHz, {points} Punkte, "
                       "Schrittweite {step}, Bandbreite {bw}"),
    "log_sweep_mode": ("Modus für Sweep: {mode} (vorher {old}, "
                       "wird zurückgestellt)"),
    "log_tuned": "Abgestimmt auf {freq} kHz",
    "memories_refreshed": "Speicherplätze aktualisiert",
    "sweep_setup_names_mode": "Modus",
    "sweep_setup_names_step": "Schrittweite",
    "set": "Setzen",
    "error": "Fehler",
    "menu_about_version": "Version",
    "menu_about_project": "Projektseite",
}

EN = {
    "app_title": "ATS-Mini Radio V1 – WLAN Remote Control",
    "connection": "Connection",
    "host": "Host:",
    "port": "Port:",
    "connect": "Connect",
    "disconnect": "Disconnect",
    "connected": "Connected",
    "disconnected": "Disconnected",
    "receiver": "Receiver",
    "frequency": "Frequency",
    "band": "Band",
    "mode": "Mode",
    "signal_strength": "Signal strength",
    "s_value": "S-value",
    "snr": "SNR",
    "battery": "Battery",
    "controls": "Controls",
    "step_size": "Step size",
    "volume": "Volume",
    "bandwidth": "Bandwidth",
    "agc_attn": "AGC/Attn",
    "agc_on": "AGC on",
    "squelch": "Squelch",
    "squelch_sens": "Sensitivity",
    "metric_rssi": "Signal strength",
    "metric_s": "S-value",
    "metric_snr": "SNR",
    "memories": "Memory slots",
    "slot": "Slot:",
    "save_current": "Save current station (#)",
    "clear_slot": "Clear slot",
    "col_slot": "Slot",
    "col_band": "Band",
    "col_frequency": "Frequency",
    "col_mode": "Mode",
    "spectrum": "Spectrum",
    "points": "Points:",
    "sweep_start": "Start sweep",
    "sweep_stop": "Cancel",
    "sweep_done": "Done",
    "sweep_cancelled": "Cancelled",
    "display": "Display",
    "screenshot": "Screenshot (C)",
    "save_as": "Save…",
    "no_screenshot": "No screenshot",
    "receiving": "Receiving… {percent} %",
    "log": "Log",
    "show_log": "Show log",
    "hide_log": "Hide log",
    "col_time": "Time",
    "col_source": "Source",
    "col_message": "Message",
    "col_kind": "Kind",
    "col_step": "Step",
    "col_bw": "BW",
    "col_agc": "AGC",
    "col_vol": "Vol",
    "col_rssi": "RSSI",
    "col_snr": "SNR",
    "col_volt": "V",
    "log_kind_status": "Status",
    "menu_view": "View",
    "menu_help": "Help",
    "menu_language": "Language",
    "menu_website": "Website",
    "menu_about": "About",
    "err_no_host": "Please enter a host",
    "err_invalid_port": "Invalid port",
    "err_connect_failed": "Connection failed",
    "err_invalid_frequency": "Invalid frequency input",
    "err_no_status": "No status from the receiver",
    "err_invalid_slot": "Invalid slot",
    "err_no_screenshot": "No screenshot available",
    "not_connected_cmd": "Not connected – command ignored",
    "not_connected_sweep": "Not connected – sweep not possible",
    "not_connected_shot": "Not connected – screenshot not possible",
    "no_status_tune": "No status – frequency step not possible",
    "no_status_sweep": "No status – sweep not possible",
    "freq_out_of_band": "Frequency outside the band",
    "freq_out_of_band_step": "Frequency outside the band – step ignored",
    "band_unknown_sweep": "Band '{band}' unknown – sweep not possible",
    "band_too_narrow": ("Band too narrow for this step size "
                        "– sweep not possible"),
    "connected_with": "Connected to {host}:{port}, monitor activated",
    "disconnected_log": "Disconnected",
    "connection_lost": "Connection lost: {reason}",
    "log_source_app": "Program",
    "log_source_radio": "Radio",
    "screenshot_saved": "Screenshot saved: {filename}",
    "log_sweep_setup_conflict": ("{name} not confirmed ({target}) "
                                 "– sweep continued anyway"),
    "log_point_skipped": "No confirmation for {freq} kHz – point skipped",
    "log_sweep_summary": "Sweep {message}: {points} points",
    "log_sweep_over": ("Sweep over {band}: {lo}–{hi} kHz, {points} points, "
                       "step size {step}, bandwidth {bw}"),
    "log_sweep_mode": ("Mode for sweep: {mode} (previously {old}, "
                       "will be restored)"),
    "log_tuned": "Tuned to {freq} kHz",
    "memories_refreshed": "Memory slots updated",
    "sweep_setup_names_mode": "Mode",
    "sweep_setup_names_step": "Step size",
    "set": "Set",
    "error": "Error",
    "menu_about_version": "Version",
    "menu_about_project": "Project page",
}

LANGUAGES: dict[str, dict[str, str]] = {"Deutsch": DE, "English": EN}

_current = DE


def available() -> list[str]:
    """Namen aller verfuegbaren Sprachen."""
    return list(LANGUAGES)


def set_language(name: str) -> None:
    """Aktive Sprache umschalten (unbekannter Name: Deutsch)."""
    global _current
    _current = LANGUAGES.get(name, DE)


def current() -> str | None:
    """Name der aktiven Sprache oder None bei Fallback."""
    for name, table in LANGUAGES.items():
        if table is _current:
            return name
    return None


def get_translator() -> Callable[..., str]:
    """Uebersetzungsfunktion fuer die aktive Sprache.

    Aufruf: t("schluessel", **platzhalter); fehlende Schluessel und
    Platzhalter bleiben unersetzt stehen, sodass Luecken auffallen.
    """
    def translate(key: str, **kwargs) -> str:
        text = _current.get(key) or DE.get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    return translate
