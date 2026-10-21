# Contributing to Energy Manager

Thank you for your interest in improving **Energy Manager**! Community contributions are welcome, whether you are fixing a bug, improving documentation, adding a feature, or extending support to another inverter brand or model.

Energy Manager combines public Home Assistant configuration and supporting code with a **private decision-making backend**. You can contribute to the public repository, and you can propose changes to the backend's behaviour, but the backend source code is not available for community editing.

## Pull requests: `development` only

**All pull requests must target the `development` branch.** Pull requests aimed at `test`, `early`, or `main` will be rejected or closed and may be resubmitted against `development`.

Our release process is:

`development` → `test` → `early` → `main`

These later branches are maintained for testing and release promotion. Please do not open pull requests against them, even for small fixes or documentation updates.

## What you can contribute

We welcome contributions such as:

- Support for additional inverter brands and models.
- Improvements to existing inverter configurations and controls.
- New Home Assistant features, helpers, scripts, automations and dashboards.
- EV charger compatibility and related improvements.
- Bug fixes, usability improvements and documentation updates.
- Ideas for new Energy Manager capabilities or improvements to energy optimisation behaviour.

Please keep contributions aligned with Energy Manager's existing architecture and conventions, rather than introducing a separate implementation pattern for the same functionality.

## Follow the existing structure

When preparing changes:

1. Use the existing directory layout, naming conventions, entity patterns and configuration structure.
2. Follow comparable implementations already in the repository, especially when adding support for a new inverter or device.
3. Avoid changing established interfaces, entity names or behaviour unless the change is necessary and clearly explained.
4. Keep changes focused and include relevant documentation or configuration updates.
5. Test what you can and describe what you tested in your pull request. If you cannot test with physical hardware, state that clearly.

For a new inverter brand or model, identify the supported models, required entities or sensors, available control actions and any known limitations. Where possible, provide examples of the expected Home Assistant entity mapping and behaviour.

## Changes involving the private backend

The decision-making backend is not included in this repository. As a result, contributors cannot directly implement or test changes to its internal logic.

**If your contribution requires new or changed backend logic, make that requirement explicit in code comments near the relevant configuration or integration point and explain it in your pull request.**

Please include:

- **What is needed:** The feature or behavioural change you are proposing.
- **Why it is needed:** The problem it solves or the expected benefit.
- **Inputs:** Any new entities, settings, sensor values or other information the backend would need.
- **Expected behaviour:** What the backend should do, including important conditions and edge cases.
- **Outputs:** Any new or changed decisions, values or actions that Home Assistant would need to receive.

For example:

```yaml
# BACKEND LOGIC REQUEST:
# When this inverter reports that battery discharge is unavailable,
# the decision logic should avoid requesting battery discharge.
# Input: sensor.example_battery_discharge_available (on/off)
# Expected behaviour: do not issue discharge commands when off.
# No change is required to charging or solar curtailment behaviour.
```

This is an illustration only; use the conventions appropriate to the file you are changing.

Backend-related requests will be reviewed for feasibility and compatibility. **A pull request being accepted does not guarantee that a proposed backend change will be implemented.** Please do not assume that backend behaviour has changed until it has been confirmed.

## How to submit a pull request

1. Fork the repository on GitHub.
2. Create a working branch from the latest `development` branch in your fork.
3. Make and test your changes, following the existing structure.
4. Commit your changes with a clear description.
5. Open a pull request against **`ha-energymanager/ha-energymanager` → `development`**.

In your pull request, describe the change, why it is useful, any affected inverter brands or models, the testing completed, and any required private-backend changes. Screenshots, examples or relevant logs are helpful when appropriate; remove passwords, tokens and other personal information before sharing.

## Review and acceptance

Contributions are reviewed for fit, maintainability, compatibility and safety. Changes may be discussed, revised, deferred or declined, particularly if they require unavailable hardware for testing or substantial changes to the private backend.

Please be patient and respectful during review. Community contributions are appreciated, but submission does not guarantee inclusion or a specific review timeframe.

Thank you for helping make Energy Manager better for everyone!
