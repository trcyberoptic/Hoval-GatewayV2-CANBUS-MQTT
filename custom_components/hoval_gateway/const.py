"""Constants for the Hoval Gateway integration."""

DOMAIN = "hoval_gateway"

# Configuration keys
CONF_UNIT_ID = "unit_id"
CONF_IGNORE_KEYWORDS = "ignore_keywords"

# Defaults
DEFAULT_PORT = 3113
DEFAULT_UNIT_ID = 513
DEFAULT_IGNORE_KEYWORDS = "CO2,VOC,voc,Luftqualität"
DEFAULT_SCAN_INTERVAL = 5  # seconds

# Update coordinator
UPDATE_INTERVAL = 5  # seconds


def normalize_name(name: str) -> str:
    """Normalize datapoint name for MQTT topics and entity IDs.

    Matches the normalization logic in hoval.py for consistency.
    """
    return (
        name.replace(' ', '_')
        .replace('ä', 'ae')
        .replace('ö', 'oe')
        .replace('ü', 'ue')
        .replace('ß', 'ss')
        .replace('.', '')
        .replace('/', '_')
        .replace('(', '')
        .replace(')', '')
        .replace('[', '')
        .replace(']', '')
        .replace('{', '')
        .replace('}', '')
        .replace("'", '')
        .replace('"', '')
        .replace('!', '')
        .replace('?', '')
        .replace('#', '')
        .replace('+', '')
        .lower()
    )
