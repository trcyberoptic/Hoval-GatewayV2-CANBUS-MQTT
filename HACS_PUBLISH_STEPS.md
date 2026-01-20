# HACS Veröffentlichung - Nächste Schritte

## ✅ Was wurde erstellt?

Die folgende Struktur wurde für die HACS-Integration erstellt:

```
Hoval-GatewayV2-CANBUS-MQTT/
├── custom_components/
│   └── hoval_gateway/
│       ├── __init__.py              # Integration Setup
│       ├── manifest.json            # Metadaten
│       ├── const.py                 # Konstanten
│       ├── config_flow.py           # UI-Konfiguration
│       ├── coordinator.py           # Datenmanagement
│       ├── sensor.py                # Sensor-Platform
│       ├── hoval_datapoints.csv     # Datenpunkt-Definitionen
│       ├── strings.json             # UI-Texte
│       ├── translations/
│       │   ├── en.json              # Englische Übersetzung
│       │   └── de.json              # Deutsche Übersetzung
│       └── README.md                # Integration-Dokumentation
│
├── hacs.json                        # HACS-Manifest
├── .github/workflows/validate.yml   # HACS-Validierung
├── HACS_INSTALLATION.md             # Installations-Anleitung
└── README.md (aktualisiert)         # Haupt-Dokumentation
```

## 📋 Checkliste vor der Veröffentlichung

### 1. Code testen

- [ ] Integration in Test-Home-Assistant installieren
- [ ] Konfiguration über UI testen
- [ ] Sensoren überprüfen (erscheinen sie korrekt?)
- [ ] Verbindung zum Hoval-Gerät testen
- [ ] Logs auf Fehler prüfen

### 2. Repository vorbereiten

- [ ] Alle Änderungen committen:
  ```bash
  git add .
  git commit -m "feat: Add Home Assistant HACS integration"
  git push
  ```

- [ ] GitHub Actions prüfen:
  - Gehe zu: https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/actions
  - Warte bis "Validate" Workflow durchläuft
  - Behebe eventuelle Fehler

### 3. Release erstellen

- [ ] Gehe zu: https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/releases
- [ ] Klicke auf "Draft a new release"
- [ ] Tag: `v3.0.0` (neue Major-Version wegen HACS-Integration)
- [ ] Title: `v3.0.0 - Home Assistant HACS Integration`
- [ ] Release Notes:

```markdown
## 🎉 Major Release: Home Assistant HACS Integration

### Neue Features

- ✅ **Native Home Assistant Integration**: Läuft direkt in HA, kein separater Service nötig
- ✅ **HACS-Support**: Installation und Updates über HACS
- ✅ **UI-Konfiguration**: Config Flow für einfache Einrichtung
- ✅ **Native Sensoren**: Keine MQTT-Konfiguration erforderlich
- ✅ **Mehrsprachig**: Deutsche und englische Übersetzungen

### Installation

**Via HACS (Empfohlen):**
1. HACS → Integrations → Custom repositories
2. Repository: `https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT`
3. Kategorie: Integration
4. Suche "Hoval Gateway V2" und installieren

**Via .deb-Paket (Standalone):**
Weiterhin verfügbar für Standalone-Installationen

Siehe [HACS_INSTALLATION.md](https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/blob/main/HACS_INSTALLATION.md) für Details.

### Breaking Changes

Keine - bestehende systemd/MQTT-Installationen funktionieren weiterhin.

### Migration

Siehe [HACS_INSTALLATION.md - Migration](https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT/blob/main/HACS_INSTALLATION.md#migration-von-systemd-zu-hacs)
```

### 4. Bei HACS registrieren (Optional)

**Achtung:** Dieser Schritt ist optional. Deine Integration kann bereits jetzt über "Custom repositories" installiert werden!

Falls du möchtest, dass deine Integration im Standard-HACS-Katalog erscheint:

- [ ] Erstelle einen PR bei: https://github.com/hacs/default
- [ ] Füge dein Repository zur Integration-Liste hinzu
- [ ] Warte auf Review und Merge (kann mehrere Tage dauern)

**Vorteil:** Benutzer müssen die Repository-URL nicht manuell eingeben
**Nachteil:** Längerer Review-Prozess

### 5. Dokumentation aktualisieren

- [ ] README Badge hinzufügen:
  ```markdown
  [![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
  ```

- [ ] Screenshots hinzufügen (optional):
  - Configuration UI
  - Sensor-Liste
  - Lovelace Dashboard Beispiel

## 🧪 Test-Anleitung

### Lokale Installation testen

1. **Test-Home-Assistant-Instanz vorbereiten:**
   ```bash
   # In einer VM oder Docker-Container
   docker run -d --name ha-test \
     -p 8123:8123 \
     -v $(pwd)/config:/config \
     homeassistant/home-assistant:latest
   ```

2. **Integration manuell installieren:**
   ```bash
   # In config-Verzeichnis
   mkdir -p custom_components
   cp -r /pfad/zu/Hoval-GatewayV2-CANBUS-MQTT/custom_components/hoval_gateway \
         custom_components/
   ```

3. **Home Assistant neustarten und testen:**
   - Einstellungen → Geräte & Dienste
   - Integration hinzufügen
   - "Hoval Gateway V2" suchen

### HACS Custom Repository testen

1. **HACS installieren** (falls nicht vorhanden)
2. **Custom Repository hinzufügen:**
   - HACS → Integrations → ⋮ → Custom repositories
   - URL: `https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT`
   - Kategorie: Integration
3. **Installation testen**
4. **Update-Funktion testen** (neuen Release erstellen und Update prüfen)

## 🐛 Bekannte Probleme und Lösungen

### Problem: "Integration not found"

**Lösung:**
- Stelle sicher, dass `manifest.json` korrekt ist
- Domain in `manifest.json` muss mit Ordnername übereinstimmen (`hoval_gateway`)
- Home Assistant neustarten

### Problem: "Requirements not met"

**Lösung:**
- Prüfe `manifest.json` → `requirements` ist leer (keine externen Dependencies)
- Falls `paho-mqtt` nötig: In `manifest.json` ergänzen: `"requirements": ["paho-mqtt==1.6.1"]`

### Problem: Validierung schlägt fehl

**Lösung:**
```bash
# Lokal validieren
pip install homeassistant
python -m homeassistant.scripts.hassfest validate --integration-path custom_components/hoval_gateway
```

## 📚 Weiterführende Ressourcen

- [HACS Documentation](https://hacs.xyz/)
- [Home Assistant Integration Development](https://developers.home-assistant.io/docs/creating_integration_manifest)
- [Home Assistant Config Flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)
- [HACS Action für CI/CD](https://github.com/hacs/action)

## 🎯 Nächste Schritte nach der Veröffentlichung

1. **Community informieren:**
   - Home Assistant Community Forum Post
   - Reddit r/homeassistant
   - Hoval-Nutzer-Communities

2. **Monitoring:**
   - GitHub Issues im Auge behalten
   - Feedback sammeln
   - Bugs fixen

3. **Zukünftige Features:**
   - Erweiterte Konfigurationsoptionen
   - Zusätzliche Sensor-Typen
   - Diagnostics-Integration
   - Services für Steuerung (falls unterstützt)

## ✅ Fertig!

Sobald alle Punkte abgehakt sind, ist deine Integration bereit für HACS! 🎉

Bei Fragen oder Problemen:
- Prüfe die Logs: Einstellungen → System → Logs
- Suche in den [Home Assistant Docs](https://developers.home-assistant.io/)
- Frage in der [HACS Discord](https://discord.gg/apgchf8)
