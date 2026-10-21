# ⚡ Energy Manager

> **⚠️ Important:** Do not use files directly from this repository unless instructed to do so. Using files that are not yet ready for release may break your existing Energy Manager configuration.

### Smarter Solar. Smarter Batteries. Lower Electricity Bills.

**Energy Manager** is an Australian-developed energy optimisation system that helps you get more value from your solar panels, home battery, electric vehicle and electricity plan.

Rather than relying on fixed charging schedules, basic price triggers or simple solar self-consumption rules, Energy Manager takes a forward-looking approach to household energy optimisation.

It combines electricity prices, solar generation forecasts, historical household consumption, battery capacity and EV charging requirements to develop an intelligent energy plan.

With advanced features such as **Dynamic Battery Charging, Dynamic Battery Reserves, forecast-driven energy exporting and intelligent EV charging**, Energy Manager continuously adapts to changing conditions to help maximise the value of your solar and battery investment.

The goal is simple: **buy electricity when it's cheap, store energy when it makes sense, and export electricity when it's most valuable.**

🌐 **[Visit EnergyManager.com.au to learn more and get started](https://energymanager.com.au/)**

---

## ☀️ Intelligent Energy Management — Beyond Simple Automation

Most energy management systems react to what's happening right now. **Energy Manager looks ahead**, using electricity pricing, solar generation forecasts, historical household consumption and battery information to plan how your energy should be managed over the coming hours.

Rather than relying on fixed charging schedules or simple automation rules, Energy Manager continuously evaluates changing conditions and adjusts its decisions to make better use of your solar, battery and electricity plan.

### 🧠 Smarter Battery Management

- **Dynamic Battery Charging** — Instead of always charging your battery at maximum power, Energy Manager dynamically adjusts the charging rate to reach your desired battery level when it's actually needed. This leaves more solar energy available for export when appropriate, while ensuring the battery is prepared for upcoming expensive electricity periods.
- **Dynamic Battery Reserve** — Automatically calculates how much battery energy should be reserved for household consumption based on forecast solar generation, expected household demand and upcoming electricity prices. This helps avoid unnecessary grid imports while allowing more stored energy to be exported when financially beneficial.
- **Forecast-Driven Energy Planning** — Plans battery charging, discharging and energy exports using upcoming solar generation, household demand and electricity pricing rather than fixed schedules alone.
- **Intelligent Grid Charging** — Takes advantage of cheap, free or negative-priced electricity to charge your battery, while respecting your chosen charging limits and target battery level.
- **Peak Period Protection** — Prepares your battery ahead of expensive electricity periods and prioritises stored energy to reduce costly grid imports.
- **Intelligent Self-Consumption** — Balances storing solar energy for later use against opportunities to export energy when feed-in tariffs are attractive.

### ⚡ Smarter Electricity Buying & Selling

- **Intelligent Energy Exporting** — Automatically identifies valuable export opportunities and manages battery discharging to take advantage of favourable feed-in tariffs, including time-limited export incentives.
- **Electricity Price Spike Optimisation** — For supported wholesale electricity plans, anticipates high-price periods and prepares your battery to take advantage of favourable market conditions.
- **Negative Electricity Price Protection** — Automatically reduces or curtails solar exports when negative feed-in tariffs could cost you money.
- **Retail Tariff Optimisation** — Optimises around free electricity windows, time-of-use tariffs, special export periods and configurable energy prices, not just wholesale electricity markets.
- **Export Limits & Energy Reserves** — Respects configurable export allowances, battery reserve requirements and inverter limitations when making energy decisions.
- **Free Electricity Optimisation** — Makes intelligent use of free grid electricity periods, including dynamically managing battery charging to reach your target before the free period ends.

### 🚗 Intelligent EV Charging

Energy Manager coordinates EV charging with your solar panels, home battery and electricity plan, rather than treating your vehicle as a separate electrical load.

- **Solar-Only Charging** — Charges your EV using available excess solar generation, helping avoid unnecessary electricity imports while preserving energy needed by your household and home battery.
- **Solar-Preferred Charging** — Prioritises excess solar while allowing controlled grid assistance to maintain a minimum charging rate, subject to your configured electricity price limits.
- **Smart Cheapest Charging** — Identifies the lowest-cost charging opportunities within your chosen charging window, rather than relying entirely on fixed charging times.
- **Scheduled & Ready-By Charging** — Plans charging around your preferred charging times and energy requirements, using solar and grid energy according to your selected strategy.
- **Battery-Aware EV Charging** — Coordinates EV demand with home battery charging and reserve requirements, including configurable limits on whether stored battery energy can be used for the vehicle.
- **Dynamic EV Charging Current** — Adjusts EV charging current according to available solar surplus, configured electrical limits and your charging preferences.
- **Forecast EV Charging Plans** — Includes expected EV energy requirements in household energy forecasts, allowing vehicle charging to be considered alongside other household energy needs.

### 📊 Visibility, Forecasting & Control

- **24-Hour Energy Planning** — See how your system expects to charge, discharge, import, export and use energy over the coming 24 hours.
- **Solar & Weather Forecasting** — Incorporates solar generation predictions and weather information when calculating charging and energy management strategies.
- **Household Consumption Forecasting** — Uses historical electricity consumption patterns to anticipate household energy requirements and improve battery planning.
- **Energy Monitoring Dashboard** — Monitor electricity prices, solar generation, household consumption, battery operation, EV charging and upcoming energy decisions.
- **Customisable Energy Strategies** — Configure battery reserves, charging targets, import price limits, export preferences and other operating parameters to suit your household.
- **Automatic Replanning** — Regularly reassesses energy decisions as solar forecasts, household consumption, electricity prices and battery conditions change.

**The result?** A coordinated energy management system that looks beyond individual devices and works to optimise your entire household's electricity usage.

Whether you're taking advantage of wholesale electricity prices, free daytime imports, peak-time export incentives or simply trying to maximise self-consumption, Energy Manager adapts its strategy to suit your electricity plan and preferences.

---

## 🔌 Supported Equipment & Electricity Providers

Energy Manager works with a range of solar and battery systems and electricity pricing arrangements.

Depending on your setup, these may include equipment from **Sungrow, Sigenergy, AlphaESS, GoodWe, Fronius and SolarEdge**, and tariffs from **Amber Electric, LocalVolts, Flow Power, GloBird and many other providers**.

Many electricity plans can be configured using custom import rates, export tariffs, free electricity periods and time-of-use schedules.

Unlike solutions designed around a single electricity retailer, Energy Manager can accommodate different electricity pricing structures, allowing you to choose an electricity plan that suits your household.

Compatibility depends on your specific inverter model, battery configuration and electricity plan.

**[Check current compatibility and requirements on our website →](https://energymanager.com.au/)**

---

## 🏠 Powered by Home Assistant

Energy Manager uses [Home Assistant](https://www.home-assistant.io/) to connect with and control supported energy equipment in your home.

A pre-configured Home Assistant installation provides the monitoring dashboards, integrations and device controls required to operate Energy Manager.

Energy Manager combines information from your equipment, electricity pricing and energy forecasts to develop an optimised energy plan. Your local Home Assistant system then carries out the applicable control instructions.

**No additional proprietary hardware is required.**

Energy Manager requires a clean, dedicated Home Assistant OS installation. It is not designed to be installed as an integration into an existing Home Assistant system.

---

## 🤝 Community Support

Energy Manager is designed to be a self-managed solution, with support provided through **Github Discussions**. Casual chat is also available through our Discord channel.

Our Discord community is a place where users can share experiences, exchange configuration tips and help one another get the most out of Energy Manager. Any configuration updates or bug fixes belong in Github code, and enhancement discussions belong in Github Discussions (with code in Github code).

Whether you're getting started, exploring advanced features or troubleshooting an issue, you're welcome to join the conversation and benefit from the knowledge and experience of other users.

**Please note that Energy Manager operates on a community-supported basis.** Individual technical assistance, personalised troubleshooting and direct developer support are not included with the subscription. Community assistance is provided voluntarily, so responses and resolutions cannot be guaranteed.

We encourage everyone to contribute where they can. Sharing your experiences, solutions and ideas helps build a stronger and more useful community for everyone.

### 💬 [Join the Energy Manager Discord Community →](https://discord.gg/yeVxvmADKn)

*Thank you for being part of the Energy Manager community and helping make it a welcoming and supportive place for everyone.*

---

## 🚀 Put Your Solar & Battery to Work

You've already invested in solar panels and battery storage. Why settle for basic charging schedules when your system could be making smarter energy decisions throughout the day?

Energy Manager brings advanced battery optimisation, electricity price awareness, predictive energy planning and EV charging coordination together in one system — without requiring you to develop and maintain complex automations yourself.

### 💡 Try Energy Manager for 30 Days — Free

Experience automated energy optimisation with a **30-day free trial**.

After your trial, continue using automated energy management for just **$10 AUD per month**.

Energy Manager is self-managed, with community-based support available. Direct developer support is not included.

The website provides the official setup process, including registration, installation guidance, configuration instructions and current compatibility information.

### ⚡ [Discover Energy Manager & Start Your Free Trial →](https://energymanager.com.au/)

*Smarter decisions. Better energy utilisation. More value from the equipment you already own.*

---

## 📂 About This Repository

This repository contains the publicly available Home Assistant configuration files, scripts and supporting resources used by Energy Manager.

**This repository is not a standalone installation package, and access to the files does not include the subscription-based automation service.**

To use Energy Manager, follow the official setup process on the website. Registration and a pre-configured Home Assistant installation are required.

For installation, updates, documentation and further information, visit:

**🌐 https://energymanager.com.au/**

---

*Developed in Australia, for Australian electricity markets.* 🇦🇺
