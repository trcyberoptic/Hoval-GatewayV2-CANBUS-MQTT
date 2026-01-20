"""DataUpdateCoordinator for Hoval Gateway."""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import struct
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_IGNORE_KEYWORDS,
    CONF_UNIT_ID,
    DEFAULT_IGNORE_KEYWORDS,
    DEFAULT_UNIT_ID,
    DOMAIN,
    UPDATE_INTERVAL,
    normalize_name,
)

_LOGGER = logging.getLogger(__name__)


class HovalDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Hoval data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.port = entry.data[CONF_PORT]
        self.unit_id = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)

        ignore_str = entry.data.get(CONF_IGNORE_KEYWORDS, DEFAULT_IGNORE_KEYWORDS)
        self.ignore_keywords = [kw.strip() for kw in ignore_str.split(',') if kw.strip()]

        self.datapoint_map = {}
        self.last_sent = {}
        self._socket = None
        self._reader_task = None
        self._running = False

        # Load CSV datapoints
        self._load_csv()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def _load_csv(self) -> None:
        """Load datapoints from CSV file."""
        csv_path = os.path.join(os.path.dirname(__file__), 'hoval_datapoints.csv')

        if not os.path.exists(csv_path):
            _LOGGER.warning("CSV file not found: %s", csv_path)
            return

        count = 0
        try:
            with open(csv_path, encoding='utf-8', errors='replace') as f:
                line = f.readline()
                delimiter = ';' if ';' in line else ','
                f.seek(0)

                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    if row.get('UnitName') != 'HV':
                        continue

                    # Filter by unit ID
                    try:
                        unit_id = int(row.get('UnitId', 0))
                        if self.unit_id and unit_id != self.unit_id:
                            continue
                    except:
                        pass

                    # Blacklist check
                    name = row['DatapointName']
                    if any(kw in name for kw in self.ignore_keywords):
                        continue

                    try:
                        dp_id = int(row['DatapointId'])
                        self.datapoint_map[dp_id] = {
                            'name': name,
                            'type': row['TypeName'],
                            'decimal': int(row.get('Decimal', 0)),
                            'unit': row.get('unit', ''),
                        }
                        count += 1
                    except (KeyError, ValueError):
                        continue

            _LOGGER.info("Loaded %d datapoints (Unit %d)", count, self.unit_id)
        except Exception as err:
            _LOGGER.error("Failed to load CSV: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Hoval device."""
        if not self._running:
            await self._start_connection()

        # Return current data
        return dict(self.last_sent)

    async def _start_connection(self) -> None:
        """Start connection to Hoval device."""
        if self._running:
            return

        self._running = True
        self._reader_task = asyncio.create_task(self._read_stream())

    async def _read_stream(self) -> None:
        """Read data stream from Hoval device."""
        buffer = b''

        while self._running:
            try:
                # Connect to device
                _LOGGER.info("Connecting to %s:%d", self.host, self.port)

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=15
                )

                _LOGGER.info("Connected to Hoval device")

                # Read data
                while self._running:
                    try:
                        data = await asyncio.wait_for(reader.read(4096), timeout=15)
                        if not data:
                            break

                        buffer += data
                        buffer = self._process_stream(buffer)

                    except asyncio.TimeoutError:
                        continue

                writer.close()
                await writer.wait_closed()

            except Exception as err:
                _LOGGER.error("Connection error: %s", err)

            if self._running:
                _LOGGER.info("Reconnecting in 10 seconds...")
                await asyncio.sleep(10)

    def _process_stream(self, data: bytes) -> bytes:
        """Process binary stream data."""
        # Process all complete frames (frame delimiter: 0xFF 0x01)
        while b'\xff\x01' in data:
            idx = data.index(b'\xff\x01')
            next_idx = data.find(b'\xff\x01', idx + 2)

            if next_idx == -1:
                # Incomplete frame
                break

            frame = data[idx:next_idx]
            data = data[next_idx:]

            # Parse frame
            self._parse_frame(frame)

        return data

    def _parse_frame(self, frame: bytes) -> None:
        """Parse a single frame."""
        # Special case: DatapointId=0 (outdoor temperature) uses different protocol
        if 0 in self.datapoint_map:
            self._scan_for_outdoor_temp(frame, self.datapoint_map[0])

        i = 2  # Skip frame delimiter

        while i < len(frame) - 2:
            # Try standard format (0x00 prefix + 2-byte ID)
            if i + 3 <= len(frame) and frame[i] == 0x00:
                dp_id = struct.unpack('>H', frame[i+1:i+3])[0]
                i += 3

                # Skip DatapointId=0 - handled by _scan_for_outdoor_temp
                if dp_id == 0:
                    continue

                if dp_id in self.datapoint_map:
                    dp_info = self.datapoint_map[dp_id]
                    value = self._decode_value(frame, i, dp_info)

                    if value is not None:
                        self._update_sensor(dp_info['name'], value, dp_info['unit'])

                    # Advance based on type
                    type_sizes = {'U8': 1, 'S16': 2, 'U16': 2, 'S32': 4, 'U32': 4}
                    i += type_sizes.get(dp_info['type'], 1)
                else:
                    i += 1
            else:
                i += 1

    def _scan_for_outdoor_temp(self, data: bytes, dp_info: dict) -> bool:
        """Scan frame for outdoor temperature using pattern matching.

        DatapointId=0 (outdoor temperature) uses a different protocol format.
        Pattern: [xx 00 00 00] [S16-value] [FF 02]

        Example positive: ... 32 00 00 00 00 1b ff 02 = 2.7°C (0x001B)
        Example negative: ... 00 00 00 00 ff f5 ff 02 = -1.1°C (0xFFF5)
        """
        # Need at least 8 bytes for the pattern
        if len(data) < 8:
            return False

        # Find all FF 02 terminators and check backwards
        for i in range(len(data) - 1):
            if data[i:i + 2] == b'\xff\x02':
                # FF 02 found at position i
                # Check if 6 bytes available before: [4-byte prefix] [2-byte value] [FF 02]
                if i < 6:
                    continue

                raw_bytes = data[i - 2:i]  # 2 bytes directly before FF 02 = value
                prefix = data[i - 6:i - 2]  # 4 bytes before that = prefix

                # Validate prefix pattern (needs consecutive 0x00 bytes)
                valid_prefix = False
                if prefix == b'\x00\x00\x00\x00':
                    valid_prefix = True
                elif prefix[1:4] == b'\x00\x00\x00':
                    # Last 3 bytes are 00 (first byte from previous datapoint)
                    valid_prefix = True
                elif prefix[0:3] == b'\x00\x00\x00':
                    # First 3 bytes are 00
                    valid_prefix = True
                elif prefix[1:3] == b'\x00\x00':
                    # At least 2 consecutive nulls in middle
                    valid_prefix = True

                if not valid_prefix:
                    continue

                # Skip known error codes
                if raw_bytes == b'\xff\xff':  # Classic null value
                    continue
                if raw_bytes == b'\xff\x02':  # Frame terminator
                    continue
                if raw_bytes == b'\x00\x00':  # Zero error code
                    continue
                # 0xFF00-0xFF01 are error codes (-25.6 to -25.5°C range)
                if raw_bytes[0] == 0xFF and raw_bytes[1] <= 0x01:
                    continue

                # Decode the S16 value
                try:
                    value = struct.unpack('>h', raw_bytes)[0]

                    # Apply decimal scaling (outdoor temp has decimal=1)
                    decimal = dp_info.get('decimal', 1)
                    if decimal > 0:
                        value = value / (10 ** decimal)
                        value = round(value, 2)

                    # Range check for outdoor temperature
                    if -40 <= value <= 50:
                        self._update_sensor(dp_info['name'], value, dp_info['unit'])
                        return True

                except Exception:
                    continue

        return False

    def _decode_value(self, data: bytes, offset: int, dp_info: dict) -> float | None:
        """Decode value based on type."""
        type_name = dp_info['type']
        decimal = dp_info['decimal']

        try:
            if type_name == 'U8':
                if offset + 1 > len(data):
                    return None
                raw = data[offset]
                if raw == 0xFF:
                    return None
                value = raw

            elif type_name == 'S16':
                if offset + 2 > len(data):
                    return None
                raw_bytes = data[offset:offset+2]

                # Filter error codes (0xFFFF = null value)
                if raw_bytes == b'\xff\xff':
                    return None
                if raw_bytes[0] == 0xFF and 0x00 <= raw_bytes[1] <= 0x05:
                    return None

                value = struct.unpack('>h', raw_bytes)[0]

                # Filter known error values
                if value in [-32768, 32767]:
                    return None

            elif type_name == 'U16':
                if offset + 2 > len(data):
                    return None
                raw = struct.unpack('>H', data[offset:offset+2])[0]
                if raw == 0xFFFF:
                    return None
                value = raw

            elif type_name in ['S32', 'U32']:
                if offset + 4 > len(data):
                    return None
                fmt = '>i' if type_name == 'S32' else '>I'
                value = struct.unpack(fmt, data[offset:offset+4])[0]

                # Filter null values
                if (type_name == 'S32' and value == -2147483648) or \
                   (type_name == 'U32' and value == 4294967295):
                    return None
            else:
                return None

            # Apply decimal scaling
            if decimal > 0:
                value = value / (10 ** decimal)

            return round(value, 2)

        except Exception:
            return None

    def _update_sensor(self, name: str, value: float, unit: str) -> None:
        """Update sensor value."""
        # Normalize name using shared function
        clean_name = normalize_name(name)

        # Check for change
        if clean_name in self.last_sent and self.last_sent[clean_name] == value:
            return

        # Anomaly filtering
        if unit == '°C':
            if abs(value - 25.5) < 0.1 or abs(value + 25.5) < 0.1:
                return
            if value < -40 or value > 70:
                return
            if value == 0.0 and 'aussen' in name.lower():
                if clean_name not in self.last_sent:
                    return

        # Update value
        self.last_sent[clean_name] = value

        # Trigger update
        self.async_set_updated_data(dict(self.last_sent))

    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        self._running = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
