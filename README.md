# Hoval Gateway V2 - CAN-BUS to MQTT Bridge

Ein Python-basiertes Gateway, das Hoval Lüftungs-/Heizungssysteme (HV-Geräte) über CAN-BUS mit MQTT-Brokern verbindet. Ideal für die Integration in Home Automation Systeme wie Home Assistant, ioBroker oder OpenHAB.

## Features

- **Echtzeit-Datenübertragung**: Kontinuierliches Auslesen von Sensor- und Statusdaten
- **MQTT-Integration**: Publiziert alle Werte als JSON-Nachrichten
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

1. **Repository klonen oder Dateien herunterladen**:
   ```bash
   git clone <repository-url>
   cd Hoval-GatewayV2-CANBUS-MQTT
   ```

2. **Abhängigkeiten installieren**:
   ```bash
   pip install paho-mqtt
   ```

3. **Konfiguration anpassen** (siehe unten)

## Konfiguration

Öffnen Sie [hoval.py](hoval.py) und passen Sie die Parameter an (Zeilen 9-27):

```python
# --- KONFIGURATION ---
HOVAL_IP = '10.0.0.95'           # IP-Adresse des Hoval-Geräts
HOVAL_PORT = 3113                 # CAN-BUS TCP-Port (Standard: 3113)
CSV_FILE = 'hoval_datapoints.csv' # Datenpunkt-Konfiguration

# --- BLACKLIST ---
# Datenpunkte ignorieren (z.B. nicht verbaute Sensoren)
IGNORE_KEYWORDS = ["VOC", "voc", "Luftqualität"]

# Logging
DEBUG_CONSOLE = True              # Werte im Terminal anzeigen
DEBUG_RAW = False                 # Hex-Dumps für Protokoll-Analyse

# MQTT
MQTT_ENABLED = True               # MQTT-Publishing aktivieren
MQTT_IP = '127.0.0.1'            # MQTT-Broker IP-Adresse
MQTT_PORT = 1883                  # MQTT-Broker Port
TOPIC_BASE = "hoval/homevent"     # MQTT-Topic-Präfix
```

## Verwendung

### Starten des Gateways

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

Beispiel-Konfiguration für `configuration.yaml`:

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

2. **Manueller Test**:
   ```bash
   mosquitto_sub -h 127.0.0.1 -t "hoval/#" -v
   ```

3. **Fallback**: Gateway läuft auch ohne MQTT (nur Console-Ausgabe)

### Debug-Modus aktivieren

Für detaillierte Protokoll-Analyse:

```python
DEBUG_RAW = True  # Zeigt alle gefilterten Werte und Hex-Dumps
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
├── hoval.py                 # Haupt-Gateway-Skript (202 Zeilen)
├── hoval_datapoints.csv     # Datenpunkt-Definitionen (1137 Zeilen)
├── README.md                # Diese Datei
└── CLAUDE.md                # Entwickler-Dokumentation
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

Dieses Projekt steht unter der MIT-Lizenz (oder andere - bitte anpassen).

## Support

Bei Problemen oder Fragen:
1. Debug-Modus aktivieren (`DEBUG_RAW = True`)
2. Log-Ausgaben prüfen
3. Issue erstellen mit vollständiger Ausgabe

## Changelog

### Version 2.0 (Aktuell)
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
