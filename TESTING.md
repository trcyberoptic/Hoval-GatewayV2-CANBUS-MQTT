# HACS Integration Testing Guide

Der `hacs-integration-beta` Branch enthält die neue Home Assistant Integration zum Testen.

## 🧪 Schnelltest: Beta-Branch in HACS installieren

### Methode 1: Direkt über HACS (Empfohlen)

1. **HACS öffnen** in Home Assistant
2. **Custom Repository hinzufügen:**
   - HACS → Integrations → ⋮ (drei Punkte) → Custom repositories
   - Repository: `https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT`
   - Kategorie: `Integration`
   - Klicke "Add"

3. **Beta-Version installieren:**
   - Suche "Hoval Gateway V2"
   - Klicke auf die Integration
   - Klicke "Download"
   - **Wichtig:** Wähle im Dropdown "hacs-integration-beta" (nicht "main")
   - Klicke "Download"

4. **Home Assistant neustarten**

5. **Integration hinzufügen:**
   - Einstellungen → Geräte & Dienste
   - "+ Integration hinzufügen"
   - Suche "Hoval Gateway V2"
   - Konfiguriere mit deinen Daten

### Methode 2: Manuell installieren

```bash
# Auf deinem Home Assistant Server/Container
cd /config
mkdir -p custom_components

# Beta-Branch klonen
git clone -b hacs-integration-beta https://github.com/trcyberoptic/Hoval-GatewayV2-CANBUS-MQTT.git /tmp/hoval
cp -r /tmp/hoval/custom_components/hoval_gateway custom_components/

# Home Assistant neustarten
```

## ✅ Was testen?

### 1. Installation
- [ ] Custom Repository lässt sich hinzufügen
- [ ] Integration erscheint in HACS
- [ ] Beta-Branch ist auswählbar
- [ ] Download funktioniert
- [ ] Home Assistant startet nach Installation neu

### 2. Konfiguration
- [ ] Integration erscheint unter "Integration hinzufügen"
- [ ] Config Flow öffnet sich
- [ ] Formular zeigt alle Felder:
  - IP-Adresse
  - Port (Standard: 3113)
  - Unit-ID (Standard: 513)
  - Ignore Keywords (Standard: CO2,VOC,voc,Luftqualität)
- [ ] Verbindungstest funktioniert bei korrekter IP
- [ ] Fehler wird angezeigt bei falscher IP

### 3. Sensoren
- [ ] Gerät "Hoval HomeVent" erscheint unter Geräte & Dienste
- [ ] Sensoren werden erstellt (kann 1-2 Minuten dauern)
- [ ] Sensorwerte werden aktualisiert
- [ ] Temperatur-Sensoren haben korrekte device_class (temperature)
- [ ] Feuchtigkeits-Sensoren haben korrekte device_class (humidity)
- [ ] Einheiten werden korrekt angezeigt (°C, %)

### 4. Logs
- [ ] Keine Fehler in den Logs (Einstellungen → System → Logs)
- [ ] Verbindungsmeldungen erscheinen:
  ```
  Connecting to <ip>:3113
  Connected to Hoval device
  Loaded X datapoints (Unit 513)
  ```

### 5. Updates
- [ ] HACS zeigt Updates an (wenn neuer Commit gepusht wird)
- [ ] Update funktioniert ohne Fehler
- [ ] Konfiguration bleibt erhalten nach Update

## 🐛 Probleme melden

Falls du Probleme findest, bitte melde sie mit:

1. **Home Assistant Version:**
   ```
   Einstellungen → System → Über → Version
   ```

2. **Logs:**
   ```
   Einstellungen → System → Logs
   Suche nach "hoval_gateway"
   ```

3. **Screenshots:**
   - Config Flow
   - Fehler-Meldungen
   - Sensor-Ansicht

4. **Schritte zum Reproduzieren**

Erstelle ein Issue auf GitHub mit diesen Informationen.

## 📊 Erwartete Sensoren

Nach erfolgreicher Installation sollten folgende Sensoren erscheinen (Beispiele):

```
sensor.hoval_temperatur_aussenluft       - Außenluft Temperatur (°C)
sensor.hoval_temperatur_abluft           - Abluft Temperatur (°C)
sensor.hoval_temperatur_fortluft         - Fortluft Temperatur (°C)
sensor.hoval_temperatur_zuluft           - Zuluft Temperatur (°C)
sensor.hoval_feuchtigkeit_abluft         - Abluft Feuchtigkeit (%)
sensor.hoval_lueftungsmodulation         - Lüftung Modulation (%)
sensor.hoval_feuchte_sollwert            - Feuchte Sollwert (%)
...
```

Anzahl der Sensoren hängt von deiner CSV-Konfiguration ab (typisch: 40-70 Sensoren).

## 🔄 Von Beta zu Main wechseln

Sobald die Beta-Tests erfolgreich sind:

1. **Merge in Main:**
   ```bash
   git checkout main
   git merge hacs-integration-beta
   git push
   ```

2. **In HACS zu Main wechseln:**
   - HACS → Hoval Gateway V2
   - Redownload
   - Wähle "main" Branch
   - Home Assistant neustarten

## 🚀 Nach erfolgreichem Test

1. **Pull Request erstellen** (optional für Review)
2. **In main mergen**
3. **Release erstellen** (v3.0.0)
4. **Community informieren**

## 💡 Vergleich: Beta vs. Alte Installation

| Feature | Beta (HACS) | Alt (systemd) |
|---------|-------------|---------------|
| Installation | HACS UI | apt install .deb |
| Config | HA UI | config.ini |
| Sensoren | Native HA | MQTT |
| Updates | HACS | apt upgrade |
| Logs | HA Logs | /var/log/hoval-gateway/ |
| MQTT nötig | ❌ Nein | ✅ Ja |

## ❓ Häufige Fragen

### Kann ich beide parallel laufen lassen?

Ja, aber nicht empfohlen. Du würdest dann:
- 2x die Daten vom Hoval-Gerät abrufen
- Doppelte Sensoren haben (MQTT + Native)

Besser: Stoppe den alten Service während des Tests:
```bash
sudo systemctl stop hoval-gateway
```

### Funktioniert die alte MQTT-Integration noch?

Ja! Der Beta-Branch ändert nichts am alten `hoval.py` oder am systemd-Service. Du kannst zwischen beiden Methoden wechseln.

### Werden meine Automationen kaputt gehen?

Wenn du von MQTT-Sensoren auf Native HA-Sensoren wechselst, ändern sich die Entity-IDs:

**Alt (MQTT):**
```yaml
sensor.mqtt_aussenluft_temp
```

**Neu (Native):**
```yaml
sensor.hoval_temperatur_aussenluft
```

Du musst deine Automationen anpassen. Tipp: Teste zuerst mit einem Dashboard, nicht mit kritischen Automationen!

## 📝 Test-Checkliste zum Abhaken

Kopiere diese Checkliste in ein Issue oder deine Notizen:

```markdown
## Installation
- [ ] HACS Custom Repository hinzugefügt
- [ ] Beta-Branch ausgewählt
- [ ] Download erfolgreich
- [ ] HA Neustart erfolgreich

## Konfiguration
- [ ] Integration erscheint in "Integration hinzufügen"
- [ ] Config Flow öffnet sich
- [ ] Verbindungstest erfolgreich
- [ ] Integration wurde hinzugefügt

## Funktionalität
- [ ] Gerät "Hoval HomeVent" sichtbar
- [ ] Sensoren werden erstellt (>10 Sensoren)
- [ ] Sensorwerte werden aktualisiert
- [ ] device_class korrekt (temperature, humidity)
- [ ] Keine Fehler in Logs

## Stabilität
- [ ] Läuft über 1 Stunde ohne Fehler
- [ ] Reconnect nach Hoval-Neustart funktioniert
- [ ] HA-Neustart erhält Konfiguration
- [ ] Sensoren bleiben verfügbar nach HA-Neustart

## Bonus (Optional)
- [ ] Update-Test (neuer Commit → HACS Update)
- [ ] Mehrere Hoval-Geräte gleichzeitig
- [ ] Integration in Dashboard eingebaut
- [ ] Automationen erstellt und getestet
```

## 🎉 Feedback willkommen!

Dein Feedback hilft, die Integration zu verbessern. Danke fürs Testen! 🙏
