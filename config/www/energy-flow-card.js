/* Energy Manager 3D Energy Flow Card — experimental. */
(() => {
  if (customElements.get('energy-flow-3d-card')) return;
  const NS = 'http://www.w3.org/2000/svg';
  const VIEW_W = 1536, VIEW_H = 1024;
  const DEFAULTS = {
    title: 'Energy Flow', image: '/local/energy-flow-house.png',
    ev_brand_entity: 'input_select.em_ev_brand', ev_connector_entity: 'sensor.charger_status_connector',
    ev_current_entity: 'sensor.charger_current_import', ev_phases_entity: 'input_select.em_ev_site_phases',
    ev_brands_dir: '/local/energy-flow/brands/', ev_max_power_w: 22080,
    solar_entity: 'sensor.inverter_pv_power', load_entity: 'sensor.inverter_load_power',
    import_entity: 'sensor.inverter_import_power', export_entity: 'sensor.inverter_export_power',
    battery_charging_entity: 'sensor.inverter_battery_charging_power',
    battery_discharging_entity: 'sensor.inverter_battery_discharging_power',
    battery_level_entity: 'sensor.inverter_battery_level',
    battery_charge_limit_entity: 'input_number.battery_charge_power_hardlimit',
    battery_discharge_limit_entity: 'input_number.battery_discharge_power_hardlimit',
    export_limit_entity: 'input_number.inverter_export_power_hardlimit',
    solar_array_size_entity: 'input_number.solar_array_size',
    import_limit: 15000, animation_speed: 1, threshold_w: 30,
    show_labels: true, show_title: true, solar_panel_glow: true, glow_intensity: 1,
    weather_entity: '', weather_effects: true, weather_intensity: 1, weather_test_condition: '',
    weather_cloud_image: '/local/energy-flow/weather/weather-cloud.png', weather_storm_cloud_image: '/local/energy-flow/weather/weather-storm-cloud.png',
    weather_rain_image: '/local/energy-flow/weather/weather-rain.png',
  };
  // Coordinates measured against the 1536×1024 supplied master image.
  // Routes converge at the centre of the wall-mounted inverter (772, 607).
  // Grid runs straight to the lower-left at approximately 245 degrees.
  const ROUTES = {
    solar:   {d:'M 918 166 C 924 251 916 332 878 428 S 813 542 772 607', color:'#f9c94d'},
    house:   {d:'M 772 607 C 840 575 903 547 1015 518',color:'#65b6ff'},
    battery: {d:'M 772 607 C 852 643 948 705 1064 764',color:'#43e3b6'},
    grid:    {d:'M 772 607 L 30 953',color:'#f28b52'},
    ev:      {d:'M 772 607 C 689 610 602 645 433 622',color:'#66f5d1'},
  };
  class EnergyFlow3DCard extends HTMLElement {
    constructor() { super(); this.attachShadow({mode:'open'}); this._hass=null; this._displayedImage=''; this._failedImages=new Set(); this._last={}; this._rainRaf=0; this._rainDrops=[]; this._snowRaf=0; this._snowflakes=[]; }
    setConfig(config) {
      if (!config || typeof config !== 'object') throw Error('Invalid 3D energy flow card config');
      this.config={...DEFAULTS,...config}; this.render(); this.updateValues();
    }
    set hass(hass) { this._hass=hass; this.updateValues(); }
    getCardSize() { return 5; }
    disconnectedCallback() { this._stopRain(); this._stopSnow(); }
    _number(entity, fallback=0) {
      const s=this._hass?.states?.[entity];
      if (!s || ['unknown','unavailable','none',''].includes(String(s.state).toLowerCase())) return fallback;
      const n=Number(s.state); if (!Number.isFinite(n)) return fallback;
      // Power entities are expected in W; respect kW reported by a sensor.
      return s.attributes?.unit_of_measurement === 'kW' ? n*1000 : n;
    }
    _limit(entity, fallback) {
      const s=this._hass?.states?.[entity]; const n=Number(s?.state);
      if (!Number.isFinite(n) || n <= 0) return fallback;
      if (s?.attributes?.unit_of_measurement === 'kW') return n*1000;
      // Legacy EM hardlimits normally expose W; solar array size is kW.
      return entity === this.config.solar_array_size_entity ? n*1000 : n;
    }
    _fmt(w) { return (Math.abs(w)/1000).toFixed(2)+' kW'; }
    render() {
      if(!this.config) return;
      this._stopRain(); this._stopSnow();
      this.shadowRoot.innerHTML=`
        <style>
          :host { display:block; }
          ha-card { overflow:hidden; background:var(--ha-card-background,var(--card-background-color,transparent)); color:var(--primary-text-color,#eee); }
          .heading { font-size:16px; font-weight:500; padding:14px 16px 0; }
          .stage { position:relative; width:100%; aspect-ratio:1536/1024; overflow:hidden; isolation:isolate; }
          .stage > img, .stage > svg { position:absolute; inset:0; width:100%; height:100%; display:block; }
          .house { object-fit:contain; z-index:0; }
          .flows { z-index:1; overflow:visible; pointer-events:none; }
          .trail { fill:none; stroke-width:3.5; opacity:.40; stroke-dasharray:4 10; stroke-linecap:round; }
          .route.active .trail { filter:drop-shadow(0 0 4px currentColor); }
          .core { stroke:white; stroke-width:1.2; opacity:.95; }
          .solar-panel-glow { pointer-events:none; opacity:0; transition:opacity .6s ease; }
          .solar-panel-glow.on { opacity:1; }
          .solar-panel-glow .panel-wash { animation:panel-breathe 3.8s ease-in-out infinite alternate; mix-blend-mode:screen; }
          .solar-panel-glow .panel-border { animation:panel-breathe 3.8s ease-in-out infinite alternate; }
          .weather-overlay { pointer-events:none; opacity:0; transition:opacity .7s ease; }
          .weather-overlay.on { opacity:1; }
          .weather-cloud { animation:weather-drift 9s ease-in-out infinite alternate; }
          .weather-rays { transform-origin:475px 145px; animation:weather-rays 14s linear infinite; }
          .weather-rain { animation:weather-fall 1.4s linear infinite; }
          .weather-rain.second {animation-delay:-.7s;}
          .weather-flash {animation:weather-flash 7s linear infinite;}
          @keyframes weather-drift {from{transform:translateX(-7px)}to{transform:translateX(12px)}}
          @keyframes weather-rays {to{transform:rotate(360deg)}}
          @keyframes weather-fall {0%{transform:translateY(-8px);opacity:0}25%{opacity:.85}100%{transform:translateY(22px);opacity:0}}
          @keyframes weather-flash {0%,89%,94%,100%{opacity:.1}90%,92%{opacity:1}}
          @keyframes panel-breathe {from{opacity:.65}to{opacity:1}}
          .halo { filter:url(#flow-glow); opacity:1; }
          .particle { filter:url(#flow-small-glow); opacity:1; }
          .route.inactive { display:none; }
          .metric { position:absolute; z-index:3; padding:5px 9px; border:1px solid var(--divider-color,#7777);
            border-radius:11px; background:var(--ha-card-background,var(--card-background-color,#222));
            color:var(--primary-text-color,#eee); box-shadow:0 2px 9px #0002;
            font-size:clamp(9px,1.25vw,13px); text-align:center; white-space:nowrap; max-width:calc(100% - 16px); box-sizing:border-box; line-height:1.35; }
          .metric strong { font-weight:650; }
          .solar-label { left:57%; top:6%; } .load-label {left:64%; top:44%;}
          .battery-label {right:2%; top:79%;} .grid-label {left:10%; top:71%;}
          .ev-label {left:17%;top:53%;}

          .weather-scene { position:absolute; inset:0; z-index:2; overflow:hidden; pointer-events:none; opacity:0; transition:opacity 1s ease; }
          .weather-scene.on {opacity:1}
          .cloudsprite {position:absolute; width:58%; height:auto; left:0%; top:-11%; opacity:0; filter:drop-shadow(0 5px 12px #121b2830); animation:cloud-move 14s ease-in-out infinite alternate; }
          .cloudsprite.cloud2 {left:39%;top:-15%;width:53%;animation-duration:20s;animation-direction:alternate-reverse;opacity:0}
          .weather-scene.cloudy .cloudsprite {opacity:.85}
          .weather-scene.partlycloudy .cloudsprite {opacity:.45}
          .weather-scene.rainy .cloudsprite, .weather-scene.pouring .cloudsprite, .weather-scene.stormy .cloudsprite {opacity:.95}
          .weather-scene.rainy .cloud2,.weather-scene.pouring .cloud2,.weather-scene.stormy .cloud2 {opacity:.77}
          .rainfield {display:none !important;} /* legacy repeating-line effect disabled */
          .weather-rain-sprite {display:none !important;} /* deprecated low-opacity APNG */
          .weather-rain-canvas {display:none;position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}
          .weather-scene.rainy .weather-rain-canvas,.weather-scene.pouring .weather-rain-canvas,.weather-scene.stormy .weather-rain-canvas {display:block;}
          .weather-snow-canvas {display:none;position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}
          .weather-scene.snowy .weather-snow-canvas {display:block;}
          .weather-scene.snowy .cloudsprite {opacity:.7}
          .weather-scene.snowy .weather-tint {opacity:.23}
          .weather-nightshade {position:absolute;inset:0;opacity:0;background:linear-gradient(155deg,rgba(10,20,49,.38),rgba(8,15,35,.24));pointer-events:none;transition:opacity .7s ease}
          .weather-scene.night .weather-nightshade {opacity:1}
          .weather-scene.night .weather-sunshine {display:none !important}
          .lightning-bolt {position:absolute;top:0;left:0;width:100%;height:100%;opacity:0;filter:drop-shadow(0 0 5px #fff) drop-shadow(0 0 15px #87bcff);pointer-events:none;}
          .weather-scene.stormy .lightning-bolt {animation:bolt-strike 5s linear infinite;}
          .weather-scene.stormy .lightning-bolt.bolt-second {animation-delay:-2.5s;}
          @keyframes bolt-strike {0%,10%,21%,23%,100%{opacity:0}11%,15%,18%,20%{opacity:1}}

          .weather-scene.rainy .weather-rain-sprite,.weather-scene.pouring .weather-rain-sprite,.weather-scene.stormy .weather-rain-sprite {display:block;}
          .weather-scene.stormy .weather-rain-sprite {opacity:1;}
          .rainfield::before,.rainfield::after {content:'';position:absolute;inset:-45% -10%;background-image:repeating-linear-gradient(105deg,transparent 0,transparent 27px,#cceaffaa 28px,#d8f5ff20 29px,transparent 31px,transparent 52px);background-size:47px 180px;animation:rain-scroll .85s linear infinite;transform:skewX(-4deg);}
          .rainfield::after {opacity:.38; background-size:63px 220px;animation-duration:1.17s}
          .weather-scene.rainy .rainfield,.weather-scene.pouring .rainfield,.weather-scene.stormy .rainfield {display:block}
          .weather-scene.stormy .rainfield {opacity:.85}
          .weather-tint {position:absolute;inset:0;opacity:0;transition:opacity 1.2s;background:linear-gradient(160deg,rgba(89,125,163,.13),rgba(19,33,55,.27));}
          .weather-scene.rainy .weather-tint {opacity:.4}
          .weather-scene.pouring .weather-tint {opacity:.62}
          .weather-scene.stormy .weather-tint {opacity:.75}
          .weather-mist {position:absolute;inset:0;opacity:0;background:linear-gradient(90deg,#c5d5db10,#e1e8e650,#bcc7cf16);filter:blur(14px);animation:mist-drift 15s ease-in-out infinite alternate}
          .weather-scene.foggy .weather-mist {opacity:.8}
          .weather-sunshine {position:absolute;inset:0;opacity:0;background:radial-gradient(ellipse 32% 34% at 32% 9%,rgba(255,247,202,.65) 0%,rgba(255,219,129,.36) 25%,rgba(255,200,100,.14) 57%,transparent 100%),linear-gradient(132deg,rgba(255,220,130,.18),transparent 60%);mix-blend-mode:screen;animation:sunshimmer 6s ease-in-out infinite alternate;}
          .weather-scene.sunny .weather-sunshine {opacity:1} .weather-scene.partlycloudy .weather-sunshine {opacity:.55}
          .weather-scene:not(.sunny):not(.partlycloudy) .weather-sunshine {display:none !important}
          .weather-lightning {position:absolute;inset:0;opacity:0;background:#eaf7ff78;animation:lightning-strike 11s linear infinite;}
          .weather-scene.stormy .weather-lightning {animation-play-state:running}
          .weather-scene:not(.stormy) .weather-lightning {display:none}
          @keyframes cloud-move {to{transform:translate(3%,1%)}}
          @keyframes rain-scroll {to{background-position:-70px 180px}}
          @keyframes mist-drift {to{transform:translateX(12%)}}
          @keyframes sunshimmer {to{opacity:.65}}
          @keyframes lightning-strike {0%,84%,85%,87%,89%,100%{opacity:0}84.2%,86.1%,88.1%{opacity:.8}}
          .error { position:absolute; inset:auto 10% 40%; text-align:center; background:var(--ha-card-background,#222); padding:10px; z-index:4; display:none; }
          @media (max-width:480px) { .metric { padding:3px 5px; border-radius:7px; font-size:9px; } }
          @media (max-width:360px) { .battery-label {top:88%;} .load-label {left:59%;top:48%;} }
          @media (prefers-reduced-motion: reduce) { .weather-rain-sprite { display:none !important; }  .solar-panel-glow .panel-wash,.solar-panel-glow .panel-border,.weather-cloud,.weather-rays,.weather-rain,.weather-flash {animation:none;} }
        </style>
        <ha-card>
          ${this.config.show_title ? `<div class="heading"></div>` : ''}
          <div class="stage">
            <img class="house" alt="Energy Manager solar home" />
            <svg class="flows" xmlns="${NS}" viewBox="0 0 ${VIEW_W} ${VIEW_H}" aria-hidden="true">
              <defs>
                <filter id="flow-glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="11"/></filter>
                <filter id="flow-small-glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3"/></filter>
                <filter id="roof-glow" x="-60%" y="-100%" width="220%" height="300%"><feGaussianBlur stdDeviation="15"/></filter>
              </defs>
              <g class="solar-panel-glow" data-solar-glow="true">
                <!-- Polygon follows the rooftop array; bounded to panel surface, not the entire roof. -->
                <polygon class="panel-wash" points="721,94 1212,117 1097,270 626,230" fill="#ffdf5a" opacity=".28"/>
                <polygon points="721,94 1212,117 1097,270 626,230" fill="none" stroke="#ffe76a" stroke-width="11" opacity=".78" filter="url(#roof-glow)"/>
                <polygon class="panel-border" points="721,94 1212,117 1097,270 626,230" fill="none" stroke="#ffe777" stroke-width="3.5" opacity=".65"/>
              </g>
              <!-- Weather glyphs are drawn entirely above / left of the roof, leaving the house untouched. -->
              <g class="weather-overlay" data-weather-effect="true" style="display:none" transform="translate(-65,-4)">
                <g data-weather-kind="sun" style="display:none">
                  <g class="weather-rays" stroke="#ffd65a" stroke-width="5" stroke-linecap="round" opacity=".72">
                    <path d="M475 101V89 M475 189V201 M431 145H419 M519 145H531 M444 114L434 104 M506 176L516 186 M506 114L516 104 M444 176L434 186" />
                  </g>
                  <circle cx="475" cy="145" r="26" fill="#ffd65a" opacity=".22" filter="url(#roof-glow)"/>
                  <circle cx="475" cy="145" r="20" fill="#ffd65a" opacity=".85"/>
                </g>
                <g data-weather-kind="cloud" style="display:none" class="weather-cloud">
                  <path d="M395 162Q392 141 415 137Q423 108 454 116Q479 93 505 123Q532 121 535 145Q562 150 555 171Q550 184 525 183H416Q394 182 395 162Z" fill="#dde6ed" stroke="#f5faff" stroke-width="3" opacity=".78"/>
                </g>
                <g data-weather-kind="rain" style="display:none">
                  <g class="weather-rain" stroke="#73c6ff" stroke-width="4" stroke-linecap="round" opacity=".9"><path d="M423 191l-11 23M455 191l-11 23M487 191l-11 23M519 191l-11 23"/></g>
                  <g class="weather-rain second" stroke="#73c6ff" stroke-width="3" stroke-linecap="round"><path d="M438 197l-9 18M469 197l-9 18M501 197l-9 18"/></g>
                </g>
                <g data-weather-kind="lightning" style="display:none"><path class="weather-flash" d="M486 186l-20 31h16l-12 32 34-43h-18z" fill="#ffe05f" stroke="#fffbcc" stroke-width="2"/></g>
                <g data-weather-kind="snow" style="display:none" fill="#c5eeff"><circle cx="415" cy="207" r="4"/><circle cx="449" cy="199" r="3"/><circle cx="482" cy="213" r="4"/><circle cx="515" cy="200" r="3"/></g>
              </g>
              ${Object.entries(ROUTES).map(([id,r])=>this._routeSvg(id,r)).join('')}
            </svg>
            <div class="weather-scene" data-weather-scene>
              <div class="weather-tint"></div><div class="weather-sunshine"></div><div class="weather-mist"></div><div class="weather-nightshade"></div>
              <img class="cloudsprite cloud1" alt="" /><img class="cloudsprite cloud2" alt="" />
              <canvas class="weather-rain-canvas" width="960" height="640" aria-hidden="true"></canvas>
              <canvas class="weather-snow-canvas" width="960" height="640" aria-hidden="true"></canvas>
              <div class="weather-lightning"></div>
              <svg class="lightning-bolt" viewBox="0 0 1536 1024" preserveAspectRatio="none" aria-hidden="true"><path d="M 620 55 L 593 160 L 640 160 L 576 290 L 612 207 L 573 207 Z" fill="#e5f4ff" stroke="#ffffff" stroke-width="8" stroke-linejoin="round"/><path d="M 620 55 L 593 160 L 640 160 L 576 290" fill="none" stroke="#9fcfff" stroke-width="20" opacity=".45"/></svg>
              <svg class="lightning-bolt bolt-second" viewBox="0 0 1536 1024" preserveAspectRatio="none" aria-hidden="true"><path d="M 1070 28 L 1035 118 L 1078 118 L 1017 250 L 1049 157 L 1015 157 Z" fill="#ebf6ff" stroke="#ffffff" stroke-width="7" stroke-linejoin="round"/></svg>
            </div>
            <div class="metric solar-label" data-label="solar">☀ Solar <strong>—</strong></div>
            <div class="metric load-label" data-label="load">⌂ House <strong>—</strong></div>
            <div class="metric battery-label" data-label="battery">▣ Battery <strong>—</strong></div>
            <div class="metric grid-label" data-label="grid">↔ Grid <strong>—</strong></div>
            <div class="metric ev-label" data-label="ev" style="display:none">⚡ EV <strong>—</strong></div>
            <div class="error">House image not found. Copy energy-flow-house.png into /config/www/.</div>
          </div>
        </ha-card>`;
      const img=this.shadowRoot.querySelector('img.house');
      img.src=this.config.image; this._displayedImage=this.config.image;
      img.onerror=()=>this.shadowRoot.querySelector('.error').style.display='block';
      img.onload=()=>this.shadowRoot.querySelector('.error').style.display='none';
      if(this.config.show_title) this.shadowRoot.querySelector('.heading').textContent=this.config.title;
      if(!this.config.show_labels) this.shadowRoot.querySelectorAll('.metric').forEach(x=>x.style.display='none');
    }
    _routeSvg(id,route) {
      const reversed = id==='battery';
      return `<g class="route inactive" data-route="${id}">
        <path d="${route.d}" class="trail" stroke="${route.color}"/>
        ${Array.from({length:5},(_,i)=>`<g>
          <circle r="13" fill="${route.color}" class="halo"/>
          <circle r="5.2" fill="${route.color}" class="particle"/>
          <circle r="2.9" fill="#ffffff" class="core"/>
          <animateMotion class="motion" dur="3s" begin="${-i*0.6}s" repeatCount="indefinite" path="${route.d}" ${reversed ? 'keyPoints="1;0" keyTimes="0;1" calcMode="linear"' : ''}/>
        </g>`).join('')}
      </g>`;
    }
    _setFlow(name,power,max,reverse=false) {
      const route=this.shadowRoot.querySelector(`[data-route="${name}"]`); if(!route) return;
      const active=power>Number(this.config.threshold_w||0);
      route.classList.toggle('inactive',!active); route.classList.toggle('active',active);
      if (!active) return;
      const fraction=Math.min(1,Math.max(0,power/Math.max(1,max)));
      const duration=(5-3.8*Math.sqrt(fraction))/Math.max(0.1,Number(this.config.animation_speed)||1);
      route.querySelectorAll('.motion').forEach((a,i)=>{
        // SVG uses reverse travel for export / discharge, forward for import / charge.
        a.setAttribute('dur',duration.toFixed(2)+'s');
        a.setAttribute('begin',(-i*duration/5).toFixed(2)+'s');
        if(name==='battery'||name==='grid') {
          a.setAttribute('keyPoints',reverse?'1;0':'0;1');
          a.setAttribute('keyTimes','0;1'); a.setAttribute('calcMode','linear');
        }
      });
    }
    _label(name,text,color) { const el=this.shadowRoot.querySelector(`[data-label="${name}"]`);if(el) {el.querySelector('strong').textContent=text;el.style.borderColor=color;} }
    _updateWeather() {
      const scene=this.shadowRoot.querySelector('[data-weather-scene]');
      if(!scene) return;
      let entity=this.config.weather_entity;
      if(!entity) {
        const keys=Object.keys(this._hass?.states||{}).filter(k=>k.startsWith('weather.'));
        entity=keys.find(k=>/bom|bureau|meteorology/i.test(k))||keys[0];
      }
      const state=String(this.config.weather_test_condition || this._hass?.states?.[entity]?.state||'').toLowerCase();
      const active=Boolean(this.config.weather_effects) && state && !['unknown','unavailable'].includes(state);
      const kind=state==='pouring'?'pouring':
        ['rainy','hail'].includes(state)?'rainy':
        ['lightning','lightning-rainy'].includes(state)?'stormy':
        ['snowy','snowy-rainy'].includes(state)?'snowy':
        ['cloudy','windy','windy-variant'].includes(state)?'cloudy':
        state==='partlycloudy'?'partlycloudy':state==='fog'?'foggy':
        state==='sunny'?'sunny':state==='clear-night'?'night':'';
      scene.className='weather-scene'+(active&&kind?' on '+kind:'');
      const cloud=(kind==='stormy'||kind==='pouring'||kind==='rainy')?this.config.weather_storm_cloud_image:this.config.weather_cloud_image;
      scene.querySelectorAll('.cloudsprite').forEach(img=>{
        if(img.getAttribute('src')!==cloud) img.setAttribute('src',cloud);
      });
      if(active && (kind==='rainy'||kind==='pouring'||kind==='stormy')) this._startRain(); else this._stopRain();
      if(active && kind==='snowy') this._startSnow(); else this._stopSnow();
      scene.style.opacity=active?Math.min(1,Math.max(0,Number(this.config.weather_intensity??1))):0;
      // Mild clouds on partly cloudy; full-screen precipitation on rainy/stormy.
      if(kind==='partlycloudy') scene.querySelector('.cloud1').style.opacity='.45';
      else scene.querySelector('.cloud1').style.removeProperty('opacity');
    }
    _stopSnow() {
      if(this._snowRaf) cancelAnimationFrame(this._snowRaf);
      this._snowRaf=0;
      const canvas=this.shadowRoot.querySelector('.weather-snow-canvas');
      if(canvas) canvas.getContext('2d')?.clearRect(0,0,canvas.width,canvas.height);
    }
    _startSnow() {
      if(this._snowRaf || !this.isConnected) return;
      const canvas=this.shadowRoot.querySelector('.weather-snow-canvas');
      if(!canvas) return;
      const ctx=canvas.getContext('2d'); if(!ctx) return;
      const w=canvas.width,h=canvas.height;
      if(!this._snowflakes.length) this._snowflakes=Array.from({length:165},()=>({x:Math.random()*w,y:Math.random()*h,r:1+Math.random()*3.1,vy:.35+Math.random()*1.45,phase:Math.random()*6.28,alpha:.48+Math.random()*.46}));
      let previous=0;
      const frame=(now)=>{
        const scene=this.shadowRoot.querySelector('[data-weather-scene]');
        if(!this.isConnected || !scene?.classList.contains('snowy')) {this._stopSnow();return;}
        const dt=Math.min(2.5,(now-(previous||now))/16.67);previous=now;
        ctx.clearRect(0,0,w,h);
        for(const f of this._snowflakes){
          f.y+=f.vy*dt;f.phase+=.012*dt;f.x+=Math.sin(f.phase)*.48*dt;
          if(f.y>h+8){f.y=-8;f.x=Math.random()*w;}
          ctx.beginPath();ctx.fillStyle=`rgba(247,252,255,${f.alpha})`;
          ctx.shadowColor='#eff9ff';ctx.shadowBlur=f.r*2.3;
          ctx.arc(f.x,f.y,f.r,0,Math.PI*2);ctx.fill();
        }
        this._snowRaf=requestAnimationFrame(frame);
      };
      this._snowRaf=requestAnimationFrame(frame);
    }
    _stopRain() {
      if(this._rainRaf) cancelAnimationFrame(this._rainRaf);
      this._rainRaf=0;
    }
    _startRain() {
      if(this._rainRaf || !this.isConnected) return;
      const canvas=this.shadowRoot.querySelector('.weather-rain-canvas');
      if(!canvas) return;
      const ctx=canvas.getContext('2d');
      if(!ctx) return;
      const w=canvas.width,h=canvas.height;
      if(!this._rainDrops.length) {
        // Full-scene rain, with depth variation and bright but fine rain streaks.
        this._rainDrops=Array.from({length:220},(_,i)=>({
          x:Math.random()*w,y:Math.random()*h,
          speed:5+Math.random()*9,len:15+Math.random()*25,
          width:.55+Math.random()*1.15,alpha:.38+Math.random()*.46,
          parallax:.7+Math.random()*.7
        }));
      }
      let last=performance.now();
      const frame=(now)=>{
        if(!this.isConnected) {this._stopRain();return;}
        const scene=this.shadowRoot.querySelector('[data-weather-scene]');
        if(!scene || !(scene.classList.contains('rainy')||scene.classList.contains('pouring')||scene.classList.contains('stormy'))) {this._stopRain();return;}
        const dt=Math.min(2.5,(now-last)/16.67);last=now;
        ctx.clearRect(0,0,w,h);
        const kind=scene.classList.contains('stormy')?'stormy':scene.classList.contains('pouring')?'pouring':'rainy';
        const intense=kind==='stormy'?1.25:kind==='pouring'?1.12:0.82;
        const visibleCount=kind==='stormy'?220:kind==='pouring'?180:70;
        ctx.lineCap='round';
        for(const d of this._rainDrops.slice(0,visibleCount)){
          d.y+=d.speed*dt*intense;d.x-=d.speed*.19*dt;
          if(d.y>h+40 || d.x< -30){d.y=-40-Math.random()*h*.3;d.x=Math.random()*(w+100);}
          const x=d.x,y=d.y,length=d.len*d.parallax;
          // Dark shadow separates each streak from light-themed backgrounds.
          ctx.beginPath();ctx.moveTo(x+length*.22,y-length);ctx.lineTo(x,y);
          ctx.strokeStyle='rgba(17,48,72,'+(d.alpha*.48)+')';ctx.lineWidth=d.width+1.15;ctx.stroke();
          ctx.beginPath();ctx.moveTo(x+length*.22,y-length);ctx.lineTo(x,y);
          ctx.strokeStyle='rgba(214,240,255,'+Math.min(.98,d.alpha*intense)+')';ctx.lineWidth=d.width;ctx.stroke();
        }
        this._rainRaf=requestAnimationFrame(frame);
      };
      this._rainRaf=requestAnimationFrame(frame);
    }
    _updateEvImage(connectorState) {
      const c=this.config;
      const brand=String(this._hass?.states?.[c.ev_brand_entity]?.state||'other').trim().toLowerCase();
      const supported=['other','byd','chery','geely','jaecoo','kia','mg','tesla','zeekr'];
      const selected=supported.includes(brand)?brand:'other';
      // OCPP Available means disconnected. Finishing and Charging mean visible vehicle.
      // Other known connected/suspended states retain the vehicle, but do not animate charging.
      const connected=['finishing','charging','preparing','suspendedev','suspendedevse','occupied'].includes(connectorState);
      const directory=String(c.ev_brands_dir||'/local/energy-flow/brands/').replace(/\/+$/,'')+'/';
      const target=connected?directory+selected+'.png':c.image;
      const requestId=(this._evRequestId||0)+1;this._evRequestId=requestId;
      if(target===this._displayedImage) return;
      const img=this.shadowRoot.querySelector('img.house');
      if(!img) return;
      // Preload before switching to avoid flashes, and fall back to master on missing assets.
      const swap=(src)=>{if(this._displayedImage===src)return;img.src=src;this._displayedImage=src;};
      if(this._failedImages.has(target)) { swap(c.image);return; }
      const pre=new Image();
      pre.onload=()=>{if(this._evRequestId===requestId)swap(target);};
      pre.onerror=()=>{this._failedImages.add(target);if(this._evRequestId===requestId)swap(c.image);};
      pre.src=target;
    }
    updateValues() {
      if(!this._hass || !this.config || !this.shadowRoot.querySelector('.stage')) return;
      const c=this.config, get=(key)=>Math.max(0,this._number(c[key]));
      const solar=get('solar_entity'), load=get('load_entity');
      const importing=get('import_entity'), exporting=get('export_entity');
      const charging=get('battery_charging_entity'), discharging=get('battery_discharging_entity');
      const netGrid=importing-exporting, netBattery=charging-discharging;
      const connectorState=String(this._hass?.states?.[c.ev_connector_entity]?.state||'available').trim().toLowerCase();
      this._updateEvImage(connectorState);
      const evCharging=connectorState==='charging';
      const amps=Math.max(0,this._number(c.ev_current_entity));
      const rawPhases=String(this._hass?.states?.[c.ev_phases_entity]?.state||'1');
      const phases=rawPhases==='3'?3:1;
      // OCPP current is assumed to be amps per phase (not summed current).
      const evWatts=evCharging?amps*230*phases:0;
      const soc=Math.max(0,Math.min(100,this._number(c.battery_level_entity)));
      const solarLimit=this._limit(c.solar_array_size_entity,10000);
      const chargeLimit=this._limit(c.battery_charge_limit_entity,10000);
      const dischargeLimit=this._limit(c.battery_discharge_limit_entity,10000);
      const exportLimit=this._limit(c.export_limit_entity,10000);
      this._label('solar',this._fmt(solar),'#f9c94d');
      this._label('load',this._fmt(load),'#65b6ff');
      this._label('battery',this._fmt(netBattery)+' · '+soc.toFixed(0)+'%'+(netBattery>30?' ↑':netBattery< -30?' ↓':''),'#43e3b6');
      this._label('grid',this._fmt(netGrid)+(netGrid>30?' import':netGrid< -30?' export':''),'#f28b52');
      const evLabel=this.shadowRoot.querySelector('[data-label="ev"]');
      if(evLabel)evLabel.style.display=c.show_labels && evCharging?'block':'none';
      this._label('ev',this._fmt(evWatts),'#66f5d1');
      const roof=this.shadowRoot.querySelector('[data-solar-glow]'); const weatherState=String(c.weather_test_condition||this._hass?.states?.[c.weather_entity]?.state||'').toLowerCase();const night=weatherState==='clear-night'; const glowEnabled=!night&&Boolean(c.solar_panel_glow)&&solar>0; if(roof){roof.classList.toggle('on',glowEnabled);roof.style.opacity=glowEnabled?Math.min(1,Math.max(.48, .4+.6*solar/Math.max(1,solarLimit))*Math.max(0,Number(c.glow_intensity??1))):0;}
      this._updateWeather();
      this._setFlow('solar',solar,solarLimit);
      this._setFlow('house',load,10000);
      this._setFlow('battery',Math.abs(netBattery),netBattery>=0?chargeLimit:dischargeLimit,netBattery<0);
      this._setFlow('grid',Math.abs(netGrid),netGrid>=0?Number(c.import_limit):exportLimit,netGrid>=0);
      this._setFlow('ev',evWatts,Number(c.ev_max_power_w)||22080);
    }
  }
  customElements.define('energy-flow-3d-card',EnergyFlow3DCard);
  window.customCards=window.customCards||[];
  window.customCards.push({type:'energy-flow-3d-card',name:'Energy Flow 3D (Experimental)',description:'Transparent house with live SVG particles'});
})();
