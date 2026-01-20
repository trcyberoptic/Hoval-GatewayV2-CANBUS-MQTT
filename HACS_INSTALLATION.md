# HACS Installation Guide

## Übersicht

Mit der Home Assistant Integration kannst du dein Hoval Gateway direkt in Home Assistant integrieren - **ohne separaten systemd-Service oder MQTT-Broker!**

## Vorteile der HACS-Integration

✅ **Keine separate Installation nötig** - läuft direkt in Home Assistant
✅ **UI-basierte Konfiguration** - keine config.ini oder YAML nötig
✅ **Automatische Updates** über HACS
✅ **Native Sensoren** - erscheinen direkt als HA-Entities
✅ **Kein MQTT nötig** - direkte Integration

## Voraussetzungen

- Home Assistant installiert (Version 2024.1.0 oder neuer)
- [HACS](https://hacs.xyz/) installiert
- Hoval-Gerät mit Netzwerk-Modul (LAN/WIFI) im Netzwerk erreichbar

## Installation

### Schritt 1: Repository in HACS hinzufügen

1. Öffne Home Assistant
2. Gehe zu **HACS** → **Integrations**
3. Klicke auf die **drei Punkte** (⋮) oben rechts
4. Wähle **Custom repositories**
5. Füge das Repository hinzu:
   - **Repository**: `https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT`
   - **Category**: `Integration`
6. Klicke auf **Add**

### Schritt 2: Integration installieren

1. Suche in HACS nach "**Hoval Gateway V2**"
2. Klicke auf die Integration
3. Klicke auf **Download**
4. Wähle die neueste Version
5. Klicke auf **Download**

### Schritt 3: Home Assistant neustarten

1. Gehe zu **Einstellungen** → **System**
2. Klicke auf **Neu starten**
3. Warte bis Home Assistant vollständig neugestartet ist

### Schritt 4: Integration konfigurieren

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Klicke auf **+ Integration hinzufügen**
3. Suche nach "**Hoval Gateway V2**"
4. Fülle das Formular aus:
   - **IP-Adresse**: Die IP deines Hoval-Geräts (z.B. `10.0.0.95`)
   - **Port**: CAN-BUS TCP-Port (Standard: `3113`)
   - **Unit-ID**: Filtert auf diese Unit (Standard: `513`)
   - **Zu ignorierende Schlüsselwörter**: Kommagetrennt (z.B. `CO2,VOC,voc,Luftqualität`)
5. Klicke auf **Absenden**

## Nach der Installation

### Sensoren finden

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Klicke auf die Hoval Gateway Integration
3. Du siehst das Gerät "**Hoval HomeVent**"
4. Klicke darauf, um alle Sensoren zu sehen

Alle Sensoren haben das Präfix "**Hoval**", z.B.:
- `sensor.hoval_temperatur_aussenluft`
- `sensor.hoval_temperatur_abluft`
- `sensor.hoval_lueftungsmodulation`

### Sensoren in Lovelace Dashboard hinzufügen

```yaml
type: entities
title: Hoval Lüftung
entities:
  - entity: sensor.hoval_temperatur_aussenluft
    name: Außentemperatur
  - entity: sensor.hoval_temperatur_abluft
    name: Abluft Temperatur
  - entity: sensor.hoval_lueftungsmodulation
    name: Lüftung
  - entity: sensor.hoval_feuchtigkeit_abluft
    name: Luftfeuchtigkeit
```

## Unterschied zur manuellen Installation

| Feature | HACS Integration | Manuelle Installation (systemd) |
|---------|------------------|----------------------------------|
| Installation | UI-basiert | Terminal/SSH |
| Konfiguration | UI-basiert | config.ini editieren |
| Updates | Automatisch via HACS | Manuell (.deb-Paket) |
| MQTT nötig | ❌ Nein | ✅ Ja |
| Separater Service | ❌ Nein | ✅ Ja (systemd) |
| Sensoren | Native HA-Entities | MQTT-basiert |
| Logs | HA Core Logs | /var/log/hoval-gateway/ |

## Migration von systemd zu HACS

Falls du bereits den systemd-Service verwendest:

### Schritt 1: Alten Service stoppen

```bash
sudo systemctl stop hoval-gateway
sudo systemctl disable hoval-gateway
```

### Schritt 2: HACS-Integration installieren (siehe oben)

### Schritt 3: MQTT-Sensoren entfernen (optional)

Wenn du die MQTT-Sensoren aus deiner `configuration.yaml` entfernen möchtest:

1. Öffne `configuration.yaml`
2. Entferne alle `hoval/homevent` MQTT-Sensor-Definitionen
3. Starte Home Assistant neu

Die HACS-Integration erstellt automatisch native Sensoren mit denselben Daten!

### Schritt 4: Altes Paket deinstallieren (optional)

```bash
sudo apt remove hoval-gateway
```

## Troubleshooting

### Integration erscheint nicht in der Liste

- Stelle sicher, dass HACS korrekt installiert ist
- Lösche den Browser-Cache
- Starte Home Assistant neu

### Verbindung schlägt fehl

1. Prüfe die IP-Adresse:
   ```bash
   ping <ip-adresse>
   ```

2. Prüfe den Port:
   ```bash
   telnet <ip-adresse> 3113
   ```

3. Prüfe die Logs:
   - **Einstellungen** → **System** → **Logs**
   - Suche nach `hoval_gateway`

### Keine Sensoren sichtbar

- Warte 1-2 Minuten nach der Installation
- Sensoren erscheinen erst, wenn das Gateway Daten empfängt
- Prüfe die Logs auf Fehlermeldungen

### Sensoren zeigen "Unavailable"

- Das Gateway versucht möglicherweise, sich zu verbinden
- Prüfe die Netzwerkverbindung zum Hoval-Gerät
- Prüfe die Logs für Verbindungsfehler

## Updates

Updates werden automatisch über HACS angezeigt:

1. Gehe zu **HACS** → **Integrations**
2. Wenn ein Update verfügbar ist, siehst du einen Hinweis
3. Klicke auf **Update**
4. Starte Home Assistant neu

## Deinstallation

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Klicke auf die Hoval Gateway Integration
3. Klicke auf **Löschen**
4. Gehe zu **HACS** → **Integrations**
5. Suche "Hoval Gateway V2"
6. Klicke auf die drei Punkte (⋮)
7. Wähle **Remove**

## Support

Bei Problemen:
- Prüfe die [GitHub Issues](https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/issues)
- Erstelle ein neues Issue mit:
  - Home Assistant Version
  - Hoval Gateway Version
  - Logs (Einstellungen → System → Logs)
  - Fehlermeldungen

## Weitere Informationen

- [Haupt-README](README.md) - Vollständige Dokumentation
- [CLAUDE.md](CLAUDE.md) - Entwickler-Dokumentation
- [GitHub Repository](https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT)
