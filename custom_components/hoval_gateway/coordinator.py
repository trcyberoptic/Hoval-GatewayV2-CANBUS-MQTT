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

                    except TimeoutError:
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
        # Process all complete frames
        while b'\\xff\\x01' in data:
            idx = data.index(b'\\xff\\x01')
            next_idx = data.find(b'\\xff\\x01', idx + 2)

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
        i = 2  # Skip frame delimiter

        while i < len(frame) - 2:
            # Try standard format (0x00 prefix + 2-byte ID)
            if i + 3 <= len(frame) and frame[i] == 0x00:
                dp_id = struct.unpack('>H', frame[i+1:i+3])[0]
                i += 3

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

                # Filter error codes
                if raw_bytes == b'\\xff\\xff':
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
        # Normalize name
        clean_name = name.lower().replace(' ', '_')
        clean_name = clean_name.replace('ä', 'ae').replace('ö', 'oe')
        clean_name = clean_name.replace('ü', 'ue').replace('ß', 'ss')
        clean_name = clean_name.replace('.', '').replace('/', '')

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
