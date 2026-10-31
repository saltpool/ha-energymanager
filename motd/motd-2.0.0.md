# Energy Manager v2.0.0

Welcome to Energy Manager v2.0.0.

This release contains some backend modifications to increase stability of updates and to reduce the requirements of users having to manually update configuration settings to perform an update. It also contains some major user-interface (UI) updates.

## Github is now used for updates

Github is now the source location for any updates. The **ha-energymanager** repository contains four branches:
- main
- early
- test
- development
  
A new entity, found on the PV Dashboard settings page, allows you to select which branch of "main" or "early" you would like your updates to come from. The "Early" branch will receive updates to new version before the "main" branch, and you're welcome to select "early" if you wish to obtain earlier updates. Just remember there is more risk using the "early" branch because less people will have tested it. If you use "early" there is an expectation that you will report any bugs that you find so that when it is later released to "main" they have been removed.

The procedure for new releases will always proceed through the following order:
1. Updates are made to "development". You should not use this branch as it will be guaranteed to break your Energy Manager.
2. Updates are pushed from "development" to "test". You should not use this branch as it is still likely that it will break your Energy Manager.
3. Updates are pushed from "test" to "early". If you would like to receive early updates, select this branch. By the time the code gets to this branch, it has travelled through both "development" and "test", bugs fixed, and then moved to "early". There is still a chance of bugs being present, but less likely than the previous "test" branch.
4. Shortly after "early" is released, the "main" branch will get updated and the update is released as GA.

You are most welcome to contribute to this project by creating a pull request against the **development** branch.
- If you want a new inverter brand supported, you can follow the logic of an existing brand and port it over to the new brand. Please feel free to request help on how to do this if you are not sure.
- If you see a bug, please create a pull request against the development branch and suggest the fix, if you can see what is wrong
- If you want to see enhancements or improvements to a dashboard, please feel free to suggest the update through a pull request

## The PV Dashboard has changed

The PV Dashboard has been optimised and has brought aspects from a number of existing dashboards (plus some new stuff) to one dashboard. Information that seldom changes has been moved to another dashboard tab. It is possible, through the PV Dashboard settings, to disable or enable features of the PV Dashboard as not everyone will want all features enabled all the time.

## The Price Strategy Configurator has changed

The SVG images have been replaced for the **wholesale**, **Flow Power** and **GloBird** electricity providers. Now running JS with interactive sliders so that it should be much easier to navigate and configure.

## UI entities converted to YAML based

The Home Assistant side of Energy Manager has grown over the last year and a half and some historical settings remained as part of the user interface and not as Home Assistant YAML. This has caused added steps during an update that the owner of the Home Assistant instance has had to manually do. With the migration to using Github for updates, a migration script was written to migrate the 35 entities that were not yet in YAML, to YAML. What this means as in the future the update procedure should be greatly simplified.

## Other updates

### MOTD
This MOTD page now contains three columns, instead of the original single column:
1. Version specific notes (this column)
2. General announcements for all versions
3. Detailed changelog for all versions

### EV Charging
If EV charging is in progress, Energy Manager will now check with the backend servers once per minute, instead of the default once per 5 minutes. This will give a finer control of EV charging amperage, meaning that it should offer more time-critical decisions like altering the charging rate for solar_only and solar_preferred policies.

The **events card** has been updated to include EV charging forecasts and history.

### HACS component add & removes
HACS component installs and removals, along with specified version requirements, are now included in the update script. This means that if an old component is retired by the HACS team that we can simply include the removal and/or replacement in the next update, meaning that you do not need to manually perform the work yourself.  If there are new HACS components that would improve Energy Manager, we can simply add them in to be automatically installed on the next update.

### Various other bug fixes
Refer to the Changelog, on the right, for other bug fixes/updates included in v1.3.0
