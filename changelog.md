# Changelog

<details open>
<summary><strong>1.3.0 - 2026-10-xx</strong></summary>

### Added
* New split news page. One column version specific, one for general information, and one for changelog
* New update method via Github allowing community submissions
* Safe-guard added for Flow Power users if EM tag detection file not present
* All entities now YAML based (removal of UI entities via migration script)
* Update script now manages HACS component addition/removal/forced version.
#### Changed
* EV update - changed decisions to be made once per minute when EV is being charged. This gives a more granular reading for the solar_only and solar_preferred policies.
* Sigenergy - EMS mode now on for self-consumption to fix issue found in firmware 116 & 117
* Energy Plan - now supports EV charging forecast and past events (events card v3.5.1)
#### Fixed
* Energy_manager_overview.yaml 24hr chart not showing, fixed
* House load not calculated correctly in "Other\DIY" provider Node-RED
* Bug where if export price (for Other\DIY) is for a 24hr period that it would fail to detect the period
* Removal of "# Goodwe not supported" in em_scripts.yaml (current_reserved_soc_backup), was producing entry in system log

</details>

<details>
<summary><strong>1.2.0 - 2026-09-14</strong></summary>

#### Added
* Custom Electricity Plans
* GoodWe_int - use purely the GoodWe integration to control the GoodWe
* Filter to reduce influxdb database size growth
* EV Charging - support to charge to percentage of car battery SoC (integration dependent) along with existing kWh
* GloBird - ability to add a kWh limit to the free import period
* Flow Power - ability to add a kWh limit to the peak export period
* Additional PV dashboard entities for consumed energy
#### Changed
* Additional recorder globs and entity exclusions
* EV Charging - new battery_only policy, to only charge from stored energy
* EV Charging - updated solar_preferred to include battery use if not enough solar and grid price too high (during scheduled period), if battery discharge allowed
* Updated em-events-card.js to v3.1.3
* New look Grafana using v13 updates
* Removed true as default for curtailment enabled (now no default)
* Add delay in Node-RED verification of settings for slow inverters (35s -> 60s)
#### Fixed
* EV Charging - fixed scripts for import/export/load_power for upstream EV circuit to show correct import and export values
* Logging - fixed ocpp charger logging if ocpp integration not installed

</details>

<details>
<summary><strong>1.1.0 - 2026-06-19</strong></summary>

#### Added
* Node-RED verifications
* Energy profiles
* Scheduled charging
* Dynamic charging
* Dynamic export reserve based on power profile
* Force charge/discharge to max safety
* Local automation to stop export at battery reserve
* Consumed Energy
#### Changed
* Updated events card
* Moved charge & discharge safety inputs to settings page
* Moved dynamic charging, charge and discharge percentage limits to the Settings tab of the PV Dashboard
* Updated GoodWe script for ARM 04 / DSP 05 firmware support
* Added V2G status to Sigenergy script
#### Fixed
* Wholesale price forecast y-axis max fix
* Removed high-sell and sell-buy mode buttons from PV dashboard
* Fixed billing cycle reset

</details>

<details>
<summary><strong>1.0.0 - 2026-05-11</strong></summary>

#### Added
* Globird 'Zerohero' support
* Tooltips for PV Dashboard
* Support for multiple modbus files
* Add force_charge_limit_to_max_safety, force_discharge_to_max_safety & force_discharge_hardlimit_inverter_rating automations (clamping)
* Added tooltips for wholesale pricing settings for sell strategies
* Added PV Dashboard misconfigured BOM and Solcast warnings
* Charge and Discharge limiters
* Electricity Provider daily charge
* Billing day support
* Consumed energy sensors (hourly, daily, monthly,yearly)
* Added Events Card (@JustinBH) for Energy Manager decision display
* Added Dynamic Charging option for potential decresed wear & tear
* Boolean entity for curtailing active, to be used in user automations
#### Changed
* Changed modbus to read merged directory /config/modbus for multiple modbus support
* Updated configuration.yaml to support future InfluxDB requirements
* Updated update system to require valid apiKey for updates
* Removed validate_safety_limits automation
* Updated PV generation modbus address for AlphaESS due to changed firmware
#### Fixed
* Energy Manager Plan next 24hrs - buy and sell pricing decimals places
* Flow Power AEMO region minimum characters (changed 4 to 3)
* Sigenergy grid power in em_scripts.yaml
* Sungrow grid power in sungrow_modbus.disabled
* Fixed GoodWe export limit enable toggle
* Fixed invalid login notification on update
* Sigenergy modbus updates @JustinBH

</details>

<details>
<summary><strong>0.3.3 - 2026-01-15</strong></summary>

### Added
* Flow Power support
  - New entities
  - New Node-RED tab and flows
  - New API
* Added support for additional PV sensors
* Added support for auxilary load_power exemptions
  - flows.json update
  - optional /share/power_load_excluded_sensors.txt exclusion file (one sensor per line, Watt only)
* Better support for GoodWe EH/ET with schedule slots
* Added support for GoodWe ESA
* Firmware version for Sungrow, Sigenergy, AlphaESS, GoodWe
* Serial number for AlphaESS
* Added battery temperature sensor to PV dashboard for all except Fronius (not supported) 
* Added new sensor for defining curtailment. Instead of curtailing at zero cents, it is user customisable. No 50% curtailment any longer.
* Added ability to set PV Power to zero on negative buy prices for Sigenergy.
### Changed
* Energy Overview dashboard
* Energy PV dashboard
* em_automations.yaml
* em_helpers.yaml
* em_scripts.yaml
* em_templates.yaml
* sungrow_modbus.yaml.disabled (addition of firmware sensor)
* sigenergy_modbus.yaml.disabled (addition of firmware sensor)
* alphaess_modbus.yaml.disabled (addition of firmware and serial sensors)
* Changed method of calculating 5 min import and export kWh for more accurate costings
* Changed method of energy kWh and $ collection for 5 min, hourly, daily, monthly
  - Including registry fix tool in case _2 entities created
* Changed mqtt_sensors.yaml for firmware version sensor addition
* AlphaESS - PV power now selected from either of two support PV power modbus sensors
### Fixed
* No bug fixes

</details>

<details>
<summary><strong>0.3.2 - 2025-01-10</strong></summary>

### Added
* Added SolarEdge support
* Added Fronius support
* Added GoodWe ET support (0.3.1 only supports EH)
* Added new "Next 24hr Energy Plan" to Energy Overview dashboard for premium subscribers.
* Added Battery Calculation Engine template (@JustinBH)
* Added battery_completion_time to energy_manager_pv dashboard (@JustinBH)
* On forced charge, battery charge power is now set to maximum
* EM API now accessed by version number
### Changed
* Increased inverter_max_charge_power and inverter_max_discharge_power from 25600 to 32600 max
* Updated Battery Hours Remaining template (@JustinBH)
* Updated battery_completion_time template (@JustinBH)
* Updated battery_hours_remaining in energy_manager_pv dashboard (@JustinBH)
* Updated Sigenergy modbus - added sigenergy_remote_ems_enable, sigenergy_pv_max_power_limit, sigenergy_import_power_limit
* High_sell_price increased from 500 to 1500c
* Changed method of displaying decisions if EM API never queried. Instead of "error" message, explanation is now shown.
* Removed deprecated sensor.battery_hour_full
### Fixed
* Weather.weather_home changed to weather.home in energy_manager_overview.yaml for Amber users (was working for LocalVolts users already)

</details>

<details>
<summary><strong>0.3.1 - 2025-12-05</strong></summary>

### Added
- Goodwe support
- Sell-Buy Mode (sell-buy price difference)
- Estimated battery runtime on dashboard (credit to JustinBH)
- Energy Control Timer
### Changed
* Display precision for various mqtt sensors
* Changed Energy Score weightings to be 0-100, not 0-1, for ease of use.  Normalisation still occurs at the EM servers to show a total score of 1.
* Updated all binary sensors (charging/discharging/importing/exporting) to be either on or off
* Added third-party PV generation for Sigenergy - scripts and modbus
* Node-red new deprecation warning for state changes updated to non-deprecated method
* Moved inverter brand selector to settings page of PV Dashboard
* Curtailment Wattage changed from 100W to 0W
### Fixed
* Inverter_battery_charge_mqtt class changed to measurement
* Various sigenergy modbus sensors updated (@JBH)

</details>

<details>
<summary><strong>0.3.0 - 2025-10-03</strong></summary>

### Added
* Flows, configuration, energy manager pv - Added granular demand period
* User based automations, templates, scenes and scripts yaml files, prefixed with user_ - for UI additions outside of EM
* New features:
  - Grafana Addon
  - Influxdb Addon
  - influxdb in Node-RED
  - Energy Scores - Availability and Profit
* New energy monitor dashboard, desktop and mobile
* New Energy Availability and Energy Profitibility scores support. Requires v0.2.5 of API to receive score data.
* New energy availability dashboard, desktop and mobile
* New energy profitability dashboard, desktop and mobile
* New PV Dashboard tab for score weightings
* New NR Solcast flow to retrieve saved Solcast forecast on HA reboot/start
### Changed
* configuration.yaml - changed for demand periods
* energy_manager_pv.yaml - change for demand periods
* Completely new file structure for EM yaml files
  - Moved automations, scripts, templates, groups and helpers into package located in integrations
  - Cleared out EM settings from configuration'
  - Users can now add their own UI based automations and scripts
### Fixed
* User created Node-RED tabs are now retained on update.
* Updated mqtt_sensors.yaml to fix deprecation warning of object_id

</details>

<details>
<summary><strong>0.2.5 - 2025-09-21</strong></summary>

### Added
* Amber forecast increased to 24hrs, Node-RED flows updated
* If EM enters disabled mode, it will now limit exports to 100W as part of the procedure
* Node-RED will now write a curtailing event twice as inverters may timeout on writes if being read at the same time
### Changed
* sigenergy_modbus.yaml.disabled - updated export power limit
* Updated perform_energy_manager_update.py update script
### Fixed
* Flows - Solcast 4am fixed (was 6am poll)
* Flows - Amber pricing was not pulling final, but estimate
* Energy Flow Visual - kW changed to W
* configuration.yaml - removed energy export limit step as it is incorrect for percentage based inverters
* Fixed Amber feedIn pricing - was spot, now perkWh
* sigenergy_modbus.yaml.disabled - 40032 changed to 40034 for battery discharging limit

</details>

<details>
<summary><strong>0.2.4 - 2025-09-05</strong></summary>

### Added
* Added new Energy Flow visual on Energy Manager PV Dashboard (with disable option)
* Added /config/www/energy-flow-card.js (energy manager flow addition)
* Added /config/www/energ-flow.svg (energy manager flow addition)
* Added /config/www/energ-flow-dark.svg (energy manager flow addition)
* Added forced reinstall button for updates to install same version again
* Added 5min perf_data to csv in /addon_configs/a0d7b954_nodered/node-red/perf_data in following format:
  - date time,generation,load,charge,discharge,import,export
### Changed
* Updated energy_manager_pv.yaml for energy flow visual addition
* Updated energy_manager_pv.yaml for reinstallation option
* Updated configuration.yaml for reinstallation option
* Updated configuration.yaml for entity slider to box conversion
* Updated scripts.yaml for reinstallation option
* Moved location of energy manager decisions to left of energy_manager_pv.yaml first tab to make room for Energy Flow visual
* Updated perform_energy_manager_update.py to support resource additions
* Updated perform_energy_manager_update.py to support forced reinstall
* Updated update_checker.py to support forced reinstall
* Changed the following entities from sliders to boxes for ease of updating on mobile devices
  - battery_1 -> 6
  - high_sell_battery_reserve
  - battery_morning_prep
  - battery_morning_limit
  - battery_evening_prep
  - grid_buy_price_night_spike_prep
  - grid_buy_price_day_spike_prep
  - grid_buy_price_day
  - grid_sell_price_night
  - grid_sell_price_day
* Node-RED flows updated to include perf_data csv saving
* Updated upper limits of the export, charge and discharge related entities for users with larger allowances
### Fixed
* Corrected curtailing issue with AlphaESS - added 0x700 register to curtailing script
* Corrected Node-RED curtailment error for battery_w for free users

</details>

<details>
<summary><strong>0.2.3 - 2025-08-30</strong></summary>

### Added
* input_boolean.emergency_override sensor to completely disable energy manager if required
* input_number.battery_use_cost sensor to value cost to discharge battery
### Changed
* configuration.yaml - addition of input_boolean.emergency_override and input_number.battery_use_cost
* Configuration image titles - wwww/energy-manager-settings.svg
* energy_manager_pv dashboard - addition of the emergency override toggle and battery_use_cost definition
* Node-RED flows - addition of the emergy override toggle and battery-use-cost submission
### Fixed
* Node-RED API server decision logic
* scripts.yaml - sensor.alphaess_pv_power updated to sensor.alphaess_total_active_pv_power

</details>

<details>
<summary><strong>0.2.2 - 2025-08-26</strong></summary>

### Added
* Additional of sending import/export kWh and appropriate pricing and entities to API (Node-Red updated)
### Changed
* energy_manager_pv dashboard - Made SVG image more responsive for mobile devices
### Fixed
* energy_manager_pv dashboard - removed user reference
* scripts.yaml - for AlphaESS
* alphaess_modbus.yaml.disabled - removed scaling for reserve UPS and charge cut-off SOC, min_soc/max_soc refresh reduced from 60 to 10

</details>

<details>
<summary><strong>0.2.1 - 2025-08-20</strong></summary>

### Added
* input_number.battery_charge_power_hardlimit
* input_number.battery_discharge_power_hardlimit
* input_boolean.notification_price
* input_boolean.notification_warning
* Added local notifications for Electricity Provider API up and down
* Added price spike and warning notifications
### Changed
* Addition of battery_charge and discharge power hardlimit entities to dashboard
* Addition of user enabled notifications to dashboard: price spike boolean & warning boolean
* Addition of "Get Charge limit" and "Get Discharge limit" in flow
* Updated emVersionOK function to give warning one version away from restriction
### Fixed
* Changed "preserve battery" "no limit on battery discharge" to use input_number.battery_discharge_power_hardlimit
* Min & Max SOC settings for AlphaESS

</details>

<details>
<summary><strong>0.2.0 - 2025-08-17</strong></summary>

### Added
* Support for separate URLs for free and premium APIs
* Added requirement for EM to only be within a specified number of updates behind
* Added sensor.em_api_server sensor
* Added node-red EM version label
### Changed
* AlphaESS PV solar sensor to correct power load calculations
* AlphaESS power_load calculation
* When sell price is -3c or lower and the inverter shuts down, instead of self-consumption, the inverter will charge the battery at full import Wattage.
* PV Dashboard sliders changed to boxes for easier use on mobile devices
* Home Assistant will now force poll every 5 mins. Previously if battery level and FIT did not change, it did not report in. Now it will. This was causing false-positive email alerts for systems not contacting the API.
### Fixed
* AlphaESS min_soc / max_soc modification scaling removed

</details>
