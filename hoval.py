import socket
import struct
import csv
import json
import os
import time
import paho.mqtt.client as mqtt

# --- KONFIGURATION ---
HOVAL_IP = '10.0.0.95'
HOVAL_PORT = 3113
CSV_FILE = 'hoval_datapoints.csv'

# --- BLACKLIST ---
# Datenpunkte, deren Name eines dieser Wörter enthält, werden IGNORIERT.
# Hier "VOC" eintragen, da nicht verbaut.
IGNORE_KEYWORDS = ["VOC", "voc", "Luftqualität"]

# Logging
DEBUG_CONSOLE = True      # Zeigt Werte im Terminal
DEBUG_RAW = False         # Zeigt Hex-Code (nur für Profis)

# MQTT
MQTT_ENABLED = True       
MQTT_IP = '127.0.0.1'
MQTT_PORT = 1883
TOPIC_BASE = "hoval/homevent"

# Speicher
datapoint_map = {}
last_sent = {}

# --- CSV LADEN ---
def load_csv():
    if not os.path.exists(CSV_FILE):
        print(f"FEHLER: {CSV_FILE} fehlt!")
        return False

    print("Lade CSV...")
    count = 0
    try:
        with open(CSV_FILE, 'r', encoding='latin-1', errors='replace') as f:
            line = f.readline()
            delimiter = ';' if ';' in line else ','
            f.seek(0)
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                if row.get('UnitName') != 'HV': continue
                
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
        print(f"{count} Datenpunkte geladen (VOC ignoriert).")
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
            val = struct.unpack('>h', raw_bytes[0:2])[0]
            if val in [-32768, 32767, 255]:
                if DEBUG_RAW:
                    print(f" [NULL] {dp_info['name']}: S16={val} (Fehlercode)")
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
    # HYBRID-MODUS: CSV + Extra-Temperatur-Logik

    # 1. Normal-Scan: Suche nach 2-Byte IDs (ohne 0x00 Zwang!)
    for i in range(len(data) - 2):
        candidate_key = data[i:i+2]

        if candidate_key in datapoint_map:
            dp = datapoint_map[candidate_key]

            byte_len = 1 if '8' in dp['type'] else 2
            if '32' in dp['type']: byte_len = 4

            if len(data) > i + 2 + byte_len:
                raw_bytes = data[i+2 : i+2+byte_len]
                value = decode_smart(raw_bytes, dp)

                if value is not None:
                    # Plausibilitätscheck nur für extreme Werte
                    if "Temp" in dp['name'] or "Aussen" in dp['name']:
                        if not (-40 <= value <= 70):
                            if DEBUG_CONSOLE:
                                print(f" [RANGE] {dp['name']}: {value}°C außerhalb -40..70")
                            continue

                    handle_output(client, dp['name'], value, dp['unit'])

    # 2. EXTRA-TEMPERATUR-LOGIK: Direktsuche nach bekannten Temp-IDs
    # ID 0 = Außenluft-Temperatur (kritisch!)
    temp_ids = [0, 1, 2, 3, 4, 5]  # Häufige Temperatur-IDs

    for temp_id in temp_ids:
        id_pattern = struct.pack('>H', temp_id)
        pos = 0
        while pos < len(data):
            found = data.find(id_pattern, pos)
            if found == -1:
                break

            # Versuche S16-Temperatur zu lesen (2 Bytes nach ID)
            if found + 4 <= len(data):
                raw_bytes = data[found+2:found+4]

                # Nicht 0xFF-Check
                if raw_bytes != b'\xff\xff':
                    try:
                        raw_val = struct.unpack('>h', raw_bytes)[0]
                        if raw_val != -32768 and raw_val != 32767:
                            temp_c = raw_val / 10.0

                            if -40 <= temp_c <= 70:
                                name = f"Temp_ID_{temp_id}"
                                handle_output(client, name, round(temp_c, 1), "°C")
                    except:
                        pass

            pos = found + 1

def handle_output(client, name, value, unit):
    clean_name = name.replace(" ", "_").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss").replace(".", "").replace("/", "_").lower()
    
    if last_sent.get(clean_name) != value:
        last_sent[clean_name] = value
        
        if DEBUG_CONSOLE:
            print(f" [LOG] {name[:30]:30}: {value} {unit}")

        if MQTT_ENABLED and client:
            try:
                topic = f"{TOPIC_BASE}/{clean_name}"
                payload = json.dumps({"value": value, "unit": unit})
                client.publish(topic, payload)
            except: pass

def main():
    if not load_csv(): return
    
    client = None
    if MQTT_ENABLED:
        try:
            client = mqtt.Client()
            client.connect(MQTT_IP, MQTT_PORT, 60)
            client.loop_start()
            print(f"MQTT verbunden ({MQTT_IP}).")
        except:
            print("MQTT nicht erreichbar -> Nur Konsolen-Ausgabe.")

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