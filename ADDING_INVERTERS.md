# Adding New Inverter Support to Energy Manager

Energy Manager welcomes community contributions that extend support to additional inverter brands and models. This guide explains how to connect a supported Home Assistant inverter integration to Energy Manager's **existing** configuration and control interface.

**Every pull request must target the `development` branch.** The release sequence is `development` → `test` → `early` → `main`.

## Non-negotiable contribution rules

1. **Do not create new Energy Manager scripts or automations.** Modify only the appropriate branches of existing scripts and automations. Do not introduce parallel schedulers, control loops, or alternative execution paths.
2. **Do not create new manufacturer-specific Energy Manager sensors, MQTT topics, or template entities if the integration already provides the information.** Map the integration's existing entities into Energy Manager's existing standardised measurements. Propose a new entity only as an explicitly justified exception for maintainer approval; do not include it in a normal inverter PR.
3. **Keep existing entity IDs, helpers, MQTT topic names, command options and common scripts unchanged.** Extend their existing manufacturer branches. Do not break other inverter brands.
4. Prefer an actively maintained Home Assistant integration over direct Modbus register writes. If the only workable approach requires custom Modbus support, discuss it with the maintainer *before* implementation.
5. Do not modify the private decision-making backend. If its behaviour must change, describe the requirement in code comments and the PR description.
6. Do not add a separate control architecture or independently managed device schedules. Energy Manager must remain the authority for forced battery operation.

## 1. Understand the common interface

Energy Manager makes charge, discharge and stop decisions without requiring separate backend logic for each inverter brand. Existing Home Assistant scripts translate those commands into integration-specific service calls; existing MQTT publishing converts the vendor's sensors into common Energy Manager measurements.

| File | What to change |
| --- | --- |
| `config/integrations/em_helpers.yaml` | Add the new option to `input_select.inverter_brand`; reuse all other helpers |
| `config/integrations/em_scripts.yaml` | Add branches to existing activation, charge/discharge, power, protection and MQTT publishing scripts |
| `config/integrations/em_automations.yaml` | Extend existing startup synchronisation and brand-specific conditions, without adding automations |
| `config/integrations/em_templates.yaml` | Extend existing mode/status/state templates, without adding brand-specific template sensors |
| Existing deployment manifest/configuration | Declare any required integration dependency through the established provisioning process |

The `goodwe_int` selection is a useful integration-based example. **Do not copy it without checking its limitations and the actual entities exposed by your integration.** `goodwe` and `goodwe_et` are separate, Modbus-based implementations.

## 2. Verify the integration and hardware first

Install and configure the proposed integration against a real inverter. Document manufacturer, exact model, inverter firmware, integration name/repository and integration version. Verify that it exposes:

- PV generation, battery SOC, battery power, grid power, device availability and battery capacity (capacity may be configured through the existing helper).
- Reliable force-charge, force-discharge and stop/normal-operation commands.
- Adjustable charge and discharge power, either in watts or units that can be safely converted.
- A means to honour upper charging and lower discharging SOC targets, either as part of the command or through persistent inverter settings.

Also list optional capabilities such as export limiting, PV curtailment and backup reserve. If a critical capability is missing, raise a GitHub Discussion before producing a PR. A monitoring-only integration is insufficient.

### SOC control is **manufacturer-specific**

Energy Manager's **intent** is consistent, but the method varies:

- **GoodWe (`goodwe_int`)**: when beginning forced charging, the command sequence must specify the **maximum charging SOC target**; when beginning forced discharging, it must specify the **minimum discharging SOC target**. GoodWe's ECO SOC setting is a target used by the active operation, not two independent persistent minimum/maximum registers.
- **Sungrow**: the existing implementation has separate minimum and maximum SOC controls; do not insert GoodWe's per-command target-setting pattern into its commands.
- **Other brands**: map the existing controls to the manufacturer's actual semantics. A brand might have separate persistent limits, a shared target that changes with the operation, or a combined mode and target command.

The rule is **achieve the required outcome with the existing Energy Manager interface**, not force every brand to use identical device-side commands. Never assume an SOC value merely because the last Home Assistant helper was set. Confirm whether the inverter enforces it. If enforcement is not supported or a command cannot be read back, document that limitation and how it is handled.

## 3. Add the inverter selection to `em_helpers.yaml`

Find `input_select.inverter_brand` and append a unique lowercase identifier (for example, `newbrand_int`). Preserve all current options. Use a distinct identifier if the same manufacturer has a separate Modbus implementation.

```yaml
  inverter_brand:
    name: Inverter Brand
    icon: mdi:form-select
    options:
      # Keep every existing option here, unchanged
      - newbrand_int
```
**When using an integration for inverter control, name the brand with _int as its suffix (e.g., newbrand_int). If it uses modbus, name the brand without any suffix (e.g., newbrand).**

The snippet illustrates the new item **only**; do not replace the existing list with it. Do not create extra control helpers unless approved by the maintainer.

## 4. Extend the existing scripts in `em_scripts.yaml`

### 4.1 `switch_inverter_brand`

Add a brand-specific `choose` branch. Integration-based activation normally requires no Modbus configuration switch. Use existing notifications or configuration checks rather than adding another script. Do not add unnecessary restarts.

### 4.2 `set_inverter_charge_discharge_mode`

Add a new exact-match brand branch and handle the three existing commands:

| Existing command | Required outcome |
| --- | --- |
| `Stop` | Cancel forced charge/discharge and return to normal self-consumption, **not** shut down the inverter |
| `Forced Charge` | Force battery charging at the requested permissible power and upper SOC target |
| `Forced Discharge` | Force battery discharging at the requested permissible power and lower SOC target |

The exact order of `select.select_option`, `number.set_value` and other integration services is manufacturer-dependent. Use integration-defined option values, not assumed GoodWe labels. Protect against unavailable control entities; do not change operating mode if the target and limits cannot be applied safely.

**GoodWe example (illustration of existing logic, not a universal recipe):**

```yaml
# Charging: target SOC must be applied as part of the charge sequence.
- action: number.set_value
  target:
    entity_id: number.goodwe_eco_mode_soc
  data:
    value: "{{ states('input_number.inverter_max_soc') | int }}"
# Then set the integration's charging mode and permissible power.
```

For discharge, the corresponding target comes from `input_number.inverter_min_soc`. For Sungrow or brands with separate persistent SOC controls, keep their existing model rather than copying this GoodWe sequence.

### 4.3 `set_inverter_charge_discharge_power`

Add an **exact-match** branch for the new identifier. `input_number.inverter_charge_discharge_power` is the existing requested value; translate it into the integration's required units. Distinguish charge and discharge hardware limits where necessary. Clamp to the permissible range and handle missing/zero limits safely.

If an integration accepts **watts**, do not convert watts to a percentage. If it accepts a percentage, derive the percentage from the correct limit and validate the denominator. When changing a power setpoint during an active forced operation, avoid interrupting the operating mode unnecessarily.

### 4.4 Review the remaining **existing** scripts

Review and add a branch only where necessary to:

- `set_inverter_ems_mode`
- `set_inverter_min_soc` and `set_inverter_max_soc`
- `set_inverter_reserved_soc_backup`
- `set_inverter_max_charge_power` and `set_inverter_max_discharge_power`
- `set_inverter_pv_power_limit`
- `set_inverter_export_power_limit` and `set_inverter_export_power_limit_enabled`
- `inverter_stop_export`

A GoodWe-style shared operational SOC target may belong inside `set_inverter_charge_discharge_mode`, rather than having separate device-side minimum and maximum controls. Explain the mapping and unsupported functions. Do not add empty success-looking branches for capabilities that do not exist.

### 4.5 `publish_inverter_data`

Include the new identifier in its allowed-brand condition. Add branches **inside the existing MQTT publishing logic** to read integration-provided entities and publish through existing `homeassistant/sensor/inverter/.../state` topics. Keep the standard topic names and definitions.

Review solar power, grid power, battery power, calculated load, import/export, SOC, capacity, energy counters, model and status, actual configured limits and any available power limits. Only map values the integration genuinely provides. Do not create alternative manufacturer sensors or topics.

Be careful about signs and units: vendors disagree on whether positive grid power means import or export, and whether positive battery power means charge or discharge. Test both directions. A critical unavailable measurement is **not** confirmed zero; do not silently convert missing grid readings into apparent zero imports. If a shared MQTT publisher currently lacks a safe unavailable-data path, document that rather than fabricate measurements.

Use exact brand conditions where possible:

```jinja2
{% elif brand == 'newbrand_int' %}
  {{ states('sensor.integration_provided_pv_power') | float(0) }}
```

This snippet illustrates placement, not a recommended missing-data fallback.

## 5. Extend existing `em_automations.yaml` automations

**Do not add new automations.** The existing `publish_inverter_data_to_mqtt` automation already executes the shared publisher every 10 seconds. Extend the publishing script, not its schedule.

In `sync_inverter_controls_on_startup`, add the brand to the supported selection and an appropriate branch. Synchronise only trustworthy **actual** integration state and settings into the existing helpers; do not substitute guessed values or read a GoodWe shared SOC target as if it were both independently configured limits. Make sure a startup action does not accidentally resume a stale forced-charge or forced-discharge request.

Where the supported mode is self-consumption, use the existing `Stop` semantics and existing control script; avoid inventing a new reset script. Account for integration initialisation delays and verify entities are ready before attempting changes. Do not reset user settings to zero merely because the integration has not initialised.

Review the existing helper-change automations and battery cutoff/offline handling. Existing automations should continue calling the shared scripts with no brand-specific duplicate triggers.

## 6. Extend existing templates in `em_templates.yaml`

Update **existing** manufacturer-specific branches, where applicable, including:

- `inverter_ems_mode_text`
- `inverter_running_state`
- `inverter_forced_charge_command`
- `inverter_charge_discharge_mode_select`
- Other existing actual-state, control or inverter-availability templates

Map the integration's reported actual state to the **existing** Energy Manager mode meanings. Do not simply echo the last command requested. Do not add separate manufacturer-specific template sensors; reuse the integration's own entities and the existing Energy Manager templates. Preserve existing entity IDs and template `unique_id` values.

## 7. Dependencies, deployment and dashboards

For an integration distributed through HACS or Marketplace, list its upstream repository and compatible version in the PR and update the **existing** deployment dependency mechanism as required. Do not bypass Home Assistant configuration validation to work around missing dependencies. New deployments should receive required components through the established provisioning process.

Review existing dashboards for brand-specific visibility conditions. Extend the relevant conditions rather than creating duplicate manufacturer dashboards or renaming standard sensors.

## 8. Required testing

Test on real hardware and report the model, firmware and integration version. A PR is not fully validated merely because the YAML loads or a Home Assistant service call returns successfully.

- [ ] Home Assistant configuration validation passes.
- [ ] Existing Energy Manager entities and MQTT topics retain their names.
- [ ] Integration connects and critical telemetry is available.
- [ ] Grid import/export and battery charge/discharge signs and units are correct.
- [ ] `Forced Charge` starts and obeys its power and maximum SOC target.
- [ ] `Forced Discharge` starts and obeys its power and minimum SOC target.
- [ ] Power-limit changes during an active operation take effect safely.
- [ ] `Stop` returns to normal/self-consumption operation.
- [ ] Missing integration entities are handled without unsafe commands or fictitious zero imports.
- [ ] Restart and brand selection synchronisation do not initiate unwanted forced operation.
- [ ] Battery minimum-SOC protection and inverter-offline behaviour have been checked.
- [ ] Where claimed, export limiting, PV curtailment and backup reserve work.
- [ ] No new scripts, automations or unnecessary manufacturer sensors were introduced.
- [ ] Existing inverter implementations remain unaffected.

Test cautiously with a means to return the inverter to normal operation independently of Energy Manager.

## 9. Submit the pull request

1. Fork [ha-energymanager/ha-energymanager](https://github.com/ha-energymanager/ha-energymanager).
2. Synchronise your fork's `development` branch with the upstream `development` branch.
3. Create a feature branch from `development` and make only the relevant modifications.
4. Commit and push the branch to your fork.
5. Open a PR against **`ha-energymanager/ha-energymanager` → `development`**. Other target branches will not be accepted.

Example commands after your local `development` is up to date:

```bash
git switch development
git switch -c add-newbrand-support
# Edit and test the existing files.
git add -A
git commit -m "Add NewBrand inverter support"
git push -u origin add-newbrand-support
```

In your PR, provide the manufacturer/model/firmware, integration link/version, new brand identifier, summary of **each existing file changed**, operating-mode and SOC mapping, control entity mapping, actual hardware test results, unavailable features, dependencies and any required backend change. Redact credentials and personal information from logs.

If a private backend change is needed, explain its inputs, outputs, expected behaviour and safety requirements in relevant YAML comments and the PR description. Backend changes are reviewed separately and are not guaranteed by acceptance of a public PR.

## 10. Review and release

Submissions are reviewed for architectural fit, safety, maintainability, completeness of tests and compatibility with existing inverters. The maintainer may request revisions, defer or decline support where the integration is incomplete or insufficiently tested. Merging into `development` does not mean a public release; changes progress through `test`, `early` and `main` after appropriate validation.

**One common interface; existing scripts and automations; integration-native entities; brand-specific commands only where required.**
