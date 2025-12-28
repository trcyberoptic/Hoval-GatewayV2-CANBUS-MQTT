# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Hoval Gateway V2** is a Python-based IoT gateway that bridges Hoval ventilation/heating systems (HV units) to MQTT via CAN-BUS protocol. It continuously reads sensor data from a Hoval device over a TCP socket and publishes it to an MQTT broker for home automation integration.

## Architecture

### Data Flow
```
Hoval Device (10.0.0.95:3113)
    ↓ TCP Socket (Binary CAN-BUS protocol)
[hoval.py]
    ├─ load_csv() - Load device configuration
    ├─ process_stream() - Parse binary protocol frames
    ├─ decode_smart() - Type conversion & filtering
    └─ handle_output() - Normalize & publish
    ↓ MQTT (JSON messages)
MQTT Broker (127.0.0.1:1883)
    ↓
Home Automation Systems
```

### Core Components

**[hoval.py](hoval.py)** - Single monolithic application (~380 lines) with 6 key functions:

1. **`load_csv()`** - Loads [hoval_datapoints.csv](hoval_datapoints.csv) into `datapoint_map` dictionary, filtering blacklisted keywords and Unit ID
2. **`decode_smart(raw_bytes, dp_info)`** - Decodes binary data based on type (U8, S16, U16, S32, U32, LIST) with decimal scaling and byte-level 0xFF checks
3. **`process_stream(client, data)`** - **Hybrid scanner** that accepts IDs with OR without 0x00 prefix (fallback for IDs 0-5)
4. **`publish_homeassistant_discovery(client, clean_name, name, unit)`** - **NEW**: Publishes Home Assistant MQTT Discovery config (once per sensor)
5. **`handle_output(client, name, value, unit)`** - Normalizes names (German umlauts → ASCII), deduplicates, publishes to MQTT with retained flag
6. **`main()`** - Orchestrates socket connection, streaming loop, and automatic reconnection

**[hoval_datapoints.csv](hoval_datapoints.csv)** - Device configuration file (1,137 rows):
- Semicolon-delimited, **UTF-8 encoded**
- Key columns: `UnitName`, `UnitId`, `DatapointId`, `DatapointName`, `TypeName`, `Decimal`, `unit`
- Only rows with `UnitName='HV'` **and** matching `UNIT_ID_FILTER` are loaded
- All datapoint names are in German (e.g., "Außenluft Temp", "Lüftung", "Betriebswahl")

## Binary Protocol Details

### Frame Structure
- Frames are delimited by `\xff\x01` byte sequence
- **Primary format**: Datapoint identifiers are 3 bytes: `\x00` + 2-byte big-endian ID
- **Fallback format** (IDs 0-5 only): Direct 2-byte big-endian ID without prefix
- Value bytes follow immediately after the ID
- Byte lengths: 1 byte (U8), 2 bytes (S16/U16), 4 bytes (S32/U32)

### Type System
| Type | Bytes | Format | Null Value |
|------|-------|--------|------------|
| U8 | 1 | Unsigned 8-bit | `0xFF` (255) |
| S16 | 2 | Signed 16-bit BE | `0x8000` (-32768) or `0x7FFF` (32767) |
| U16 | 2 | Unsigned 16-bit BE | `0xFFFF` (65535) |
| S32 | 4 | Signed 32-bit BE | `0x80000000` (-2147483648) |
| U32 | 4 | Unsigned 32-bit BE | `0xFFFFFFFF` (4294967295) |

Values are scaled by dividing by `10^decimal` (from CSV configuration).

## Filtering Logic

The application implements multiple filtering layers to prevent invalid data (9 layers total):

### 1. Unit ID Filter ([hoval.py:54-57](hoval.py#L54-L57))
- Only datapoints from `UNIT_ID_FILTER` (default: 513) are loaded
- Prevents duplicate datapoints from multiple units

### 2. Load-Time Blacklist ([hoval.py:63](hoval.py#L63))
- Keywords in `IGNORE_KEYWORDS` (default: `["VOC", "voc", "Luftqualität"]`)
- Datapoints with blacklisted names are never loaded into memory

### 3. Byte-Level Null Detection ([hoval.py:106-109](hoval.py#L106-L109))
- **NEW**: S16 values are checked for individual `0xFF` bytes BEFORE unpacking
- Prevents `-25.4°C` (from `0xFF02`) being misinterpreted as valid
- Also filters `0x0000` in NOPREFIX path

### 4. Type-Specific Null Values
- All `0xFF` byte patterns are rejected
- Type-specific null values (see table above) are filtered

### 5. Anomaly Detection ([hoval.py:147-165](hoval.py#L147-L165))
- `25.5°C` temperature readings (common error value)
- `112.0` values (erroneous VOC readings)
- `0.0°C` for outdoor temperature ("Aussen") - common error code, real outdoor 0°C is rare enough to filter

### 6. Range Validation ([hoval.py:188-193](hoval.py#L188-L193))
- Temperatures must be in range `-40°C` to `70°C`

### 7. Jump Detection ([hoval.py:238-243](hoval.py#L238-L243))
- **NEW**: For NOPREFIX path, rejects temperature changes > 20°C
- Prevents false positives from random byte patterns

### 8. Initial Value Filter ([hoval.py:244-249](hoval.py#L244-L249))
- **NEW**: Filters 0.0°C on first reading (when no previous value exists)
- Common error code at connection startup
- After first valid reading, normal jump detection applies

### 9. Change Detection ([hoval.py:264-265](hoval.py#L264-L265))
- Only publish when value changes (reduces MQTT traffic)
- Uses `last_sent` dictionary to track previous values

## Configuration

All configuration is stored in [config.ini](config.ini):

```ini
[hoval]
ip = 10.0.0.95                    # Hoval device IP
port = 3113                        # CAN-BUS TCP port
csv_file = hoval_datapoints.csv   # Device mapping file

[filter]
unit_id = 513                      # Only load this Unit ID (prevents duplicates)
ignore_keywords = CO2, VOC, voc, Luftqualität  # Comma-separated blacklist

[logging]
debug_console = true               # Print values to terminal
debug_raw = false                  # Print hex data (for protocol analysis)

[mqtt]
enabled = true                     # Enable MQTT publishing
ip = 127.0.0.1                    # MQTT broker address
port = 1883                        # MQTT broker port
username =                         # MQTT username (empty for anonymous)
password =                         # MQTT password (empty for anonymous)
topic_base = hoval/homevent       # MQTT topic prefix

[homeassistant]
discovery = true                   # Home Assistant Auto-Discovery
prefix = homeassistant            # Discovery prefix
```

## Installation

### Debian/Ubuntu Package (Recommended)

Download the `.deb` package from [GitHub Releases](https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/releases):

```bash
# Install package
sudo apt install ./hoval-gateway_2.4.0_all.deb

# Edit configuration
sudo nano /opt/hoval-gateway/config.ini

# Enable and start service
sudo systemctl enable --now hoval-gateway

# View logs
tail -f /var/log/hoval-gateway/hoval.log
```

The package installs:
- Application to `/opt/hoval-gateway/`
- Systemd service `hoval-gateway.service`
- Log rotation to `/var/log/hoval-gateway/`
- Dedicated `hoval` system user

### Manual Installation

```bash
pip install paho-mqtt
python hoval.py
```

## Running the Application

### As a Systemd Service (Debian Package)
```bash
sudo systemctl start hoval-gateway    # Start
sudo systemctl stop hoval-gateway     # Stop
sudo systemctl status hoval-gateway   # Status
journalctl -u hoval-gateway -f        # Follow logs
```

### Manual Execution
```bash
python hoval.py
```

### Expected Output
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

Note: The initial 0.0°C reading that sometimes appears at startup is now automatically filtered out by the Initial Value Filter (Layer 8).

### Stopping
- Press `Ctrl+C` to gracefully shutdown

## MQTT Message Format

Published messages use JSON format with **retained flag**:
```json
{
  "value": 21.3,
  "unit": "°C"
}
```

Topic structure: `{TOPIC_BASE}/{normalized_name}`

Example: `hoval/homevent/aussenluft_temp`

## Home Assistant Auto-Discovery

The application automatically publishes Home Assistant MQTT Discovery configuration for each sensor on first appearance. This eliminates the need for manual sensor configuration in Home Assistant.

### Discovery Topics
Format: `{HOMEASSISTANT_PREFIX}/sensor/hoval/{sensor_name}/config`

Example: `homeassistant/sensor/hoval/aussenluft_temp/config`

### Discovery Payload
```json
{
  "name": "Hoval Außenluft Temp",
  "unique_id": "hoval_aussenluft_temp",
  "state_topic": "hoval/homevent/aussenluft_temp",
  "value_template": "{{ value_json.value }}",
  "unit_of_measurement": "°C",
  "device_class": "temperature",
  "icon": "mdi:thermometer",
  "device": {
    "identifiers": ["hoval_homevent"],
    "name": "Hoval HomeVent",
    "manufacturer": "Hoval",
    "model": "HomeVent"
  }
}
```

### Automatic Device Class Assignment
- **Temperature sensors** (`°C`): `device_class: temperature`, icon: `mdi:thermometer`
- **Humidity sensors** (`%` + "feucht"): `device_class: humidity`, icon: `mdi:water-percent`
- **Ventilation** (`%` + "lueft"): icon: `mdi:fan`
- **CO2 sensors**: `device_class: carbon_dioxide`, icon: `mdi:molecule-co2`
- **VOC sensors**: `device_class: volatile_organic_compounds`, icon: `mdi:air-filter`

### State Management
- **`discovered_topics`** set tracks which sensors have been discovered
- Discovery config is only published once per sensor (on first value)
- All discovery messages are retained to survive broker restarts

### Name Normalization
German datapoint names are normalized for MQTT topics:
- Spaces → underscores
- German umlauts: `ä→ae`, `ö→oe`, `ü→ue`, `ß→ss`
- Remove: `.` and `/`
- Lowercase

## Error Handling & Reconnection

- **Socket timeout**: 15 seconds
- **Reconnection delay**: 10 seconds after any exception
- **MQTT fallback**: If broker unreachable, continues in console-only mode
- **MQTT authentication**: Supports both anonymous and authenticated connections via `username_pw_set()`
- **MQTT error logging**: Detailed error messages via `on_connect` and `on_disconnect` callbacks
- **CSV validation**: Checks file existence before loading
- **Silent parsing errors**: Invalid datapoints are skipped, not fatal

### MQTT Error Messages
The application logs detailed MQTT connection errors:
| Code | Message |
|------|---------|
| 1 | Falsche Protokollversion |
| 2 | Ungültige Client-ID |
| 3 | Server nicht erreichbar |
| 4 | Authentifizierung fehlgeschlagen (falscher Benutzername/Passwort) |
| 5 | Nicht autorisiert |

Unexpected disconnections are also logged with their return code.

## Development Notes

### No Testing Framework
This codebase has no automated tests. When modifying code:
- Test manually with actual Hoval hardware or simulated socket
- Monitor console output and MQTT messages
- Verify filtering logic with edge cases

### Build System
- **Debian packaging**: `debian/` directory with full debhelper support
- **GitHub Actions**: Automatic `.deb` builds on tagged releases (`.github/workflows/build-deb.yml`)
- **Manual build**: Run `./build-deb.sh` on a Debian system

### German Language Context
All device datapoint names and comments are in German. Key terms:
- **Lüftung** - Ventilation
- **Außenluft** - Outdoor air
- **Abluft** - Exhaust air
- **Fortluft** - Outgoing air
- **Zuluft** - Supply air
- **Betriebswahl** - Operating mode selection

### State Management
Three global data structures maintain state:
- **`datapoint_map`** - CSV configuration cache (loaded once at startup)
- **`last_sent`** - Change detection cache (prevents duplicate MQTT publishes)
- **`discovered_topics`** - Set of sensor names that have been discovered (prevents duplicate discovery configs)

### Protocol Analysis
Enable `DEBUG_RAW = True` to view hex dumps of binary protocol data for debugging or reverse engineering.
