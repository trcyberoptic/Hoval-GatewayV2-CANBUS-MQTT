import configparser
import csv
import json
import os
import socket
import struct
import sys
import time

import paho.mqtt.client as mqtt

# Unbuffered output für systemd logging
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# --- KONFIGURATION LADEN ---
def load_config():
    """Lädt Konfiguration aus config.ini"""
    config = configparser.ConfigParser()

    # Suche config.ini im gleichen Verzeichnis wie das Skript
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.ini')

    if not os.path.exists(config_path):
        print(f'FEHLER: {config_path} nicht gefunden!')
        print('Bitte config.ini erstellen (siehe config.ini.example)')
        sys.exit(1)

    config.read(config_path, encoding='utf-8')
    return config


# Konfiguration laden
_config = load_config()

# Hoval-Gerät
HOVAL_IP = _config.get('hoval', 'ip', fallback='10.0.0.95')
HOVAL_PORT = _config.getint('hoval', 'port', fallback=3113)
CSV_FILE = _config.get('hoval', 'csv_file', fallback='hoval_datapoints.csv')

# Filter
UNIT_ID_FILTER = _config.getint('filter', 'unit_id', fallback=513)
_ignore_str = _config.get('filter', 'ignore_keywords', fallback='VOC, voc, Luftqualität')
IGNORE_KEYWORDS = [kw.strip() for kw in _ignore_str.split(',') if kw.strip()]

# Logging
DEBUG_CONSOLE = _config.getboolean('logging', 'debug_console', fallback=True)
DEBUG_RAW = _config.getboolean('logging', 'debug_raw', fallback=False)

# MQTT
MQTT_ENABLED = _config.getboolean('mqtt', 'enabled', fallback=True)
MQTT_IP = _config.get('mqtt', 'ip', fallback='127.0.0.1')
MQTT_PORT = _config.getint('mqtt', 'port', fallback=1883)
MQTT_USERNAME = _config.get('mqtt', 'username', fallback='')
MQTT_PASSWORD = _config.get('mqtt', 'password', fallback='')
TOPIC_BASE = _config.get('mqtt', 'topic_base', fallback='hoval/homevent')

# Home Assistant
MQTT_HOMEASSISTANT_DISCOVERY = _config.getboolean('homeassistant', 'discovery', fallback=True)
HOMEASSISTANT_PREFIX = _config.get('homeassistant', 'prefix', fallback='homeassistant')

# Speicher
datapoint_map = {}
last_sent = {}
discovered_topics = set()  # Bereits registrierte Topics für Home Assistant


# --- CSV LADEN ---
def load_csv():
    if not os.path.exists(CSV_FILE):
        print(f'FEHLER: {CSV_FILE} fehlt!')
        return False

    print('Lade CSV...')
    count = 0
    try:
        with open(CSV_FILE, encoding='utf-8', errors='replace') as f:
            line = f.readline()
            delimiter = ';' if ';' in line else ','
            f.seek(0)

            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                if row.get('UnitName') != 'HV':
                    continue

                # UNIT ID FILTER
                # Nur die konfigurierte Unit-ID laden (verhindert Duplikate!)
                try:
                    unit_id = int(row.get('UnitId', 0))
                    if UNIT_ID_FILTER and unit_id != UNIT_ID_FILTER:
                        continue
                except:
                    pass

                # BLACKLIST CHECK BEIM LADEN
                # Wenn der Name auf der Blacklist steht, gar nicht erst laden!
                name = row['DatapointName']
                if any(x in name for x in IGNORE_KEYWORDS):
                    continue

                try:
                    dp_id = int(row['DatapointId'])
                    # Speichere die ID selbst (2 Bytes) statt mit 0x00 Prefix
                    id_bytes = struct.pack('>H', dp_id)

                    datapoint_map[id_bytes] = {
                        'name': name,
                        'type': row['TypeName'],
                        'decimal': int(row['Decimal']),
                        'unit': row['unit'],
                        'id': dp_id,  # Speichere auch die numerische ID
                    }
                    count += 1
                except:
                    continue
        print(f'{count} Datenpunkte geladen (Unit {UNIT_ID_FILTER}, VOC ignoriert).')
        return True
    except Exception as e:
        print(f'CSV Fehler: {e}')
        return False


# --- DECODER ---
def decode_smart(raw_bytes, dp_info):
    if raw_bytes == b'\xff' * len(raw_bytes):
        if DEBUG_RAW:
            print(f' [NULL] {dp_info["name"]}: Alle Bytes 0xFF (Fehlercode)')
        return None

    val = 0
    type_name = dp_info['type']

    try:
        if type_name == 'U8':
            val = raw_bytes[0]
            if val == 255:
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: U8=255 (Fehlercode)')
                return None

        elif type_name == 'S16':
            # S16 Fehlercodes:
            # - 0xFFFF = -1 (raw) - klassischer Null-Wert
            # - 0xFF00 bis 0xFF01 = -256 bis -255 → -25.6 bis -25.5°C (Fehlercodes)
            # - 0x00FF = 255 → 25.5°C (bereits im Anomalie-Filter)
            # Aber NICHT alle 0xFF-High-Bytes filtern, da echte negative Temps
            # z.B. -1.0°C = 0xFFF6, -1.1°C = 0xFFF5, -5.0°C = 0xFFCE, -12.8°C = 0xFF80
            if raw_bytes == b'\xff\xff':
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: S16=0xFFFF (Fehlercode)')
                return None
            # 0xFF00-0xFF02 filtern (resultiert in -25.6 bis -25.4°C)
            # 0xFF02 ist der Frame-Terminator, der manchmal als Daten fehlinterpretiert wird
            # Echte Temperaturen unter -25°C sind bei Innenraum-Sensoren unrealistisch
            if raw_bytes[0] == 0xFF and raw_bytes[1] <= 0x02:
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: S16={raw_bytes.hex()} (Fehlercode-Bereich)')
                return None

            val = struct.unpack('>h', raw_bytes[0:2])[0]
            if val in [-32768, 32767]:
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: S16={val} (Extremwert/Fehlercode)')
                return None

        elif type_name == 'U16':
            val = struct.unpack('>H', raw_bytes[0:2])[0]
            if val == 65535:
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: U16=65535 (Fehlercode)')
                return None

        elif type_name == 'S32':
            val = struct.unpack('>i', raw_bytes[0:4])[0]
            if val == -2147483648:
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: S32={val} (Fehlercode)')
                return None

        elif type_name == 'U32':
            val = struct.unpack('>I', raw_bytes[0:4])[0]
            if val == 4294967295:
                if DEBUG_RAW:
                    print(f' [NULL] {dp_info["name"]}: U32={val} (Fehlercode)')
                return None
        else:
            return None

        # Dezimal anwenden
        if dp_info['decimal'] > 0:
            val = val / (10 ** dp_info['decimal'])
            val = round(val, 2)

            # --- FILTER (REDUZIERT) ---
            # 25.5°C und -25.5°C sind bekannte Fehlercodes (0x00FF und 0xFF01)
            if val in [25.5, -25.5] and 'Temp' in dp_info['name']:
                if DEBUG_CONSOLE:
                    print(f' [FILTER] {val}°C erkannt bei {dp_info["name"]} - gefiltert')
                return None

            if val == 112.0:
                if DEBUG_CONSOLE:
                    print(f' [FILTER] 112.0 erkannt bei {dp_info["name"]} - gefiltert')
                return None

        return val
    except:
        return None


def scan_for_outdoor_temp(client, data, dp):
    """
    Scannt den gesamten Frame nach dem Außentemperatur-Pattern.

    Neuer Ansatz: Suche RÜCKWÄRTS von FF 02 Terminatoren.
    Pattern: [00 00 00 00] [S16-value] [FF 02] für positive Temps
    Pattern: [xx 00 00 00] [S16-value] [FF 02] allgemein (xx = Vorgänger-Byte)

    Beispiel positiv: ... 32 00 00 00 00 1b ff 02 = 2.7°C (0x001B)
    Beispiel negativ: ... 00 00 00 00 ff f5 ff 02 = -1.1°C (0xFFF5)
    Position:            -8 -7 -6 -5 -4 -3 -2 -1  (relativ zu FF 02 Ende)

    Negative Temperaturen (S16):
    - -1.0°C = 0xFFF6, -1.1°C = 0xFFF5, -5.0°C = 0xFFCE, etc.
    - Das High-Byte 0xFF ist KEIN Fehlercode, sondern das Vorzeichen!
    """
    # Wir brauchen mindestens 8 Bytes
    if len(data) < 8:
        return False

    # Finde alle FF 02 Terminatoren und prüfe rückwärts
    for i in range(len(data) - 1):
        if data[i : i + 2] == b'\xff\x02':
            # FF 02 gefunden an Position i
            # Prüfe ob 6 Bytes davor verfügbar: [4-byte prefix] [2-byte value] [FF 02]
            if i < 6:
                continue

            raw_bytes = data[i - 2 : i]  # 2 Bytes direkt vor FF 02 = Value
            prefix = data[i - 6 : i - 2]  # 4 Bytes davor = Prefix

            if DEBUG_RAW:
                # Zeige mehr Kontext: 10 Bytes vor FF 02
                context_start = max(0, i - 10)
                context = data[context_start : i + 2]
                print(f' [FF02] @ {i}: prefix={prefix.hex()} value={raw_bytes.hex()} context={context.hex()}')

            # Prüfe auf gültiges Prefix-Pattern
            # Das Prefix muss mindestens 2x 0x00 aufeinanderfolgend haben
            # Mögliche Patterns:
            # - 00 00 00 00 (Standard für positive Temps)
            # - xx 00 00 00 (xx = beliebiges Vorgänger-Byte)
            # - 00 00 00 xx (möglich bei negativen Temps?)
            # - xx 00 00 xx (auch möglich?)
            valid_prefix = False
            if prefix == b'\x00\x00\x00\x00':
                valid_prefix = True
            elif prefix[1:4] == b'\x00\x00\x00':
                # Auch akzeptieren wenn nur die letzten 3 Bytes 00 sind
                # (das erste Byte kann vom vorherigen Datenpunkt sein)
                valid_prefix = True
            elif prefix[0:3] == b'\x00\x00\x00':
                # Alternative: Die ersten 3 Bytes sind 00
                # (das letzte Byte könnte Teil des Temperaturwerts sein bei 4-byte Kodierung?)
                valid_prefix = True
            elif prefix[1:3] == b'\x00\x00':
                # Noch lockerer: Mindestens 2 aufeinanderfolgende Nullen in der Mitte
                valid_prefix = True

            if not valid_prefix:
                continue

            # Überspringe echte Fehlercodes (NICHT negative Temperaturen!)
            # 0xFFFF = -1 (klassischer Null-Wert für S16)
            # 0xFF02 = Frame-Terminator (KEIN echter Temperaturwert!)
            # 0x00FF = 255 → 25.5°C (Fehlercode, wird später als Anomalie gefiltert)
            # 0x0000 = 0 → 0.0°C (oft Fehlercode bei Außentemp)
            # 0xFF00-0xFF01 = Fehlercodes (-25.6 bis -25.5°C Bereich)
            # ABER: 0xFFF5 = -11 → -1.1°C ist KEIN Fehlercode!
            # ABER: 0xFF02 könnte theoretisch -25.4°C sein - praktisch unmöglich
            if raw_bytes == b'\xff\xff':
                if DEBUG_RAW:
                    print('   -> Fehlercode 0xFFFF übersprungen')
                continue
            if raw_bytes == b'\xff\x02':
                # Das ist der Frame-Terminator, nicht ein Temperaturwert!
                if DEBUG_RAW:
                    print('   -> Frame-Terminator 0xFF02 übersprungen')
                continue
            if raw_bytes == b'\x00\x00':
                if DEBUG_RAW:
                    print('   -> Fehlercode 0x0000 übersprungen')
                continue
            # Nur 0xFF00-0xFF01 sind Fehlercodes (nicht 0xFF02+, das sind echte negative Temps)
            # 0xFF00 = -25.6°C, 0xFF01 = -25.5°C (bekannter Fehlercode)
            if raw_bytes[0] == 0xFF and raw_bytes[1] <= 0x01:
                if DEBUG_RAW:
                    print(f'   -> Fehlercode-Bereich 0xFF00-0xFF01 übersprungen: {raw_bytes.hex()}')
                continue

            # DEBUG: Zeige auch gültige Kandidaten die durch decode_smart gehen
            if DEBUG_RAW:
                print(f'   -> Gültiger Kandidat mit prefix={prefix.hex()}, versuche decode...')

            value = decode_smart(raw_bytes, dp)
            if value is not None and -40 <= value <= 50:
                print(f' [SCAN] Außentemp: 0x{raw_bytes.hex()} = {value}°C @ pos {i - 2}')
                handle_output(client, dp['name'], value, dp['unit'])
                return True
            elif DEBUG_RAW and value is not None:
                print(f'   -> Wert {value}°C außerhalb Bereich -40..50')

    return False


def process_stream(client, data):
    # Scan durch Frame (bereits durch 0xFF 0x01 getrennt in main())
    # Jetzt flexibel: Akzeptiere IDs mit ODER ohne 0x00 Prefix

    # Spezialfall: DatapointId=0 (Außentemperatur) - scanne gesamten Frame
    dp_outdoor = datapoint_map.get(b'\x00\x00')  # ID=0
    if dp_outdoor:
        scan_for_outdoor_temp(client, data, dp_outdoor)

    i = 0
    while i < len(data) - 2:
        # Variante 1: 3-Byte ID mit 0x00 Prefix (klassisch)
        if i < len(data) - 3:
            key_3byte = data[i : i + 3]
            if key_3byte[0] == 0x00:  # Hat 0x00 Prefix?
                key_2byte = key_3byte[1:3]  # Extrahiere die echte 2-Byte ID

                if key_2byte in datapoint_map:
                    dp = datapoint_map[key_2byte]
                    byte_len = 1 if '8' in dp['type'] else 2
                    if '32' in dp['type']:
                        byte_len = 4

                    # ID=0 wird bereits oben per scan_for_outdoor_temp behandelt
                    if dp['id'] == 0:
                        i += 1
                        continue

                    # Normaler Fall für alle anderen IDs
                    offset = 3
                    if i + offset + byte_len <= len(data):
                        raw_bytes = data[i + offset : i + offset + byte_len]

                        if DEBUG_RAW and 'Aussen' in dp['name']:
                            hex_str = raw_bytes.hex()
                            print(f' [RAW] {dp["name"]} @ pos {i} (offset {offset}): 0x{hex_str}')

                        value = decode_smart(raw_bytes, dp)

                        if value is not None:
                            if 'Temp' in dp['name'] or 'Aussen' in dp['name']:
                                # Range Check
                                if not (-40 <= value <= 70):
                                    if DEBUG_RAW:
                                        print(f' [RANGE] {dp["name"]}: {value}°C @ pos {i}')
                                    i += 1
                                    continue

                                # Filter 0.0°C für Außentemperatur (häufiger Fehlercode)
                                if value == 0.0 and 'Aussen' in dp['name']:
                                    if DEBUG_CONSOLE:
                                        print(f' [FILTER] 0.0°C bei {dp["name"]} gefiltert (Fehlercode)')
                                    i += 1
                                    continue

                            handle_output(client, dp['name'], value, dp['unit'])
                            i += offset + byte_len  # Überspringe verarbeitete Bytes
                            continue

        # Variante 2: Direkte 2-Byte ID (neu, für Temperaturen ohne Prefix)
        # NUR für sehr niedrige IDs (0-5) und NUR wenn Position > 0
        key_2byte = data[i : i + 2]
        if key_2byte in datapoint_map:
            dp = datapoint_map[key_2byte]

            # WICHTIG: Nur für IDs 0-5 und NICHT am Frame-Anfang (pos 0)
            if dp['id'] <= 5 and i > 0:
                byte_len = 1 if '8' in dp['type'] else 2
                if '32' in dp['type']:
                    byte_len = 4

                if i + 2 + byte_len <= len(data):
                    raw_bytes = data[i + 2 : i + 2 + byte_len]

                    # Extra-Check für NOPREFIX: 0x0000 ist auch ein Fehlercode
                    if raw_bytes == b'\x00\x00':
                        i += 1
                        continue

                    value = decode_smart(raw_bytes, dp)

                    if value is not None:
                        # Strengere Prüfung für niedrige IDs ohne Prefix
                        if 'Temp' in dp['name'] or 'Aussen' in dp['name']:
                            if not (-40 <= value <= 70):
                                i += 1
                                continue

                        # Extra-Validierung: Wert sollte stabil sein
                        # (verhindert wilde Sprünge durch False Positives)
                        prev_val = last_sent.get(dp['name'].replace(' ', '_').lower())
                        if prev_val is not None:
                            # Wenn Änderung > 20 Grad, wahrscheinlich False Positive
                            if abs(value - prev_val) > 20:
                                i += 1
                                continue
                        else:
                            # Beim ersten Wert: 0.0°C ist sehr verdächtig (oft Fehlercode)
                            # Nur akzeptieren wenn es der einzige Wert in diesem Frame ist
                            if value == 0.0 and ('Temp' in dp['name'] or 'Aussen' in dp['name']):
                                i += 1
                                continue

                        handle_output(client, dp['name'], value, dp['unit'])
                        i += 2 + byte_len
                        continue

        i += 1


def publish_homeassistant_discovery(client, clean_name, name, unit):
    """
    Publiziert Home Assistant Auto-Discovery Konfiguration.
    Wird nur einmal pro Topic aufgerufen.
    """
    if not MQTT_HOMEASSISTANT_DISCOVERY or clean_name in discovered_topics:
        return

    # Bestimme device_class und icon basierend auf Einheit und Namen
    device_class = None
    icon = None

    if unit == '°C' or 'temp' in clean_name.lower():
        device_class = 'temperature'
        icon = 'mdi:thermometer'
    elif unit == '%' and ('feucht' in clean_name.lower() or 'humidity' in clean_name.lower()):
        device_class = 'humidity'
        icon = 'mdi:water-percent'
    elif unit == '%' and 'lueft' in clean_name.lower():
        icon = 'mdi:fan'
    elif 'co2' in clean_name.lower():
        device_class = 'carbon_dioxide'
        icon = 'mdi:molecule-co2'
    elif 'voc' in clean_name.lower():
        device_class = 'volatile_organic_compounds'
        icon = 'mdi:air-filter'

    # Erstelle eindeutige ID für Home Assistant
    unique_id = f'hoval_{clean_name}'

    # Discovery Topic
    component = 'sensor'
    discovery_topic = f'{HOMEASSISTANT_PREFIX}/{component}/hoval/{clean_name}/config'

    # Discovery Payload
    config = {
        'name': f'Hoval {name}',
        'unique_id': unique_id,
        'state_topic': f'{TOPIC_BASE}/{clean_name}',
        'value_template': '{{ value_json.value }}',
        'unit_of_measurement': unit,
        'device': {
            'identifiers': ['hoval_homevent'],
            'name': 'Hoval HomeVent',
            'manufacturer': 'Hoval',
            'model': 'HomeVent',
        },
    }

    if device_class:
        config['device_class'] = device_class
    if icon:
        config['icon'] = icon

    # Publiziere Discovery Config als retained message
    try:
        client.publish(discovery_topic, json.dumps(config), retain=True)
        discovered_topics.add(clean_name)
        if DEBUG_CONSOLE:
            print(f' [DISCOVERY] Home Assistant Entity: {name}')
    except Exception as e:
        if DEBUG_CONSOLE:
            print(f' [DISCOVERY ERROR] {e}')


def handle_output(client, name, value, unit):
    clean_name = (
        name.replace(' ', '_')
        .replace('ä', 'ae')
        .replace('ö', 'oe')
        .replace('ü', 'ue')
        .replace('ß', 'ss')
        .replace('.', '')
        .replace('/', '_')
        .lower()
    )

    # Duplikatserkennung: Nur bei Änderung publizieren
    if last_sent.get(clean_name) != value:
        last_sent[clean_name] = value

        if DEBUG_CONSOLE:
            # Terminal-Ausgabe mit UTF-8
            try:
                print(f' [LOG] {name[:30]:30}: {value} {unit}')
            except UnicodeEncodeError:
                # Fallback falls Terminal kein UTF-8 unterstützt
                unit_ascii = unit.encode('ascii', errors='replace').decode('ascii')
                print(f' [LOG] {name[:30]:30}: {value} {unit_ascii}')

        if MQTT_ENABLED and client:
            try:
                # Home Assistant Auto-Discovery (nur beim ersten Mal)
                publish_homeassistant_discovery(client, clean_name, name, unit)

                # Publiziere Wert als retained message
                topic = f'{TOPIC_BASE}/{clean_name}'
                payload = json.dumps({'value': value, 'unit': unit})
                client.publish(topic, payload, retain=True)
            except:
                pass


def main():
    if not load_csv():
        return

    client = None
    if MQTT_ENABLED:
        try:
            client = mqtt.Client()

            # MQTT Callbacks für Fehler-Logging
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    print(f'MQTT verbunden ({MQTT_IP}).')
                else:
                    error_messages = {
                        1: 'Falsche Protokollversion',
                        2: 'Ungültige Client-ID',
                        3: 'Server nicht erreichbar',
                        4: 'Authentifizierung fehlgeschlagen (falscher Benutzername/Passwort)',
                        5: 'Nicht autorisiert',
                    }
                    error_msg = error_messages.get(rc, f'Unbekannter Fehler (Code: {rc})')
                    print(f'MQTT FEHLER: {error_msg}')

            def on_disconnect(client, userdata, rc):
                if rc != 0:
                    print(f'MQTT Verbindung verloren (Code: {rc}). Versuche Reconnect...')

            client.on_connect = on_connect
            client.on_disconnect = on_disconnect

            # Authentifizierung setzen, falls konfiguriert
            if MQTT_USERNAME and MQTT_PASSWORD:
                client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
                print(f'MQTT: Verwende Authentifizierung (User: {MQTT_USERNAME})')

            client.connect(MQTT_IP, MQTT_PORT, 60)
            client.loop_start()
        except Exception as e:
            print(f'MQTT nicht erreichbar -> Nur Konsolen-Ausgabe. ({e})')

    print('Starte Hoval Universal Listener...')

    while True:
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(15)
            s.connect((HOVAL_IP, HOVAL_PORT))
            print(f'Verbunden mit {HOVAL_IP}')

            while True:
                data = s.recv(4096)
                if not data:
                    break

                parts = data.split(b'\xff\x01')
                for part in parts:
                    if len(part) > 4:
                        process_stream(client, part)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f'Reconnect... ({e})')
            time.sleep(10)
        finally:
            if s:
                s.close()


if __name__ == '__main__':
    main()
