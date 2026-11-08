# Energy Manager Installation Guide

Energy Manager v2.0.0 is installed on a **fresh, dedicated Home Assistant OS** installation. It is not intended to be added to an existing, customised Home Assistant system.

This guide assumes Home Assistant OS has already been installed and its initial setup completed.

> **Requirement:** Home Assistant Core **2026.11 or newer**. Update Home Assistant before starting if necessary.

## 0. Preparation (Optional but recommended)

During the installation you will be asked for two different API keys so that your Home Assistant can be configured appropriately. These can be added later by yourself manually if you would prefer, but it is highly recommended that you obtain these keys prior to commencing the installation script.

1. **Energy Manager API key**. This is required to access the Energy Manager servers to obtain optimisation decisions. Home Assistant will run fine without this key, but opimisations and automations will not work without it. You can obtain the key from the **Subscriptions** page within your https://energymanager.com.au account. 
2. **Solcast API key** and **Resource IDs**. These are required for accurate optimisation and decisions to be made by the Energy Manager server. Unless the system knows how much solar is forecast for your unique system, its decisions cannot be accurate. They are also required for various Energy Manager dashboards. The Solcast API key and at least one Resource ID are **mandatory** for Energy Manager to function correctly. Follow the instructions at https://energymanager.com.au/usersc/install-solcast.php to obtain your Key and Resource IDs.

## 1. Install Advanced SSH & Web Terminal

1. In Home Assistant, open **Settings → Apps**.
2. Click on **Install app**, find **Advanced SSH & Web Terminal** and install it. Use the Advanced SSH app, not the basic Terminal & SSH app.
3. Open the app's **Configuration** tab. Click on the upper-right **three dot menu** and select **Edit in YAML**.
4. Configure a password under `ssh` (and leave other settings at their defaults). Save the configuration.
5. Start the app, and enable **Start on boot**.
6. Select **Open Web UI** to launch the terminal.

> Keep the SSH password secure. Energy Manager configures its own SSH key during installation, without removing the credentials you have set.

## 2. Start the Energy Manager installer

In **Advanced SSH & Web Terminal**, enter the following command:

```bash
wget -O /tmp/install.py https://raw.githubusercontent.com/ha-energymanager/ha-energymanager/main/install.py && python3 -u /tmp/install.py
```

This downloads the bootstrap script from the official production repository and runs it.

## 3. Follow the on-screen prompts

The installer handles the setup in a single run. During startup it:

- Checks that Home Assistant Core meets the minimum version requirement.
- Checks Marketplace readiness, asks for the required consent, and handles GitHub authentication as prompted.
- Requests your **Solcast API key** and **Solcast resource ID(s)**. Solcast is required for Energy Manager optimisation. You may skip entry during installation, but must configure it later.
- Requests your **Energy Manager key**. If skipped, automated optimisation will not operate until the key is configured.

The API keys are entered directly into the terminal prompts. Follow the instructions shown by the installer.

## 4. Let the installer complete the deployment

After the prompts, the installer automatically:

1. Downloads and prepares Energy Manager's support scripts.
2. Installs and configures the required Home Assistant Apps and Node-RED dependencies.
3. Deploys Home Assistant configuration, dashboards, automations and Node-RED flows.
4. Installs the required Marketplace components listed in the release manifest.
5. Configures SSH-key access for future Energy Manager updates.
6. Registers automated post-reboot configuration for MQTT and Node-RED.
7. Checks the Home Assistant configuration and requests a **full Home Assistant OS reboot**.

The terminal **will disconnect during the reboot** under normal circumstances; this is expected. If configuration validation fails, the installer does not request the reboot: review the error shown in the terminal first.

## 5. Complete the Home Assistant setup

After Home Assistant is back online, allow its post-reboot setup to complete, then perform a forced cache clear:
- Press **F12** to enter developer mode in your browser. **Right-click on the refresh button** and select **Empty Cache and Hard Reload**. Press **ESC** to exit developer mode.

Configure the integrations and settings relevant to your system:

- Inverter and battery integration (or modify /config/secrets.yaml if using modbus for inverter control)
- Solcast integration, if details were not entered during installation.
- Electricity retailer, tariff and Energy Manager settings.
- EV charger integration and settings, if applicable.

Use the Energy Manager dashboards to confirm that the required entities, forecasts and device readings are available before enabling automated control.

## 6. Troubleshooting and logs

The installer saves diagnostic information under `/config/.energy_manager/`. In Advanced SSH & Web Terminal, useful checks include:

```bash
cat /config/.energy_manager/install-status.json
cat /config/.energy_manager/post-reboot-status.json
cat /config/.energy_manager/marketplace-install.log
cat /config/.energy_manager/post-reboot.log
```

Some files may not exist until their installation stage has started. If a stage fails, use the error displayed in the terminal or the relevant log to diagnose it before rerunning the installer.

For community support, use [Energy Manager GitHub Discussions](https://github.com/ha-energymanager/ha-energymanager/discussions).
