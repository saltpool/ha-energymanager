# Installing Energy Manager

Energy Manager can be installed on a fresh Home Assistant OS system using its automated installer. There is no need to restore a pre-configured Home Assistant backup or manually copy Energy Manager files.

This guide assumes Home Assistant OS has already been installed, is running, and you can sign in to its web interface.

## 1. Install Advanced SSH & Web Terminal

1. In Home Assistant, open **Settings → Apps** (called **Add-ons** in some versions).
2. Open the app store.
3. Find **Advanced SSH & Web Terminal** and select **Install**. Make sure you choose **Advanced SSH & Web Terminal**, not the similarly named official Terminal & SSH app.
4. When installation finishes, open the app's **Configuration** tab.
5. Under `ssh`, set a temporary password of your choice. For example, the configuration should contain an entry like this (preserve the other existing settings):

   ```yaml
   ssh:
     username: hassio
     password: "YOUR_STRONG_TEMPORARY_PASSWORD"
   ```

   Replace the placeholder with your own strong password. The exact layout of the configuration may differ by app version; change the `ssh.password` value rather than replacing the entire configuration.

6. **Save** the configuration.
7. Return to the app's **Info** tab, then select **Start**.
8. Optionally enable **Start on boot** and **Show in sidebar** for easier access.
9. Select **Open Web UI** to launch the terminal.

You should now see a command prompt inside the Advanced SSH & Web Terminal app. All remaining installation commands in this guide are entered there, **not** in a terminal on your computer.

> **Important:** The temporary password is used only to get the terminal app running. The Energy Manager installer creates and configures its own SSH key for subsequent automated operations. Do not disable or remove the SSH app during installation.

## 2. Download and launch the Energy Manager installer

In the Advanced SSH & Web Terminal terminal, copy and paste the following commands:

```bash
wget -qO /tmp/install.py https://raw.githubusercontent.com/ha-energymanager/ha-energymanager/main/install.py
python3 /tmp/install.py
```

These commands download the installer from the Energy Manager GitHub repository and run it.

**Keep the terminal open while the installer runs.** The installer displays progress and any errors directly in the terminal.

## 3. What the installer does

The installer automatically:

1. Prepares the Energy Manager installation directories, helper scripts, and SSH key.
2. Installs and configures the required Home Assistant apps and Node-RED dependencies.
3. Deploys Energy Manager configuration files, dashboards, and Node-RED flows.
4. Downloads the HACS integration files, ready for initial setup in Home Assistant. It does **not** install the HACS-managed components at this stage.
5. Authorises Energy Manager's SSH key, validates the Home Assistant configuration, and requests a full Home Assistant OS reboot.

You do **not** need to separately install the other Energy Manager apps or manually deploy its configuration files.

The process may take some time, particularly while the required apps are being installed. Once the final reboot is requested, the web terminal will disconnect. **This is expected.**

If the installer reports an error, read the error message in the terminal rather than assuming installation has completed. If necessary, the installer supports individual stages using `python3 /tmp/install.py --step <stage>`; consult the project support community before retrying stages on a partially configured system.

## 4. Set up HACS after the first reboot

When Home Assistant is available again:

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **HACS** and select it. The first-stage installer has already installed the HACS integration files.
3. Follow the HACS onboarding instructions, including authorising HACS with your GitHub account.
4. Check that HACS appears as a configured integration and has completed initialisation before proceeding.

**Do not skip this step.** The second-stage installer uses the authorised HACS integration to download the components Energy Manager requires.

## 5. Install the HACS components (second stage)

Return to **Settings → Apps → Advanced SSH & Web Terminal → Open Web UI**.

Run these commands in the terminal:

```bash
wget -qO /tmp/install_hacs_components.py https://raw.githubusercontent.com/ha-energymanager/ha-energymanager/main/install_hacs_components.py
python3 /tmp/install_hacs_components.py
```

This second-stage installer:

1. Refreshes the Energy Manager HACS management script.
2. Reads the HACS components specified in the Energy Manager `manifest/manifest.json` file.
3. Installs or reconciles the required HACS integrations and frontend components, verifying that essential integration files are actually present.
4. Prepares the automated post-reboot configuration scripts.
5. Registers a one-time startup task for Advanced SSH & Web Terminal to complete configuration after reboot.
6. Requests another full Home Assistant OS reboot to load the newly installed custom integrations.

The terminal will disconnect when Home Assistant reboots. This is expected. **Allow the installer to report that its HACS operations completed successfully before treating this stage as finished.**

## 6. Complete setup after the second reboot

Once Home Assistant is available again, allow its installed integrations to start. The post-reboot configuration task runs through Advanced SSH & Web Terminal. If you need to verify its progress or troubleshoot an issue, check:

```bash
cat /config/.energy_manager/post-hacs-status.json
cat /config/.energy_manager/post-hacs.log
```

Then complete the site-specific configuration:

1. **Clear browser cache and force refresh** - Press **F12** and then right-click on the refresh button. Select **Empty Cache and Hard Reload** (then exit developer mode). This is required to remove stale cache which will be displaying "Entity not found" false positive errors.
2. Configure your inverter and other hardware connections.
3. Complete any required integration onboarding and credentials, including BOM and Solcast. These can both be installed from **Settings → Devices & services → Add integration** - search for **Bureau of Meteorology** and **Solcast**. Both of these **must** be configured for Energy Manager to function. 
4. Configure your electricity provider and Energy Manager account/API credentials. These can be found through the **PV Dashboard** ("PV" item on the left menu, then select the **settings** (cog) tab to configure. All the settings on this page must be configured.
5. Confirm that the Energy Manager dashboards, sensors and required integrations are working correctly.
6. Keep **MQTT discovery disabled**, as required for this deployment.

The installation scripts deploy the software and automate common setup tasks, but they cannot supply your inverter connection details, provider credentials or other site-specific settings.

## Troubleshooting

**The Advanced SSH & Web Terminal app will not start:** Check that a valid password has been entered under `ssh.password`, save the configuration, and try starting it again. Review the app log for details.

**The `wget` download fails:** Confirm that Home Assistant can access GitHub and that the branch and installer URL are correct. Do not execute an empty or partially downloaded script.

**The installer reports `Supervisor token not available`:** Run the command inside **Advanced SSH & Web Terminal**, rather than a separate SSH session or another terminal environment.

**The terminal disconnects at the end:** Both installer stages request a full Home Assistant OS reboot. Reopen Home Assistant after it restarts.

**The second stage reports that HACS is not running or authorised:** Complete HACS integration onboarding and GitHub authorisation in Home Assistant, then rerun `python3 /tmp/install_hacs_components.py`.

**HACS components appear missing after the second reboot:** Review `/config/.energy_manager/post-hacs.log` and `/config/.energy_manager/post-hacs-status.json` before retrying the second stage.

For installation questions and errors, use the [Energy Manager GitHub Discussions](https://github.com/ha-energymanager/ha-energymanager/discussions).
