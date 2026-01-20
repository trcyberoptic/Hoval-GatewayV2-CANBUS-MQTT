# Hoval Gateway V2 - Home Assistant Integration

This is the Home Assistant custom component for the Hoval Gateway V2.

## Installation via HACS

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations → ⋮ (three dots) → Custom repositories
   - Add: `https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT`
   - Category: Integration
3. Click "Install"
4. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Hoval Gateway V2"
4. Enter your configuration:
   - **IP Address**: The IP address of your Hoval device (e.g., `10.0.0.95`)
   - **Port**: CAN-BUS TCP port (default: `3113`)
   - **Unit ID**: Filter for specific unit (default: `513`)
   - **Ignore Keywords**: Comma-separated keywords to ignore (default: `CO2,VOC,voc,Luftqualität`)

## Features

- Native Home Assistant integration - no separate service needed
- Automatic sensor discovery for all datapoints
- Real-time updates via CAN-BUS protocol
- Temperature, humidity, and ventilation sensors
- German datapoint names automatically normalized
- Intelligent error code filtering

## Sensors

All sensors are automatically created based on your CSV configuration. Common sensors include:

- Outdoor air temperature
- Exhaust air temperature
- Supply air temperature
- Humidity sensors
- Ventilation modulation
- Operating mode

## Supported Devices

- Hoval HomeVent series with CAN-BUS interface
- Hoval network module (LAN or WIFI)

## Troubleshooting

### Connection Issues
- Verify the IP address is correct: `ping <ip-address>`
- Check that port 3113 is accessible: `telnet <ip-address> 3113`
- Ensure firewall allows TCP port 3113

### No Sensors Appearing
- Wait a few minutes for sensors to appear after initial connection
- Check Home Assistant logs for errors
- Verify your Unit ID matches your device

## Support

For issues, please visit: https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/issues
