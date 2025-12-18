import socket
import struct
import csv
import json
import os
import time
import sys
import paho.mqtt.client as mqtt

# UTF-8 Encoding für Terminal sicherstellen
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# --- KONFIGURATION ---
HOVAL_IP = '10.0.0.95'
HOVAL_PORT = 3113
CSV_FILE = 'hoval_datapoints.csv'

# --- FILTER ---
# Nur diese UnitId laden (z.B. 513)
UNIT_ID_FILTER = 513

# --- BLACKLIST ---
# Datenpunkte, deren Name eines dieser Wörter enthält, werden IGNORIERT.
# Hier "VOC" eintragen, wenn nicht verbaut.
IGNORE_KEYWORDS = ["CO2", "VOC", "voc", "Luftqualität"]

# Logging
DEBUG_CONSOLE = True      # Zeigt Werte im Terminal
DEBUG_RAW = False         # Zeigt Hex-Code (für Debugging)

# MQTT
MQTT_ENABLED = True
MQTT_IP = 'homeassistant'
MQTT_PORT = 1883
MQTT_USERNAME = ''         # MQTT Benutzername (leer lassen für anonymous)
MQTT_PASSWORD = ''         # MQTT Passwort (leer lassen für anonymous)
TOPIC_BASE = "hoval/homevent"
MQTT_HOMEASSISTANT_DISCOVERY = True  # Home Assistant Auto-Discovery aktivieren
HOMEASSISTANT_PREFIX = "homeassistant"  # Home Assistant Discovery Prefix

# Speicher
datapoint_map = {}
last_sent = {}
discovered_topics = set()  # Bereits registrierte Topics für Home Assistant

# --- CSV LADEN ---
def load_csv():
    if not os.path.exists(CSV_FILE):
        print(f"FEHLER: {CSV_FILE} fehlt!")
        return False

    print("Lade CSV...")
    count = 0
    try:
        with open(CSV_FILE, 'r', encoding='utf-8', errors='replace') as f:
            line = f.readline()
            delimiter = ';' if ';' in line else ','
            f.seek(0)
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                if row.get('UnitName') != 'HV': continue

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
                        'id': dp_id  # Speichere auch die numerische ID
                    }
                    count += 1
                except: continue
        print(f"{count} Datenpunkte geladen (Unit {UNIT_ID_FILTER}, VOC ignoriert).")
        return True
    except Exception as e:
        print(f"CSV Fehler: {e}")
        return False

# --- DECODER ---
def decode_smart(raw_bytes, dp_info):
    if raw_bytes == b'\xff' * len(raw_bytes):
        if DEBUG_RAW:
            print(f" [NULL] {dp_info['name']}: Alle Bytes 0xFF (Fehlercode)")
        return None

    val = 0
    type_name = dp_info['type']

    try:
        if type_name == 'U8':
            val = raw_bytes[0]
            if val == 255:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: U8=255 (Fehlercode)")
                return None

        elif type_name == 'S16':
            # Prüfe ZUERST ob einzelne Bytes 0xFF sind (Fehlercode)
            if raw_bytes[0] == 0xFF or raw_bytes[1] == 0xFF:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: S16={raw_bytes.hex()} enthält 0xFF (Fehlercode)")
                return None

            val = struct.unpack('>h', raw_bytes[0:2])[0]
            if val in [-32768, 32767]:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: S16={val} (Extremwert/Fehlercode)")
                return None

        elif type_name == 'U16':
            val = struct.unpack('>H', raw_bytes[0:2])[0]
            if val == 65535:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: U16=65535 (Fehlercode)")
                return None

        elif type_name == 'S32':
            val = struct.unpack('>i', raw_bytes[0:4])[0]
            if val == -2147483648:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: S32={val} (Fehlercode)")
                return None

        elif type_name == 'U32':
            val = struct.unpack('>I', raw_bytes[0:4])[0]
            if val == 4294967295:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: U32={val} (Fehlercode)")
                return None
        else:
            return None 

        # Dezimal anwenden
        if dp_info['decimal'] > 0:
            val = val / (10 ** dp_info['decimal'])
            val = round(val, 2)

            # --- FILTER (REDUZIERT) ---
            # Nur noch 25.5 und 112.0 filtern - 0.0 ist ein echter Wert!
            if val == 25.5 and "Temp" in dp_info['name']:
                if DEBUG_CONSOLE:
                    print(f" [FILTER] 25.5°C erkannt bei {dp_info['name']} - gefiltert")
                return None

            if val == 112.0:
                if DEBUG_CONSOLE:
                    print(f" [FILTER] 112.0 erkannt bei {dp_info['name']} - gefiltert")
                return None

        return val
    except:
        return None

def process_stream(client, data):
    # Scan durch Frame (bereits durch 0xFF 0x01 getrennt in main())
    # Jetzt flexibel: Akzeptiere IDs mit ODER ohne 0x00 Prefix

    i = 0
    while i < len(data) - 2:
        # Variante 1: 3-Byte ID mit 0x00 Prefix (klassisch)
        if i < len(data) - 3:
            key_3byte = data[i:i+3]
            if key_3byte[0] == 0x00:  # Hat 0x00 Prefix?
                key_2byte = key_3byte[1:3]  # Extrahiere die echte 2-Byte ID

                if key_2byte in datapoint_map:
                    dp = datapoint_map[key_2byte]
                    byte_len = 1 if '8' in dp['type'] else 2
                    if '32' in dp['type']: byte_len = 4

                    if i + 3 + byte_len <= len(data):
                        raw_bytes = data[i+3 : i+3+byte_len]

                        if DEBUG_RAW and "Aussen" in dp['name']:
                            hex_str = raw_bytes.hex()
                            print(f" [RAW] {dp['name']} @ pos {i}: 0x{hex_str}")

                        value = decode_smart(raw_bytes, dp)

                        if value is not None:
                            if "Temp" in dp['name'] or "Aussen" in dp['name']:
                                if not (-40 <= value <= 70):
                                    if DEBUG_RAW:
                                        print(f" [RANGE] {dp['name']}: {value}°C @ pos {i}")
                                    i += 1
                                    continue

                            handle_output(client, dp['name'], value, dp['unit'])
                            i += 3 + byte_len  # Überspringe verarbeitete Bytes
                            continue

        # Variante 2: Direkte 2-Byte ID (neu, für Temperaturen ohne Prefix)
        # NUR für sehr niedrige IDs (0-5) und NUR wenn Position > 0
        key_2byte = data[i:i+2]
        if key_2byte in datapoint_map:
            dp = datapoint_map[key_2byte]

            # WICHTIG: Nur für IDs 0-5 und NICHT am Frame-Anfang (pos 0)
            if dp['id'] <= 5 and i > 0:
                byte_len = 1 if '8' in dp['type'] else 2
                if '32' in dp['type']: byte_len = 4

                if i + 2 + byte_len <= len(data):
                    raw_bytes = data[i+2 : i+2+byte_len]

                    # Extra-Check für NOPREFIX: 0x0000 ist auch ein Fehlercode
                    if raw_bytes == b'\x00\x00':
                        i += 1
                        continue

                    value = decode_smart(raw_bytes, dp)

                    if value is not None:
                        # Strengere Prüfung für niedrige IDs ohne Prefix
                        if "Temp" in dp['name'] or "Aussen" in dp['name']:
                            if not (-40 <= value <= 70):
                                i += 1
                                continue

                        # Extra-Validierung: Wert sollte stabil sein
                        # (verhindert wilde Sprünge durch False Positives)
                        prev_val = last_sent.get(dp['name'].replace(" ", "_").lower())
                        if prev_val is not None:
                            # Wenn Änderung > 20 Grad, wahrscheinlich False Positive
                            if abs(value - prev_val) > 20:
                                i += 1
                                continue
                        else:
                            # Beim ersten Wert: 0.0°C ist sehr verdächtig (oft Fehlercode)
                            # Nur akzeptieren wenn es der einzige Wert in diesem Frame ist
                            if value == 0.0 and ("Temp" in dp['name'] or "Aussen" in dp['name']):
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

    if unit == "°C" or "temp" in clean_name.lower():
        device_class = "temperature"
        icon = "mdi:thermometer"
    elif unit == "%" and ("feucht" in clean_name.lower() or "humidity" in clean_name.lower()):
        device_class = "humidity"
        icon = "mdi:water-percent"
    elif unit == "%" and "lueft" in clean_name.lower():
        icon = "mdi:fan"
    elif "co2" in clean_name.lower():
        device_class = "carbon_dioxide"
        icon = "mdi:molecule-co2"
    elif "voc" in clean_name.lower():
        device_class = "volatile_organic_compounds"
        icon = "mdi:air-filter"

    # Erstelle eindeutige ID für Home Assistant
    unique_id = f"hoval_{clean_name}"

    # Discovery Topic
    component = "sensor"
    discovery_topic = f"{HOMEASSISTANT_PREFIX}/{component}/hoval/{clean_name}/config"

    # Discovery Payload
    config = {
        "name": f"Hoval {name}",
        "unique_id": unique_id,
        "state_topic": f"{TOPIC_BASE}/{clean_name}",
        "value_template": "{{ value_json.value }}",
        "unit_of_measurement": unit,
        "device": {
            "identifiers": ["hoval_homevent"],
            "name": "Hoval HomeVent",
            "manufacturer": "Hoval",
            "model": "HomeVent"
        }
    }

    if device_class:
        config["device_class"] = device_class
    if icon:
        config["icon"] = icon

    # Publiziere Discovery Config als retained message
    try:
        client.publish(discovery_topic, json.dumps(config), retain=True)
        discovered_topics.add(clean_name)
        if DEBUG_CONSOLE:
            print(f" [DISCOVERY] Home Assistant Entity: {name}")
    except Exception as e:
        if DEBUG_CONSOLE:
            print(f" [DISCOVERY ERROR] {e}")

def handle_output(client, name, value, unit):
    clean_name = name.replace(" ", "_").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss").replace(".", "").replace("/", "_").lower()

    # Duplikatserkennung: Nur bei Änderung publizieren
    if last_sent.get(clean_name) != value:
        last_sent[clean_name] = value

        if DEBUG_CONSOLE:
            # Terminal-Ausgabe mit UTF-8
            try:
                print(f" [LOG] {name[:30]:30}: {value} {unit}")
            except UnicodeEncodeError:
                # Fallback falls Terminal kein UTF-8 unterstützt
                unit_ascii = unit.encode('ascii', errors='replace').decode('ascii')
                print(f" [LOG] {name[:30]:30}: {value} {unit_ascii}")

        if MQTT_ENABLED and client:
            try:
                # Home Assistant Auto-Discovery (nur beim ersten Mal)
                publish_homeassistant_discovery(client, clean_name, name, unit)

                # Publiziere Wert als retained message
                topic = f"{TOPIC_BASE}/{clean_name}"
                payload = json.dumps({"value": value, "unit": unit})
                client.publish(topic, payload, retain=True)
            except: pass

def main():
    if not load_csv(): return
    
    client = None
    if MQTT_ENABLED:
        try:
            client = mqtt.Client()

            # Authentifizierung setzen, falls konfiguriert
            if MQTT_USERNAME and MQTT_PASSWORD:
                client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
                print(f"MQTT: Verwende Authentifizierung (User: {MQTT_USERNAME})")

            client.connect(MQTT_IP, MQTT_PORT, 60)
            client.loop_start()
            print(f"MQTT verbunden ({MQTT_IP}).")
        except Exception as e:
            print(f"MQTT nicht erreichbar -> Nur Konsolen-Ausgabe. ({e})")

    print("Starte Hoval Universal Listener...")
    
    while True:
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(15)
            s.connect((HOVAL_IP, HOVAL_PORT))
            print(f"Verbunden mit {HOVAL_IP}")
            
            while True:
                data = s.recv(4096)
                if not data: break
                
                parts = data.split(b'\xff\x01')
                for part in parts:
                    if len(part) > 4:
                        process_stream(client, part)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Reconnect... ({e})")
            time.sleep(10)
        finally:
            if s: s.close()

if __name__ == "__main__":
    main()