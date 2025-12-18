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

**[hoval.py](hoval.py)** - Single monolithic application (202 lines) with 5 key functions:

1. **`load_csv()`** - Loads [hoval_datapoints.csv](hoval_datapoints.csv) into `datapoint_map` dictionary, filtering blacklisted keywords
2. **`decode_smart(raw_bytes, dp_info)`** - Decodes binary data based on type (U8, S16, U16, S32, U32, LIST) with decimal scaling
3. **`process_stream(client, data)`** - Scans binary stream for 3-byte datapoint keys, extracts values
4. **`handle_output(client, name, value, unit)`** - Normalizes names (German umlauts → ASCII), deduplicates, publishes to MQTT
5. **`main()`** - Orchestrates socket connection, streaming loop, and automatic reconnection

**[hoval_datapoints.csv](hoval_datapoints.csv)** - Device configuration file (1,137 rows):
- Semicolon-delimited, Latin-1 encoded
- Key columns: `UnitName`, `DatapointId`, `DatapointName`, `TypeName`, `Decimal`, `unit`
- Only rows with `UnitName='HV'` are loaded
- All datapoint names are in German (e.g., "Außenluft Temp", "Lüftung", "Betriebswahl")

## Binary Protocol Details

### Frame Structure
- Frames are delimited by `\xff\x01` byte sequence
- Datapoint identifiers are 3 bytes: `\x00` + 2-byte big-endian ID
- Value bytes follow immediately after the 3-byte key
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

The application implements multiple filtering layers to prevent invalid data:

### 1. Load-Time Blacklist ([hoval.py:54](hoval.py#L54))
- Keywords in `IGNORE_KEYWORDS` (default: `["VOC", "voc", "Luftqualität"]`)
- Datapoints with blacklisted names are never loaded into memory

### 2. Null Value Detection ([hoval.py:77-101](hoval.py#L77-L101))
- All `0xFF` byte patterns are rejected
- Type-specific null values (see table above) are filtered

### 3. Anomaly Detection ([hoval.py:110-118](hoval.py#L110-L118))
- `25.5°C` temperature readings (common error value)
- `112.0` values (erroneous VOC readings)
- `0.0°C` on "Aussen" (outdoor) sensors (spike filtering)

### 4. Range Validation ([hoval.py:139-141](hoval.py#L139-L141))
- Outdoor temperatures must be in range `-40°C` to `50°C`

### 5. Change Detection ([hoval.py:148-149](hoval.py#L148-L149))
- Only publish when value changes (reduces MQTT traffic)
- Uses `last_sent` dictionary to track previous values

## Configuration

All configuration is at the top of [hoval.py](hoval.py) (lines 9-31):

```python
# Device connection
HOVAL_IP = '10.0.0.95'           # Hoval device IP
HOVAL_PORT = 3113                 # CAN-BUS TCP port
CSV_FILE = 'hoval_datapoints.csv' # Device mapping file

# Filtering
IGNORE_KEYWORDS = ["VOC", "voc", "Luftqualität"]

# Debugging
DEBUG_CONSOLE = True              # Print values to terminal
DEBUG_RAW = False                 # Print hex data (for protocol analysis)

# MQTT
MQTT_ENABLED = True               # Enable MQTT publishing
MQTT_IP = '127.0.0.1'            # MQTT broker address
MQTT_PORT = 1883                  # MQTT broker port
TOPIC_BASE = "hoval/homevent"     # MQTT topic prefix
```

## Running the Application

### Prerequisites
```bash
pip install paho-mqtt
```

### Execution
```bash
python hoval.py
```

### Expected Output
```
Lade CSV...
1136 Datenpunkte geladen (VOC ignoriert).
MQTT verbunden (127.0.0.1).
Starte Hoval Universal Listener...
Verbunden mit 10.0.0.95
 [LOG] Außenluft Temp              : 12.5 °C
 [LOG] Abluft Temp                 : 21.3 °C
 [LOG] Lüftungsmodulation          : 45 %
```

### Stopping
- Press `Ctrl+C` to gracefully shutdown

## MQTT Message Format

Published messages use JSON format:
```json
{
  "value": 21.3,
  "unit": "°C"
}
```

Topic structure: `{TOPIC_BASE}/{normalized_name}`

Example: `hoval/homevent/aussenluft_temp`

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
- **CSV validation**: Checks file existence before loading
- **Silent parsing errors**: Invalid datapoints are skipped, not fatal

## Development Notes

### No Testing Framework
This codebase has no automated tests. When modifying code:
- Test manually with actual Hoval hardware or simulated socket
- Monitor console output and MQTT messages
- Verify filtering logic with edge cases

### No Build System
Direct Python execution - no Makefile, setup.py, or requirements.txt

### German Language Context
All device datapoint names and comments are in German. Key terms:
- **Lüftung** - Ventilation
- **Außenluft** - Outdoor air
- **Abluft** - Exhaust air
- **Fortluft** - Outgoing air
- **Zuluft** - Supply air
- **Betriebswahl** - Operating mode selection

### State Management
Two global dictionaries maintain state:
- **`datapoint_map`** - CSV configuration cache (loaded once at startup)
- **`last_sent`** - Change detection cache (prevents duplicate MQTT publishes)

### Protocol Analysis
Enable `DEBUG_RAW = True` to view hex dumps of binary protocol data for debugging or reverse engineering.
