# Hoval Gateway V2 - CAN-BUS to MQTT Bridge

Ein Python-basiertes Gateway, das Hoval Lüftungs-/Heizungssysteme (HV-Geräte) über CAN-BUS mit MQTT-Brokern verbindet. Ideal für die Integration in Home Automation Systeme wie Home Assistant, ioBroker oder OpenHAB.

## Features

- **Echtzeit-Datenübertragung**: Kontinuierliches Auslesen von Sensor- und Statusdaten
- **MQTT-Integration**: Publiziert alle Werte als JSON-Nachrichten mit Retained Flag
- **Home Assistant Auto-Discovery**: Automatische Sensor-Registrierung - keine manuelle Konfiguration nötig!
- **Intelligente Filterung**: 9-schichtige Fehlercode-Erkennung und Plausibilitätsprüfung
- **Hybrid-Modus**: CSV-basierte Datenpunkt-Konfiguration + direkte Temperatur-Erfassung
- **Automatische Wiederverbindung**: Robuste Fehlerbehandlung bei Netzwerkproblemen
- **Deutsche Datenpunkt-Namen**: Automatische Normalisierung für MQTT (Umlaute → ASCII)
- **Kein MODBUS-Gateway nötig**: Direktverbindung über Hoval Netzwerk-Modul (LAN/WIFI)

## Voraussetzungen

### Hardware
- Hoval Lüftungsgerät (HomeVent Serie) mit CAN-BUS-Schnittstelle
- **Hoval Netzwerk-Modul (LAN oder WIFI)** - kein MODBUS-Gateway erforderlich!
- MQTT-Broker (z.B. Mosquitto)

### Software
- Python 3.x
- Bibliothek: `paho-mqtt`

## Installation

### Debian/Ubuntu (Empfohlen)

Das einfachste ist die Installation über das fertige `.deb`-Paket:

```bash
# Paket von GitHub Releases herunterladen
wget https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/releases/latest/download/hoval-gateway_2.4.0_all.deb

# Installieren
sudo apt install ./hoval-gateway_2.4.0_all.deb

# Konfiguration anpassen
sudo nano /opt/hoval-gateway/config.ini

# Service starten
sudo systemctl enable --now hoval-gateway

# Logs anzeigen
tail -f /var/log/hoval-gateway/hoval.log
```

Das Paket installiert:
- Anwendung nach `/opt/hoval-gateway/`
- Systemd-Service `hoval-gateway.service`
- Log-Rotation nach `/var/log/hoval-gateway/`
- Dedizierter `hoval` System-Benutzer

### Manuelle Installation

1. **Repository klonen oder Dateien herunterladen**:
   ```bash
   git clone https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT.git
   cd Hoval-GatewayV2-CANBUS-MQTT
   ```

2. **Abhängigkeiten installieren**:
   ```bash
   pip install paho-mqtt
   ```

3. **Konfiguration anpassen** (siehe unten)

## Konfiguration

Alle Einstellungen werden in der Datei `config.ini` vorgenommen:

```ini
[hoval]
# IP-Adresse des Hoval-Geräts
ip = 10.0.0.95
# CAN-BUS TCP-Port (Standard: 3113)
port = 3113

[filter]
# Nur diese UnitId laden (verhindert Duplikate)
unit_id = 513
# Datenpunkte ignorieren (kommasepariert)
ignore_keywords = CO2, VOC, voc, Luftqualität

[logging]
# Werte im Terminal anzeigen
debug_console = true
# Hex-Dumps für Protokoll-Analyse
debug_raw = false

[mqtt]
# MQTT-Publishing aktivieren
enabled = true
# MQTT-Broker IP-Adresse oder Hostname
ip = 127.0.0.1
port = 1883
# Authentifizierung (leer lassen für anonymous)
username =
password =
# Topic-Präfix
topic_base = hoval/homevent

[homeassistant]
# Auto-Discovery aktivieren
discovery = true
prefix = homeassistant
```

## Verwendung

### Als Systemd-Service (Debian-Paket)

```bash
sudo systemctl start hoval-gateway    # Starten
sudo systemctl stop hoval-gateway     # Stoppen
sudo systemctl status hoval-gateway   # Status
sudo systemctl restart hoval-gateway  # Neustarten
journalctl -u hoval-gateway -f        # Logs folgen
```

### Manueller Start

```bash
python hoval.py
```

### Erwartete Ausgabe

```
Lade CSV...
64 Datenpunkte geladen (Unit 513, VOC ignoriert).
MQTT verbunden (127.0.0.1).
Starte Hoval Universal Listener...
Verbunden mit 10.0.0.95
 [LOG] Status Lüftungsregelung       : 1
 [LOG] Lüftungsmodulation            : 45 %
 [LOG] Feuchte Sollwert              : 55 %
 [LOG] Temperatur Aussenluft         : 9.6 °C
 [LOG] Feuchtigkeit Abluft           : 42 %
 [LOG] Temperatur Abluft             : 22.3 °C
```

**Hinweis**: Die initiale 0.0°C-Anzeige, die manchmal beim Start erscheint, wird automatisch durch den Initial Value Filter (Schicht 8) herausgefiltert.

### Beenden

Drücken Sie `Ctrl+C` für einen sauberen Shutdown.

## MQTT-Integration

### MQTT-Authentifizierung

Das Gateway unterstützt sowohl anonyme als auch authentifizierte MQTT-Verbindungen:

**Ohne Authentifizierung (Standard)**:
```ini
[mqtt]
username =
password =
```

**Mit Authentifizierung** (z.B. für Mosquitto mit Passwortdatei):
```ini
[mqtt]
username = mein_benutzer
password = mein_passwort
```

### Topic-Struktur

```
{TOPIC_BASE}/{normalisierter_name}
```

Beispiele:
- `hoval/homevent/aussenluft_temp`
- `hoval/homevent/abluft_temp`
- `hoval/homevent/lueftungsmodulation`

### Nachrichtenformat

Alle Werte werden als JSON publiziert:

```json
{
  "value": 21.3,
  "unit": "°C"
}
```

### Home Assistant Integration

#### Automatische Erkennung (Empfohlen!)

Das Gateway unterstützt **Home Assistant MQTT Discovery**. Alle Sensoren werden automatisch erkannt und hinzugefügt - **keine manuelle Konfiguration erforderlich**!

**Voraussetzungen**:
- MQTT-Integration in Home Assistant aktiviert
- `MQTT_HOMEASSISTANT_DISCOVERY = True` (Standard)

**So funktioniert's**:
1. Gateway starten
2. Sobald der erste Wert für einen Sensor empfangen wird, publiziert das Gateway automatisch die Discovery-Konfiguration
3. Home Assistant erkennt den neuen Sensor und fügt ihn automatisch hinzu
4. Alle Sensoren erscheinen unter einem gemeinsamen Device: **"Hoval HomeVent"**

**Features der Auto-Discovery**:
- ✅ Automatische `device_class` Zuweisung (temperature, humidity, etc.)
- ✅ Passende Icons (Thermometer, Wassertropfen, Lüfter, etc.)
- ✅ Alle Sensoren gruppiert unter einem Device
- ✅ Eindeutige IDs für stabile Entity-Namen
- ✅ Retained Messages - Sensoren bleiben nach Neustart erhalten

**Ausgabe beim Start**:
```
[LOG] Temperatur Aussenluft         : 9.6 °C
[DISCOVERY] Home Assistant Entity: Temperatur Aussenluft
[LOG] Temperatur Abluft             : 22.3 °C
[DISCOVERY] Home Assistant Entity: Temperatur Abluft
```

#### Manuelle Konfiguration (Optional)

Falls Sie Auto-Discovery deaktivieren (`discovery = false` in `[homeassistant]`), können Sie die Sensoren manuell in `configuration.yaml` definieren:

```yaml
mqtt:
  sensor:
    - name: "Hoval Außenluft Temperatur"
      state_topic: "hoval/homevent/aussenluft_temp"
      value_template: "{{ value_json.value }}"
      unit_of_measurement: "°C"
      device_class: "temperature"

    - name: "Hoval Abluft Temperatur"
      state_topic: "hoval/homevent/abluft_temp"
      value_template: "{{ value_json.value }}"
      unit_of_measurement: "°C"
      device_class: "temperature"

    - name: "Hoval Lüftung"
      state_topic: "hoval/homevent/lueftungsmodulation"
      value_template: "{{ value_json.value }}"
      unit_of_measurement: "%"
```

## Architektur

### Datenfluss

```
Hoval-Gerät (CAN-BUS) → TCP Socket (Port 3113)
    ↓
hoval.py (Python Gateway)
    ├─ CSV-Lookup (1136 Datenpunkte)
    ├─ Binary Protocol Decoder
    ├─ Intelligente Filterung
    └─ MQTT Publisher
    ↓
MQTT Broker (z.B. Mosquitto)
    ↓
Home Automation System
```

### Hybrid-Modus (Neu!)

Das Gateway arbeitet in zwei Modi parallel:

1. **CSV-basierter Scan**: Nutzt [hoval_datapoints.csv](hoval_datapoints.csv) für alle bekannten Datenpunkte
2. **Direkte Temperatur-Erfassung**: Sucht zusätzlich nach Temperatur-IDs 0-5, auch ohne korrektes Framing

Dies stellt sicher, dass kritische Temperaturwerte (besonders Außentemperatur) **garantiert** erfasst werden, selbst wenn das CAN-BUS-Protokoll inkonsistent ist.

## Filterung & Fehlerbehandlung

Das Gateway implementiert mehrere Filterschichten:

### 1. Blacklist beim Laden
Datenpunkte mit Keywords in `IGNORE_KEYWORDS` werden nicht geladen.

### 2. Fehlercode-Erkennung
- `0xFF` (255) für U8-Werte
- `0xFFFF` (65535) für U16-Werte
- `-32768` / `32767` für S16-Werte
- Null-Werte bei S32/U32

### 3. Anomalie-Filter
- `25.5°C` (bekannter Fehlercode bei Temperaturen)
- `112.0` (fehlerhafte VOC-Messung)
- `0.0°C` bei Außentemperatur (häufiger Fehlercode, echte 0°C sind selten genug zum Filtern)

### 4. Plausibilitätsprüfung
Temperaturen müssen im Bereich `-40°C` bis `70°C` liegen.

### 5. Change Detection
MQTT-Nachrichten werden nur bei Wertänderungen gesendet (Traffic-Reduktion).

## Wichtige Datenpunkte

Häufig verwendete Sensoren (alle Namen in Deutsch):

| Datenpunkt | Beschreibung | Einheit |
|------------|--------------|---------|
| Außenluft Temp | Außentemperatur | °C |
| Abluft Temp | Abluft-Temperatur | °C |
| Fortluft Temp | Fortluft-Temperatur | °C |
| Zuluft Temp | Zuluft-Temperatur | °C |
| Lüftungsmodulation | Lüfterstufe | % |
| Betriebswahl Lüftung | Betriebsmodus | - |

## Fehlersuche

### Keine Temperaturen sichtbar?

**Problem gelöst in V2!** Frühere Versionen hatten zu strenge Filter. Jetzt:
- ✅ Kein `0x00` Padding-Zwang mehr für IDs
- ✅ `0.0°C` ist ein gültiger Wert (Winter!)
- ✅ Hybrid-Modus mit direkter Temperatursuche

### Verbindung schlägt fehl?

1. **IP-Adresse prüfen**: Ist `HOVAL_IP` korrekt?
   ```bash
   ping 10.0.0.95
   ```

2. **Port prüfen**: Standard ist 3113
   ```bash
   telnet 10.0.0.95 3113
   ```

3. **Firewall**: Port 3113 TCP muss offen sein

### MQTT funktioniert nicht?

1. **Broker läuft?**
   ```bash
   mosquitto -v  # Test-Modus
   ```

2. **Authentifizierung erforderlich?**
   - Prüfen Sie die Mosquitto-Konfiguration auf `allow_anonymous false`
   - Falls aktiviert, setzen Sie `MQTT_USERNAME` und `MQTT_PASSWORD`

3. **Manueller Test** (ohne Authentifizierung):
   ```bash
   mosquitto_sub -h 127.0.0.1 -t "hoval/#" -v
   ```

4. **Manueller Test** (mit Authentifizierung):
   ```bash
   mosquitto_sub -h 127.0.0.1 -t "hoval/#" -v -u username -P password
   ```

5. **Fallback**: Gateway läuft auch ohne MQTT (nur Console-Ausgabe)

### Debug-Modus aktivieren

Für detaillierte Protokoll-Analyse in `config.ini`:

```ini
[logging]
debug_raw = true
```

Ausgabe:
```
 [NULL] Unbekannter Sensor: U8=255 (Fehlercode)
 [FILTER] 25.5°C erkannt bei Außenluft Temp - gefiltert
 [RANGE] Fortluft Temp: 85.3°C außerhalb -40..70
```

## Dateistruktur

```
Hoval-GatewayV2-CANBUS-MQTT/
│
├── hoval.py                 # Haupt-Gateway-Skript
├── config.ini               # Konfigurationsdatei
├── hoval_datapoints.csv     # Datenpunkt-Definitionen (1137 Zeilen)
├── hoval-gateway.service    # Systemd Service-Datei
├── requirements.txt         # Python-Abhängigkeiten
├── README.md                # Diese Datei
├── CLAUDE.md                # Entwickler-Dokumentation
├── debian/                  # Debian-Paketierung
│   ├── control              # Paket-Metadaten
│   ├── changelog            # Versionshistorie
│   ├── rules                # Build-Regeln
│   └── ...
└── .github/
    └── workflows/
        ├── build-deb.yml    # Automatische .deb-Builds
        └── lint.yml         # Ruff Linting
```

## Protokoll-Details

### CAN-BUS Binary Protocol

- **Frame-Delimiter**: `\xff\x01`
- **Datenpunkt-ID**: 2 Bytes (Big-Endian)
- **Wert**: 1-4 Bytes je nach Typ
- **Typen**: U8, S16, U16, S32, U32, LIST

Beispiel (Hex):
```
FF 01 00 00 00 64 00 01 01 2C ...
      └──┬──┘ └─┬─┘ └──┬──┘
      ID=0   Wert  ID=1
      (2B)   (2B)  (2B)
```

### Wert-Dekodierung

1. Bytes als Integer dekodieren (Big-Endian)
2. Dezimal-Skalierung: `wert / (10 ^ decimal)`
3. Runden auf 2 Dezimalstellen

Beispiel:
- Raw: `0x00C8` = 200
- Decimal: 1
- Ergebnis: `200 / 10 = 20.0°C`

## Lizenz

Dieses Projekt steht unter der GPL.

## Support

Bei Problemen oder Fragen:
1. Debug-Modus aktivieren (`DEBUG_RAW = True`)
2. Log-Ausgaben prüfen
3. Issue erstellen mit vollständiger Ausgabe

## Changelog

### Version 2.4.0 (Aktuell)
- ✅ **Externe Konfigurationsdatei**: Alle Einstellungen in `config.ini`
- ✅ **Keine Code-Änderungen nötig**: Benutzer müssen `hoval.py` nicht mehr editieren
- ✅ **INI-Format**: Einfach lesbare und editierbare Konfiguration

### Version 2.3.2
- ✅ **MQTT Error Logging**: Detaillierte Fehlermeldungen bei Auth-Fehlern und Verbindungsabbrüchen
- ✅ **on_connect/on_disconnect Callbacks**: Klare Diagnose bei MQTT-Problemen

### Version 2.3.1
- ✅ **Fix: Unbuffered Output** für korrektes systemd Logging
- ✅ **PYTHONUNBUFFERED=1** Environment-Variable im Service
- ✅ **Ruff Linting** mit GitHub Actions CI
- ✅ **Dependabot** für automatische Dependency-Updates

### Version 2.3.0
- ✅ **Debian-Paketierung**: Fertiges `.deb`-Paket für einfache Installation
- ✅ **Systemd-Service**: `hoval-gateway.service` mit Security-Hardening
- ✅ **Log-Rotation**: Automatische Rotation nach `/var/log/hoval-gateway/`
- ✅ **GitHub Actions CI/CD**: Automatische Builds bei neuen Tags
- ✅ Dedizierter `hoval` System-Benutzer

### Version 2.2
- ✅ **Home Assistant MQTT Auto-Discovery**: Automatische Sensor-Registrierung ohne manuelle Konfiguration
- ✅ **Retained Messages**: Alle MQTT-Nachrichten werden persistent gespeichert
- ✅ **Smart Device Grouping**: Alle Sensoren erscheinen unter einem gemeinsamen Device
- ✅ **Automatische device_class und Icons**: Intelligente Zuweisung basierend auf Sensor-Typ
- ✅ Discovery nur beim ersten Wert pro Sensor (Performance-Optimierung)

### Version 2.1
- ✅ MQTT-Authentifizierung: Unterstützung für Username/Password
- ✅ Neue Konfigurationsparameter: `MQTT_USERNAME` und `MQTT_PASSWORD`
- ✅ Bessere Fehlermeldungen bei MQTT-Verbindungsproblemen
- ✅ Dokumentation für Mosquitto mit Authentifizierung

### Version 2.0
- ✅ Hybrid-Modus: CSV + direkte Temperatur-Suche
- ✅ Kein 0x00-Padding mehr erforderlich
- ✅ 0.0°C ist jetzt ein gültiger Wert
- ✅ Erweiterte Debug-Ausgaben
- ✅ Robustere Temperatur-Erfassung

### Version 1.0
- Initiale Version mit CSV-basiertem Lookup
- Grundlegende Filterung und MQTT-Integration

## Danksagungen

Entwickelt für die Integration von Hoval HomeVent Systemen in moderne Smart-Home-Umgebungen.
