#  Adding Your Own Home Assistant Configuration

Energy Manager uses Home Assistant's packages feature to keep its configuration organised.

You can add your own Home Assistant configuration without modifying Energy Manager files.

## Creating a personal package

Create a new YAML file in /config/integrations/.

For example:

/config/integrations/user_custom.yaml

You can put your own supported Home Assistant configuration in that file:

```bash
template:
  - sensor:
      - name: "My Custom Sensor"
        unique_id: my_custom_sensor
        state: "{{ states('sensor.some_existing_sensor') }}"

group:
  my_devices:
    name: "My Devices"
    entities:
      - light.lounge
      - switch.garage
```

Replace the example entities with your own.

## Rules

- Use filenames beginning with user_ for personal packages.
- Do not edit Energy Manager's em_*.yaml files.
- Do not reuse Energy Manager entity IDs or unique IDs.
- Continue creating UI automations and scripts normally through Home Assistant.
- Use configuration.yaml for top-level configuration that cannot be included in a package.
- Always run Home Assistant's configuration check after changing YAML.

## Updates

Energy Manager updates only the files and tagged sections identified in its update manifest.

Your personal package files are not part of that manifest, so normal updates and force reinstalls leave them unchanged.

Avoid modifying settings inside Energy Manager's managed sections because those sections may be replaced during updates.
