#!/usr/bin/env python3
"""Debug script to dump raw frames and find outdoor temperature pattern."""

import socket
import struct

HOVAL_IP = '10.0.0.95'
HOVAL_PORT = 3113

# Zieltemperatur (aktuell ca. +2.x°C)
TARGET_TEMP_MIN = 2.0
TARGET_TEMP_MAX = 3.5


def find_target_temp(data):
    """Suche nach dem Zieltemperaturwert im Frame."""
    results = []

    # Scanne alle 2-Byte Sequenzen als S16
    for i in range(len(data) - 1):
        raw = data[i : i + 2]
        try:
            val = struct.unpack('>h', raw)[0] / 10
            if TARGET_TEMP_MIN <= val <= TARGET_TEMP_MAX:
                # Zeige Kontext
                start = max(0, i - 4)
                end = min(len(data), i + 6)
                context = data[start:end]
                results.append(f'  *** FOUND {val}°C @ pos {i}: {context.hex()} (raw=0x{raw.hex()})')
        except:
            pass

    return results


def find_temp_pattern(data):
    """Suche nach möglichen Temperaturwerten im Frame."""
    results = []

    # Suche nach FF 02 (bekannter Terminator)
    for i in range(len(data) - 1):
        if data[i : i + 2] == b'\xff\x02':
            # Zeige Kontext vor FF 02
            start = max(0, i - 10)
            context = data[start : i + 2]
            results.append(f'  FF02 @ pos {i}: ...{context.hex()}')

            # Wenn 2 Bytes vor FF02, versuche als S16 zu dekodieren
            if i >= 2:
                raw = data[i - 2 : i]
                val = struct.unpack('>h', raw)[0] / 10
                if -40 <= val <= 50:
                    results.append(f'    -> Mögliche Temp: {val}°C (raw=0x{raw.hex()})')

    return results


def main():
    print(f'Verbinde mit {HOVAL_IP}:{HOVAL_PORT}...')

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(15)
    s.connect((HOVAL_IP, HOVAL_PORT))
    print('Verbunden. Sammle Frames...\n')

    frame_count = 0
    try:
        while frame_count < 20:  # Nur 20 Frames
            data = s.recv(4096)
            if not data:
                break

            parts = data.split(b'\xff\x01')
            for part in parts:
                if len(part) > 10:
                    frame_count += 1
                    print(f'=== Frame {frame_count} ({len(part)} bytes) ===')

                    # Hex dump in Zeilen
                    hex_str = part.hex()
                    for j in range(0, len(hex_str), 64):
                        pos = j // 2
                        print(f'  {pos:4d}: {hex_str[j : j + 64]}')

                    # Suche nach Zieltemperatur (2.x°C)
                    target = find_target_temp(part)
                    if target:
                        print('  ZIELTEMPERATUR GEFUNDEN:')
                        for t in target:
                            print(t)

                    # Suche nach Temperatur-Pattern
                    patterns = find_temp_pattern(part)
                    if patterns:
                        print('  Gefundene FF02 Terminatoren:')
                        for p in patterns:
                            print(p)
                    print()

    except KeyboardInterrupt:
        pass
    finally:
        s.close()
        print('\nFertig.')


if __name__ == '__main__':
    main()
