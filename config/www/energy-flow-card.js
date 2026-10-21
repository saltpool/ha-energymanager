// /config/www/energy-flow-card.js
// Energy Manager v2.0.0

class EnergyFlowCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this.particles = [];
      this.animationId = null;
      this._hass = null;
      this._onLocationChanged = this.updateValues.bind(this);
      this._onThemeChanged = this.updateTheme.bind(this);
    }
  
    setConfig(config) {
      if (!config) throw new Error('Invalid configuration');
  
      this.config = {
        solar_entity: config.solar_entity || 'sensor.inverter_pv_power',
        load_entity: config.load_entity || 'sensor.inverter_load_power',
        import_entity: config.import_entity || 'sensor.inverter_import_power',
        export_entity: config.export_entity || 'sensor.inverter_export_power',
        battery_charging_entity: config.battery_charging_entity || 'sensor.inverter_battery_charging_power',
        battery_discharging_entity: config.battery_discharging_entity || 'sensor.inverter_battery_discharging_power',
        battery_level_entity: config.battery_level_entity || 'sensor.inverter_battery_level',
        battery_charge_entity: config.battery_charge_entity || 'sensor.inverter_battery_charge',
  
        battery_charge_limit_entity: config.battery_charge_limit_entity || 'input_number.battery_charge_power_hardlimit',
        battery_discharge_limit_entity: config.battery_discharge_limit_entity || 'input_number.battery_discharge_power_hardlimit',
        export_limit_entity: config.export_limit_entity || 'input_number.inverter_export_power_hardlimit',
        solar_array_size_entity: config.solar_array_size_entity || 'input_number.solar_array_size',
        import_limit: config.import_limit || 15000,
  
        light_theme_image: config.light_theme_image || '/local/energy-flow.svg',
        dark_theme_image: config.dark_theme_image || '/local/energy-flow-dark.svg',
  
        title: config.title || 'Power Flow',
        ...config,
      };
  
      this.render();
    }
  
    set hass(hass) {
      this._hass = hass;
      this.updateValues();
      this.updateTheme();
    }
  
    isDarkMode() {
      const dm = this._hass?.themes?.darkMode;
      if (typeof dm === 'boolean') return dm;
  
      const name =
        this._hass?.themes?.activeTheme ||
        this._hass?.selectedTheme?.theme ||
        '';
      if (typeof name === 'string' && name.toLowerCase().includes('dark')) {
        return true;
      }
  
      const bg = getComputedStyle(document.documentElement)
        .getPropertyValue('--primary-background-color')
        .trim();
      if (bg) return this._isColorDark(bg);
  
      return false;
    }
  
    _isColorDark(color) {
      let r, g, b;
      const hex = color.match(/^#([0-9a-f]{3}){1,2}$/i);
      if (hex) {
        let v = hex[0].substring(1);
        if (v.length === 3) v = v.split('').map((c) => c + c).join('');
        r = parseInt(v.slice(0, 2), 16);
        g = parseInt(v.slice(2, 4), 16);
        b = parseInt(v.slice(4, 6), 16);
      } else {
        const rgb = color.match(/rgba?\s*\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
        if (!rgb) return false;
        r = parseFloat(rgb[1]);
        g = parseFloat(rgb[2]);
        b = parseFloat(rgb[3]);
      }

      const lum =
        (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
      return lum < 0.5;
    }

    updateTheme() {
      const isDark = this.isDarkMode();
      const imagePath = isDark ? this.config.dark_theme_image : this.config.light_theme_image;
      const houseImage = this.shadowRoot.querySelector('.house-image');
      if (houseImage) {
        houseImage.setAttribute('src', imagePath);
      }
    }
  
    render() {
      const isDark = this.isDarkMode();
      const imagePath = isDark ? this.config.dark_theme_image : this.config.light_theme_image;
  
      this.shadowRoot.innerHTML = `
        <style>
          ha-card {
            padding: 0;
            overflow: hidden;
            background: linear-gradient(135deg, var(--ha-card-background) 0%, var(--ha-card-background) 100%);
            border-radius: 15px;
            position: relative;
            height: 400px;
          }
          .energy-container { position: relative; width: 100%; height: 100%; overflow: hidden; }
          .house-image { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); max-width: 80%; max-height: 70%; z-index: 2; opacity: 0.9; }
          .energy-label { position: absolute; background: var(--ha-card-background); color: var(--primary-text-color);
            padding: 8px 12px; border-radius: 15px; font-size: 12px; font-weight: 600; border: 1px solid rgba(255,255,255,0.3);
            backdrop-filter: blur(10px); z-index: 10; transition: all 0.3s ease; animation: labelFloat 3s ease-in-out infinite;
            min-width: 60px; text-align: center; }
          .label-solar { top: 4%; left: 50%; transform: translateX(-50%); color: #f1c40f; border-color: #f1c40f; opacity: 0.9; }
          .label-house { top: 50%; right: 0%; transform: translateX(-50%); color: rgb(47, 142, 250); border-color: rgb(47, 142, 250); }
          .label-grid { top: 5%; left: 10%; color: #e74c3c; border-color: #e74c3c; }
          .label-battery { bottom: 20%; left: 20%; color: #27ae60; border-color: #27ae60; }
          @keyframes labelFloat { 0%,100% { transform: translateX(-50%) translateY(0px); } 50% { transform: translateX(-50%) translateY(-3px); } }
          .label-grid { animation: labelFloatGrid 3s ease-in-out infinite; }
          .label-battery { animation: labelFloatBattery 3s ease-in-out infinite; }
          @keyframes labelFloatGrid { 0%,100% { transform: translateY(0px); } 50% { transform: translateY(-3px); } }
          @keyframes labelFloatBattery { 0%,100% { transform: translateY(0px); } 50% { transform: translateY(-3px); } }
          .particle { position: absolute; width: 15px; height: 6px; border-radius: 50%; z-index: 5; pointer-events: none; animation-iteration-count: infinite; animation-timing-function: linear; animation-play-state: paused; }
          .particle-house { background: radial-gradient(circle, rgb(47, 142, 250), transparent); box-shadow: 0 0 10px rgb(47, 142, 250); animation-name: moveHouseLoad; }
          .particle-solar { background: radial-gradient(circle, #f1c40f, transparent); box-shadow: 0 0 10px #f1c40f; animation-name: moveSolar; }
          .particle-grid-import { background: radial-gradient(circle, #e74c3c, transparent); box-shadow: 0 0 10px #e74c3c; animation-name: moveGridImport; }
          .particle-grid-export { background: radial-gradient(circle,rgb(185, 3, 134), transparent); box-shadow: 0 0 10px rgb(185, 3, 134); animation-name: moveGridExport; }
          .particle-battery-charge { background: radial-gradient(circle, #27ae60, transparent); box-shadow: 0 0 10px #27ae60; animation-name: moveBatteryCharge; }
          .particle-battery-discharge { background: radial-gradient(circle, #27ae60, transparent); box-shadow: 0 0 10px #27ae60; animation-name: moveBatteryDischarge; }
          .card-header { padding: 12px 16px; font-size: 16px; font-weight: 500; color: #27ae60; text-align: center; position: relative; z-index: 10; }
          .no-data { display: flex; align-items: center; justify-content: center; height: 200px; color: white; font-size: 14px; }
          .error-message { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #e74c3c; text-align: center; font-size: 14px; background: rgba(0,0,0,0.8); padding: 20px; border-radius: 10px; z-index: 15; }
          @keyframes moveHouseLoad { 0% { top: 55%; left: 55%; opacity: 0; } 1% { opacity: 1; } 99% { opacity: 1; } 100% { top: 55%; left: 72%; opacity: 0; } }
          @keyframes moveSolar { 0% { top: 20%; left: 50%; opacity: 0; } 1% { opacity: 1; } 99% { opacity: 1; } 100% { top: 55%; left: 55%; opacity: 0; } }
          @keyframes moveGridImport { 0% { top: 30%; left: 25%; opacity: 0; } 1% { opacity: 1; } 99% { opacity: 1; } 100% { top: 55%; left: 55%; opacity: 0; } }
          @keyframes moveGridExport { 0% { top: 55%; left: 55%; opacity: 0; } 1% { opacity: 1; } 99% { opacity: 1; } 100% { top: 30%; left: 25%; opacity: 0; } }
          @keyframes moveBatteryCharge { 0% { top: 55%; left: 55%; opacity: 0; } 1% { opacity: 1; } 99% { opacity: 1; } 100% { top: 70%; left: 35%; opacity: 0; } }
          @keyframes moveBatteryDischarge { 0% { top: 70%; left: 35%; opacity: 0; } 1% { opacity: 1; } 99% { opacity: 1; } 100% { top: 55%; left: 55%; opacity: 0; } }
        </style>
  
        <ha-card>
          <div class="card-header">${this.config.title}</div>
          <div class="energy-container">
            <img class="house-image" src="${imagePath}" alt="House Power Flow"
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="error-message" style="display: none;">
              Image not found:<br>
              <small>Please upload your SVGs to /config/www/</small>
            </div>
  
            <div class="energy-label label-solar">☀️ Solar<br><span class="solar-value">-- kW</span></div>
            <div class="energy-label label-house">🏠 Load<br><span class="house-value">-- kW</span></div>
            <div class="energy-label label-grid">⚡ Grid<br><span class="grid-value">-- kW</span></div>
            <div class="energy-label label-battery">🔋 Battery<br><span class="battery-value">-- kW</span><br><span class="battery-level">--%</span></div>
          </div>
        </ha-card>
      `;
  
      this.createParticles('house', 3);
      this.createParticles('solar', 3);
      this.createParticles('grid-import', 3);
      this.createParticles('grid-export', 3);
      this.createParticles('battery-charge', 3);
      this.createParticles('battery-discharge', 3);
    }
  
    connectedCallback() {
      this.updateValues();
      window.addEventListener('location-changed', this._onLocationChanged);
      window.addEventListener('hass-themes-updated', this._onThemeChanged);
      window.addEventListener('settheme', this._onThemeChanged);
      window.addEventListener('color-scheme-changed', this._onThemeChanged);
    }
  
    disconnectedCallback() {
      if (this.animationId) cancelAnimationFrame(this.animationId);
      this.particles.forEach((p) => p.element?.remove?.());
      window.removeEventListener('location-changed', this._onLocationChanged);
      window.removeEventListener('hass-themes-updated', this._onThemeChanged);
      window.removeEventListener('settheme', this._onThemeChanged);
      window.removeEventListener('color-scheme-changed', this._onThemeChanged);
    }
  
    updateValues() {
      if (!this._hass) return;

      this.updateTheme();
  
      try {
        const solarState = this._hass.states[this.config.solar_entity];
        const loadState = this._hass.states[this.config.load_entity];
        const importState = this._hass.states[this.config.import_entity];
        const exportState = this._hass.states[this.config.export_entity];
        const batteryChargingState = this._hass.states[this.config.battery_charging_entity];
        const batteryDischargingState = this._hass.states[this.config.battery_discharging_entity];
        const batteryLevelState = this._hass.states[this.config.battery_level_entity];
  
        const batteryChargeLimit = this._hass.states[this.config.battery_charge_limit_entity]
          ? parseFloat(this._hass.states[this.config.battery_charge_limit_entity].state) : 5.0;
        const batteryDischargeLimit = this._hass.states[this.config.battery_discharge_limit_entity]
          ? parseFloat(this._hass.states[this.config.battery_discharge_limit_entity].state) : 5.0;
        const exportLimit = this._hass.states[this.config.export_limit_entity]
          ? parseFloat(this._hass.states[this.config.export_limit_entity].state) : 5.0;
        const importLimit = this.config.import_limit;
        const solarArraySize = this._hass.states[this.config.solar_array_size_entity]
          ? parseFloat(this._hass.states[this.config.solar_array_size_entity].state) * 1000 : 5000;

        const solarValue = solarState ? parseFloat(solarState.state) || 0 : 0;
        const loadValue = loadState ? parseFloat(loadState.state) || 0 : 0;
        const importValue = importState ? parseFloat(importState.state) || 0 : 0;
        const exportValue = exportState ? parseFloat(exportState.state) || 0 : 0;
        const batteryChargingValue = batteryChargingState ? parseFloat(batteryChargingState.state) || 0 : 0;
        const batteryDischargingValue = batteryDischargingState ? parseFloat(batteryDischargingState.state) || 0 : 0;
        const batteryLevelValue = batteryLevelState ? parseFloat(batteryLevelState.state) || 0 : 0;
  
        this.shadowRoot.querySelector('.solar-value').textContent = `${(solarValue / 1000).toFixed(2)} kW`;
        this.shadowRoot.querySelector('.house-value').textContent = `${(loadValue / 1000).toFixed(2)} kW`;
  
        const netGrid = importValue - exportValue;
        this.shadowRoot.querySelector('.grid-value').textContent = `${(Math.abs(netGrid) / 1000).toFixed(2)} kW`;
  
        const netBattery = batteryChargingValue - batteryDischargingValue;
        this.shadowRoot.querySelector('.battery-value').textContent = `${(Math.abs(netBattery) / 1000).toFixed(2)} kW`;
        this.shadowRoot.querySelector('.battery-level').textContent = `${batteryLevelValue.toFixed(0)}%`;
  
        this.energyData = {
          solar: { power: solarValue, max: solarArraySize },
          load: { power: loadValue, max: loadValue > 0.1 ? loadValue * 2 : 5000 },
          gridImport: { power: Math.max(0, netGrid), max: importLimit },
          gridExport: { power: Math.max(0, -netGrid), max: exportLimit },
          batteryCharge: { power: Math.max(0, netBattery), max: batteryChargeLimit },
          batteryDischarge: { power: Math.max(0, -netBattery), max: batteryDischargeLimit },
        };
  
        this.updateAnimationSpeeds();
  
      } catch (error) {
        console.warn('Power Flow Card: Error updating values', error);
      }
    }
  
    createParticles(type, numParticles) {
      const container = this.shadowRoot.querySelector('.energy-container');
      for (let i = 0; i < numParticles; i++) {
        const particle = document.createElement('div');
        particle.className = `particle particle-${type}`;
        particle.style.animationDelay = `${(i / numParticles) * -1.5}s`;
        container.appendChild(particle);
      }
    }
  
    updateAnimationSpeeds() {
      if (!this.energyData) return;
      const flows = [
        { type: 'house', power: this.energyData.load.power, max: this.energyData.load.max },
        { type: 'solar', power: this.energyData.solar.power, max: this.energyData.solar.max },
        { type: 'grid-import', power: this.energyData.gridImport.power, max: this.energyData.gridImport.max },
        { type: 'grid-export', power: this.energyData.gridExport.power, max: this.energyData.gridExport.max },
        { type: 'battery-charge', power: this.energyData.batteryCharge.power, max: this.energyData.batteryCharge.max },
        { type: 'battery-discharge', power: this.energyData.batteryDischarge.power, max: this.energyData.batteryDischarge.max },
      ];
  
      flows.forEach((flow) => {
        const particles = this.shadowRoot.querySelectorAll(`.particle-${flow.type}`);
        if (flow.power > 0.1) {
          const speed = this.calculateSpeed(flow.power, flow.max);
          particles.forEach((p) => {
            p.style.animationDuration = `${speed}s`;
            p.style.animationPlayState = 'running';
            p.style.display = 'block';
          });
        } else {
          particles.forEach((p) => {
            p.style.animationPlayState = 'paused';
            p.style.display = 'none';
          });
        }
      });
    }
  
    calculateSpeed(power, maxPower) {
      const minPower = 0.1;
      const minDuration = 5.0;
      const maxDuration = 0.5;
      const clampedPower = Math.max(minPower, Math.min(maxPower, power));
      const duration = minDuration + (maxDuration - minDuration) * ((clampedPower - minPower) / (maxPower - minPower));
      return duration;
    }
  
    getCardSize() {
      return 4;
    }
  }
  
  customElements.define('energy-flow-card', EnergyFlowCard);
  
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'energy-flow-card',
    name: 'Energy Flow Card',
    description: 'Animated energy flow visualization with particles over custom house image',
  });
  
  console.info(
    `%c ENERGY-FLOW-CARD %c Version 0.2.5 `,
    'color: white; background: steelblue; font-weight: 700;',
    'color: steelblue; background: white; font-weight: 700;'
  );
  

