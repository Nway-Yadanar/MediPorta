#!/usr/bin/env python3
"""Build the multi-region MediRoute console with region/hub switchers + animation."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PRE = os.path.join(ROOT, "demo_data", "precomputed")
from app.regions import REGIONS

scenarios = {}
for fn in sorted(os.listdir(PRE)):
    if fn.endswith(".json"):
        scenarios[fn[:-5]] = json.load(open(os.path.join(PRE, fn)))

regions_meta = {r: {"label": c["label"], "story": c["story"],
                    "story_text": c["story_text"], "center": c["center"], "zoom": c["zoom"],
                    "hubs": [{"id": h["id"], "name": h["name"], "default": h.get("default", False)}
                             for h in c["hubs"]]}
                for r, c in REGIONS.items()}

import csv as _csv
_payloads = []
with open(os.path.join(ROOT, "data", "medical_payloads.csv")) as _f:
    for _row in _csv.DictReader(_f):
        _payloads.append({
            "item_id": _row["item_id"], "item_name": _row["item_name"],
            "category": _row.get("category", "medicine"),
            "cold_chain": str(_row.get("cold_chain", "")).upper() == "TRUE",
            "storage_temp": _row.get("storage_temp_c", ""),
            "max_transit_hours": _row.get("max_transit_hours", ""),
        })

BUNDLE = json.dumps({"scenarios": scenarios, "regions": regions_meta,
                     "payloads": _payloads}, separators=(",", ":"))

HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MediRoute — Dispatch Console</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#0b1013;--panel:#111a1f;--panel2:#16232a;--line:#22333c;--fog:#8aa0aa;
--pale:#d6e2e6;--hot:#ff5a3c;--amber:#ffb03a;--gold:#ffd24a;--go:#3fd08a;--water:#3aa0ff;
--blackout:#c94dff;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
--disp:"Space Grotesk",system-ui,sans-serif}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--ink);color:var(--pale);
font-family:var(--mono);font-size:13px;line-height:1.45}
#app{display:grid;grid-template-columns:370px 1fr 330px;height:100vh}
@media(max-width:1100px){#app{grid-template-columns:1fr;height:auto}}
.panel{background:var(--panel);border-right:1px solid var(--line);overflow-y:auto}
.panel.right{border-right:none;border-left:1px solid var(--line)}
.pad{padding:16px 18px}
h1{font-family:var(--disp);font-weight:600;font-size:18px;letter-spacing:-.02em;margin:0 0 2px;color:#fff}
.sub{color:var(--fog);font-size:11px;letter-spacing:.05em;text-transform:uppercase}
.eyebrow{color:var(--hot);font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;font-weight:600;margin-bottom:9px}
.sect{border-top:1px solid var(--line)}
.sect h2{font-family:var(--disp);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--fog);margin:0 0 10px;font-weight:600}
select{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--pale);
font-family:var(--mono);font-size:12px;padding:9px;border-radius:4px;margin-bottom:8px;cursor:pointer}
.sellbl{display:block;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--fog);margin:2px 0 4px}
optgroup{color:var(--gold);font-style:normal;font-weight:600}
option{color:var(--pale);background:var(--panel2)}
.story{font-family:var(--disp);font-size:12.5px;line-height:1.5;color:var(--pale);
border-left:2px solid var(--hot);padding:3px 0 3px 11px;margin:6px 0 2px}
.tog{display:flex;gap:6px;margin:6px 0 12px}
.tog button{flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--fog);
font-family:var(--mono);font-size:11px;padding:9px 6px;cursor:pointer;letter-spacing:.03em;
text-transform:uppercase;transition:.15s;border-radius:3px}
.tog button.on{background:var(--hot);border-color:var(--hot);color:#fff}
.tog button:hover:not(.on){border-color:var(--hot);color:var(--pale)}
.mapwrap{position:relative;height:100vh}
#map{height:100vh;min-height:520px}
@media(max-width:1100px){.mapwrap{height:58vh}}
@media(max-width:1100px){#map{height:58vh}}
.chain{list-style:none;margin:0;padding:0}
.chain li{position:relative;padding:0 0 4px 34px}
.chain .node{padding:8px 0}
.chain .dot{position:absolute;left:6px;top:13px;width:9px;height:9px;border-radius:50%;background:var(--pale);border:2px solid var(--panel);z-index:2}
.chain .seg{position:absolute;left:9px;top:22px;bottom:-4px;width:2px;background:var(--line);z-index:1}
.chain .nm{padding-left:0}
.chain .seg.road{background:var(--amber)}
.chain .seg.water{background:var(--water);background-image:repeating-linear-gradient(0deg,var(--water),var(--water) 4px,transparent 4px,transparent 8px)}
.chain .seg.transfer{background:var(--fog)}
.nm{color:#fff;font-size:12.5px}.tp{color:var(--fog);font-size:10px;letter-spacing:.07em;text-transform:uppercase}
.modepill{display:inline-block;font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;padding:1px 6px;border-radius:2px;margin-left:6px}
.modepill.water{background:rgba(58,160,255,.16);color:var(--water)}
.modepill.transfer{background:rgba(138,160,170,.16);color:var(--fog)}
.modepill.hub{background:rgba(255,210,74,.16);color:var(--gold)}
.dotc{background:var(--go)}.dotw{background:var(--water)}.dotk{background:var(--amber)}.doth{background:var(--gold)}
.cc{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:14px;margin:8px 0}
.cc.ok{border-color:rgba(63,208,138,.5)}.cc.fail{border-color:rgba(255,90,60,.6)}
.cc .row{display:flex;justify-content:space-between;align-items:baseline;margin:3px 0}
.cc .big{font-family:var(--disp);font-size:15px;color:#fff}
.mani{font-size:9.5px;letter-spacing:.2em;color:var(--hot);font-weight:600;margin-bottom:4px}
.gauge{height:6px;background:var(--ink);border-radius:3px;overflow:hidden;margin:8px 0 4px}
.gauge i{display:block;height:100%}
.verdict{font-family:var(--disp);font-size:13px;font-weight:600;margin-top:8px}
.verdict.ok{color:var(--go)}.verdict.fail{color:var(--hot)}
.reason{color:var(--fog);font-size:11px;margin-top:4px;line-height:1.5}
.fix{margin-top:10px;padding:9px 10px;background:rgba(63,208,138,.10);border:1px solid rgba(63,208,138,.4);border-radius:5px;color:var(--pale);font-size:11px;line-height:1.5}
.fix .fixh{display:block;font-family:var(--disp);font-size:9.5px;letter-spacing:.14em;color:var(--go);font-weight:600;margin-bottom:4px}
.fix b{color:var(--go)}
.play{width:100%;background:var(--gold);border:none;color:#0b1013;font-family:var(--disp);
font-weight:600;font-size:13px;padding:11px;border-radius:5px;cursor:pointer;margin-top:8px;letter-spacing:.02em}
.play:hover{filter:brightness(1.08)}.play:disabled{opacity:.5;cursor:default}
.tr{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid var(--line)}
.tr .rank{font-family:var(--disp);font-size:14px;color:var(--fog);width:24px;text-align:right}
.tr .bar{width:5px;height:26px;border-radius:2px;flex:none}
.tr .who{flex:1;min-width:0}.tr .who .n{color:#fff;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tr .who .m{color:var(--fog);font-size:10px}
.tr .delta{font-family:var(--disp);font-size:11px;font-weight:600;color:var(--go);opacity:0;transition:.5s;white-space:nowrap}
.tr .delta.show{opacity:1}.tr .bo{color:var(--blackout);font-size:12px;width:14px;text-align:center}
.legend{display:flex;flex-wrap:wrap;gap:7px 12px;margin-top:12px;color:var(--fog);font-size:10px}
.legend span{display:flex;align-items:center;gap:4px}.sw{width:9px;height:9px;border-radius:2px}
.foot{color:var(--fog);font-size:9.5px;line-height:1.6;padding:12px 18px;border-top:1px solid var(--line)}
.foot b{color:var(--pale)}
.leaflet-popup-content-wrapper{background:var(--panel);color:var(--pale);border-radius:6px}
.leaflet-popup-tip{background:var(--panel)}
.pop .pn{font-family:var(--disp);color:#fff;font-size:13px;margin-bottom:3px}
.pop .pm{color:var(--fog);font-size:11px}
.badge{display:inline-block;font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:1px 6px;border-radius:2px;margin-top:5px}
.badge.blackout{background:rgba(201,77,255,.18);color:var(--blackout)}
.og{background:rgba(201,77,255,.07);border:1px solid rgba(201,77,255,.35);border-radius:6px;padding:12px}
.og .oghd{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.og .satdish{width:15px;height:15px;border:2px solid var(--blackout);border-radius:50% 50% 50% 0;transform:rotate(-45deg)}
.og .ogt{font-family:var(--disp);font-size:13px;color:#fff}
.og .ogsub{font-size:11px;color:var(--fog);line-height:1.5;margin-bottom:8px}
.og .ogrow{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-top:1px solid rgba(201,77,255,.15);font-size:11px}
.og .ogrow .nm{color:var(--pale)}
.og .ogrow .pri{font-family:var(--disp);color:var(--blackout);font-weight:600}
.og .ogrec{margin-top:9px;font-size:10.5px;color:var(--blackout);font-family:var(--disp);letter-spacing:.04em}
.og .ognote{margin-top:6px;font-size:10px;color:var(--fog);line-height:1.5;font-style:italic}
.destbtn{display:block;width:100%;margin-top:8px;padding:6px 8px;background:var(--gold,#ffd24a);
  color:#0b1013;border:none;border-radius:4px;font-family:var(--mono);font-size:11px;font-weight:700;
  cursor:pointer;letter-spacing:.03em}
.destbtn:hover{filter:brightness(1.08)}
.liveroute{position:absolute;left:16px;bottom:16px;z-index:600;max-width:320px;display:none;
  background:rgba(17,26,31,.94);border:1px solid var(--line,#22333c);border-radius:6px;padding:10px 12px;
  font-family:var(--mono);backdrop-filter:blur(4px)}
.liveroute .lrh{font-size:9.5px;letter-spacing:.16em;color:var(--gold,#ffd24a);font-weight:600;margin-bottom:4px}
.liveroute .lrb{font-size:11px;color:var(--pale,#d6e2e6);line-height:1.5}
.liveroute .lrb b{color:#fff;font-size:14px}
.liveroute code{background:rgba(255,255,255,.08);padding:1px 4px;border-radius:3px;font-size:10px}
.badge.hub{background:rgba(255,210,74,.18);color:var(--gold)}
</style></head><body>
<div id="app">
  <aside class="panel">
    <div class="pad">
      <div class="eyebrow">MediRoute · Field Dispatch</div>
      <h1>Multi-region supply routing</h1>
      <div class="sub">Risk-weighted · multi-modal · cold-chain aware</div>
    </div>
    <div class="sect pad">
      <h2>Region &amp; supply hub</h2>
      <select id="regionSel"></select>
      <select id="hubSel"></select>
      <label class="sellbl">Deliver to</label>
      <select id="destSel"></select>
      <div class="story" id="storyBox"></div>
    </div>
    <div class="sect pad">
      <h2>Scenario</h2>
      <div class="tog" id="scenTog">
        <button data-s="normal" class="on">Normal</button>
        <button data-s="blockage">Disruption</button>
      </div>
      <h2>Payload</h2>
      <select id="paySel"></select>
      <div id="ccCard"></div>
      
    </div>
    <div class="sect pad">
      <h2>Route</h2>
      <ul class="chain" id="chain"></ul>
    </div>
    <div class="sect pad">
      <h2>Off-grid connectivity</h2>
      <div id="offgrid"></div>
    </div>
    <div class="foot">
      <b>Provenance.</b> Real: clinic locations, road topology, disease&#8594;region
      priorities, WHO cold-chain windows, blackout-township reporting, stock schema.
      Synthetic (flagged): waterway geometry, dock sites, boat speed, transfer
      penalty, per-segment cold-chain capability, conflict-proxy telecom, hub role.
    </div>
  </aside>
  <div class="mapwrap">
    <div id="map"></div>
    <div id="liveRoute" class="liveroute"></div>
  </div>
  <aside class="panel right">
    <div class="pad">
      <h2 style="font-family:var(--disp);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--fog);margin:0 0 4px">Priority queue</h2>
      <div class="sub" style="margin-bottom:8px">Who gets the truck first</div>
      <div class="tog" id="teleTog">
        <button data-t="base" class="on">Stock only</button>
        <button data-t="boost">+ Comms blackout</button>
      </div>
      <div id="triage"></div>
      <div class="legend">
        <span><i class="sw" style="background:#ffd24a"></i>hub</span>
        <span><i class="sw" style="background:#c0392b"></i>critical</span>
        <span><i class="sw" style="background:#e67e22"></i>high</span>
        <span><i class="sw" style="background:#f1c40f"></i>moderate</span>
        <span><i class="sw" style="background:#27ae60"></i>ok</span>
        <span><i class="sw" style="background:#c94dff"></i>blackout</span>
      </div>
    </div>
  </aside>
</div>
<script>
const BUNDLE=__DATA__;
const S={region:null,hub:null,scenario:"normal",payload:"MED_ORS",tele:"base"};
let SC=null;
let map=null,layers={};
try{
  map=L.map("map",{zoomControl:true,attributionControl:false}).setView([21,94],7);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {maxZoom:19,subdomains:"abcd"}).addTo(map);
  layers={clinics:L.layerGroup().addTo(map),water:L.layerGroup().addTo(map),
    route:L.layerGroup().addTo(map),vehicle:L.layerGroup().addTo(map)};
}catch(e){document.getElementById("map").innerHTML=
  '<div style="padding:40px;color:#8aa0aa;font-size:12px">Map needs internet (Leaflet CDN). Panels work offline.</div>';}
const hasMap=()=>map&&layers.clinics;
function colorFor(p){return p>=.75?"#c0392b":p>=.55?"#e67e22":p>=.35?"#f1c40f":"#27ae60";}

function initSelectors(){
  const rs=document.getElementById("regionSel");
  Object.keys(BUNDLE.regions).forEach(r=>{const o=document.createElement("option");
    o.value=r;o.textContent=BUNDLE.regions[r].label;rs.appendChild(o);});
  rs.onchange=()=>{S.region=rs.value;populateHubs();loadScenario();};
  document.getElementById("hubSel").onchange=e=>{S.hub=e.target.value;loadScenario();};
  populatePayloads();
  document.getElementById("paySel").onchange=e=>{S.payload=e.target.value;
    if(S.dest&&S.dest!=="__scenario__"){applyDestination();}else{drawChain();drawCC();}};
  document.getElementById("destSel").onchange=e=>{S.dest=e.target.value;applyDestination();};
  S.region=Object.keys(BUNDLE.regions)[0];rs.value=S.region;populateHubs();
}
function populatePayloads(){
  const ps=document.getElementById("paySel");ps.innerHTML="";
  const groups={vaccine:"Vaccines",medicine:"Medicines",test_kit:"Test kits",antivenom:"Antivenom"};
  const byCat={};
  BUNDLE.payloads.forEach(p=>{(byCat[p.category]=byCat[p.category]||[]).push(p);});
  Object.keys(groups).forEach(cat=>{
    if(!byCat[cat])return;
    const og=document.createElement("optgroup");og.label=groups[cat];
    byCat[cat].forEach(p=>{const o=document.createElement("option");o.value=p.item_id;
      o.textContent=p.item_name+(p.cold_chain?" \u00b7 "+p.storage_temp+"\u00b0C":" \u00b7 ambient");
      og.appendChild(o);});
    ps.appendChild(og);
  });
  // any leftover categories not in the ordered list
  Object.keys(byCat).forEach(cat=>{if(groups[cat])return;
    const og=document.createElement("optgroup");og.label=cat;
    byCat[cat].forEach(p=>{const o=document.createElement("option");o.value=p.item_id;
      o.textContent=p.item_name;og.appendChild(o);});ps.appendChild(og);});
  S.payload=BUNDLE.payloads[0].item_id;ps.value=S.payload;
}
function populateHubs(){
  const hs=document.getElementById("hubSel");hs.innerHTML="";
  BUNDLE.regions[S.region].hubs.forEach(h=>{const o=document.createElement("option");
    o.value=h.id;o.textContent="\u2302 "+h.name+(h.default?" (default)":"");hs.appendChild(o);});
  const hubs=BUNDLE.regions[S.region].hubs;S.hub=(hubs.find(h=>h.default)||hubs[0]).id;hs.value=S.hub;
}
function loadScenario(){
  stopAnim();SC=BUNDLE.scenarios[S.region+"__"+S.hub];
  document.getElementById("storyBox").textContent=BUNDLE.regions[S.region].story_text;
  if(hasMap()&&SC)map.setView(SC.center,SC.zoom);
  populateDest();
  drawClinics();drawWater();drawChain();drawCC();drawTriage();drawOffgrid();
}
function populateDest(){
  const ds=document.getElementById("destSel");if(!ds||!SC)return;ds.innerHTML="";
  // default option = the scenario's built-in failover clinic (the demo target)
  const def=document.createElement("option");def.value="__scenario__";
  def.textContent="\u2691 Scenario clinic (default)";ds.appendChild(def);
  // all clinics in this scenario's triage, sorted by name
  const clinics=(SC.triage||[]).slice().sort((a,b)=>a.clinic_name.localeCompare(b.clinic_name));
  clinics.forEach(c=>{const o=document.createElement("option");o.value=c.clinic_id;
    o.textContent=c.clinic_name+(c.blackout?" \u25cc":"");ds.appendChild(o);});
  S.dest="__scenario__";ds.value="__scenario__";
}
function applyDestination(){
  if(S.dest==="__scenario__"){drawChain();drawCC();return;}
  // live route to chosen clinic via API; graceful note if static file
  const box=document.getElementById("liveRoute");if(box){box.style.display="block";
    box.innerHTML='<div class="lrh">LIVE ROUTE</div><div class="lrb">Computing \u2026</div>';}
  fetch("/route",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({origin:S.hub,target:S.dest})})
    .then(r=>{if(!r.ok)throw 0;return r.json();})
    .then(d=>{
      const usesWater=(d.waypoints||[]).some(w=>w.mode_in==="water");
      if(hasMap()&&d.polyline&&d.polyline.length){layers.route.clearLayers();
        L.polyline(d.polyline,{color:usesWater?"#3aa0ff":"#ffb03a",weight:4,opacity:.95,
          dashArray:usesWater?"1 7":null}).addTo(layers.route);
        map.fitBounds(d.polyline,{padding:[60,60],maxZoom:11});}
      const nm=(SC.triage.find(c=>c.clinic_id===S.dest)||{}).clinic_name||S.dest;
      if(box)box.innerHTML='<div class="lrh">LIVE ROUTE \u00b7 '+nm+'</div><div class="lrb"><b>'
        +(d.cost_hours!=null?d.cost_hours.toFixed(1):"?")+'h</b> \u00b7 '
        +(d.distance_km!=null?d.distance_km.toFixed(0):"?")+' km'+(usesWater?' \u00b7 boat leg':' \u00b7 road')+'</div>';
      // update the CARRYING card for THIS live route + selected medicine
      drawCCLive(d.cost_hours, usesWater, nm);
    })
    .catch(()=>{if(box)box.innerHTML='<div class="lrh">LIVE ROUTE</div><div class="lrb">'
      +'Routing to any clinic needs the API running (Option 2: <code>uvicorn app.api:app</code>). '
      +'The standalone file uses the built-in scenario routes.</div>';});
}
function drawWater(){
  if(!hasMap())return;layers.water.clearLayers();
  (SC.map_layers.waterways||[]).forEach(w=>
    L.polyline([w.from,w.to],{color:"#3aa0ff",weight:2,opacity:.5,dashArray:"5 6"}).addTo(layers.water));
  (SC.map_layers.docks||[]).forEach(d=>
    L.marker([d.lat,d.lon],{icon:L.divIcon({className:"",html:
    '<div style="width:11px;height:11px;background:#3aa0ff;border:2px solid #0b1013;transform:rotate(45deg)"></div>',iconSize:[11,11]})})
    .bindPopup('<div class="pop"><div class="pn">'+d.name+'</div><div class="pm">boat transfer point</div></div>').addTo(layers.water));
}
function drawClinics(){
  if(!hasMap())return;layers.clinics.clearLayers();
  const boost=S.tele==="boost";
  SC.map_layers.clinics.forEach(c=>{
    const pr=boost?c.boosted_priority:c.base_priority;
    if(c.is_hub){
      L.marker([c.lat,c.lon],{icon:L.divIcon({className:"",html:
        '<div style="width:20px;height:20px;background:#ffd24a;border:2px solid #0b1013;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:12px;color:#0b1013;font-weight:700">\u2302</div>',iconSize:[20,20]})})
        .bindPopup('<div class="pop"><div class="pn">'+c.name+'</div><div class="pm">regional supply hub</div><span class="badge hub">\u2302 stocks &amp; dispatches</span></div>')
        .addTo(layers.clinics);return;}
    const bo=c.blackout,col=colorFor(pr),r=4+pr*7;
    const mk=L.circleMarker([c.lat,c.lon],{radius:r,fillColor:col,color:bo?"#c94dff":col,
      weight:bo?2:1,opacity:bo?1:.5,fillOpacity:.82});
    mk.bindPopup('<div class="pop"><div class="pn">'+c.name+'</div><div class="pm">priority '+pr.toFixed(2)+(c.near_water?' \u00b7 near water':'')+'</div>'
        +(bo?'<span class="badge blackout">\u25cc comms blackout</span>':'')
        +'<button class="destbtn" onclick="setDestination(\''+c.id+'\',\''+c.name.replace(/'/g,"")+'\')">\u2192 Route here</button></div>');
    mk.addTo(layers.clinics);
  });
}
// ---- destination selection: live route via API, graceful fallback if static ----
async function setDestination(clinicId,clinicName){
  if(hasMap())map.closePopup();
  const box=document.getElementById("liveRoute");
  box.style.display="block";
  box.innerHTML='<div class="lrh">LIVE ROUTE</div><div class="lrb">Computing '+S.hub+' \u2192 '+clinicName+' \u2026</div>';
  try{
    const resp=await fetch("/route",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({origin:S.hub,target:clinicId})});
    if(!resp.ok)throw new Error("api");
    const d=await resp.json();
    const usesWater=(d.waypoints||[]).some(w=>w.mode_in==="water");
    if(hasMap()&&d.polyline&&d.polyline.length){
      layers.route.clearLayers();
      L.polyline(d.polyline,{color:usesWater?"#3aa0ff":"#ffb03a",weight:4,opacity:.95,
        dashArray:usesWater?"1 7":null}).addTo(layers.route);
      map.fitBounds(d.polyline,{padding:[60,60],maxZoom:11});
    }
    box.innerHTML='<div class="lrh">LIVE ROUTE \u00b7 '+S.hub+' \u2192 '+clinicName+'</div>'
      +'<div class="lrb"><b>'+(d.cost_hours!=null?d.cost_hours.toFixed(1):"?")+'h</b> \u00b7 '
      +(d.distance_km!=null?d.distance_km.toFixed(0):"?")+' km'
      +(usesWater?' \u00b7 includes boat leg':' \u00b7 road')+'</div>';
  }catch(e){
    box.innerHTML='<div class="lrh">LIVE ROUTE</div><div class="lrb">Live routing needs the API running '
      +'(Option 2: <code>uvicorn app.api:app</code>). In the standalone file, use the region &amp; hub '
      +'switchers with the built-in scenarios.</div>';
  }
}
window.setDestination=setDestination;
function curRoute(){
  const f=SC.failover&&SC.failover[S.payload];
  if(S.scenario==="normal"){
    const legs=(SC.route_normal&&SC.route_normal.legs)||[];
    let wp=[],line=[];legs.forEach(l=>{l.waypoints.forEach(w=>wp.push(w));line=line.concat(l.polyline||[]);});
    return {waypoints:dedupe(wp),polyline:line,feasible:f?f.manifest.failure_mode==="none":true};
  }
  const bl=f?f.blockage:{};
  return {waypoints:bl.reroute_waypoints||[],polyline:bl.reroute_polyline||[],
    feasible:bl.payload_feasible,water:bl.reroute_uses_water};
}
function dedupe(wp){const o=[];let last=null;wp.forEach(w=>{if(w.id!==last)o.push(w);last=w.id;});return o;}
function drawChain(){
  const r=curRoute(),el=document.getElementById("chain");el.innerHTML="";
  r.waypoints.forEach((w,i)=>{
    const li=document.createElement("li");li.className="node";
    const isHub=w.id===S.hub;
    const dotc=isHub?"doth":w.type==="clinic"?"dotc":w.type==="dock"?"dotw":"dotk";
    const nextMode=(r.waypoints[i+1]||{}).mode_in||"road";
    const seg=i<r.waypoints.length-1?'<span class="seg '+nextMode+'"></span>':'';
    const pill=isHub?'<span class="modepill hub">hub</span>'
      :(w.mode_in==="water")?'<span class="modepill water">boat</span>'
      :(w.mode_in==="transfer")?'<span class="modepill transfer">transfer</span>':'';
    li.innerHTML='<span class="dot '+dotc+'"></span>'+seg+'<div class="nm">'+w.name+pill+'</div><div class="tp">'
      +(isHub?"supply hub":w.type.replace("_"," "))+'</div>';el.appendChild(li);
  });
  if(hasMap()){
    layers.route.clearLayers();const line=r.polyline;
    if(line.length){L.polyline(line,{color:r.water?"#3aa0ff":"#ffb03a",weight:4,opacity:.9,
      dashArray:r.water?"1 7":null}).addTo(layers.route);map.fitBounds(line,{padding:[60,60],maxZoom:11});}
    r.waypoints.forEach(w=>{if(w.lat)L.circleMarker([w.lat,w.lon],{radius:5,fillColor:"#fff",color:"#0b1013",weight:2,fillOpacity:1}).addTo(layers.route);});
  }
}
function stopAnim(){}
function drawCC(){
  const f=SC.failover&&SC.failover[S.payload];
  if(!f){document.getElementById("ccCard").innerHTML="";return;}
  const m=f.manifest,r=curRoute();
  const hrs=S.scenario==="normal"?m.normal_route_h:m.blockage_route_h;
  const margin=S.scenario==="normal"?m.normal_margin_h:m.blockage_margin_h;
  const win=f.max_transit_hours,ok=r.feasible;
  const pct=hrs!=null?Math.min(100,(hrs/win)*100):0;
  // WHO passive cold box holds 2-8C for days without power -> extends the safe
  // out-of-fridge window. If the boat leg fails cold chain but the route time
  // fits a cold-box-extended window, the fix is real and deployable.
  const COLDBOX_WINDOW_H=72;  // conservative WHO cold-box hold time (real)
  let verdict,reason,fix="";
  if(ok){verdict="\u2713 delivers in time, cold chain intact";reason="Arrives with "+margin+"h to spare, within the "+win+"h window.";}
  else if(m.failure_mode==="cold_chain_break"){
    verdict="\u2715 arrives in time \u2014 but spoiled";
    reason="Route is "+(hrs!=null?hrs.toFixed(1):"?")+"h (inside "+win+"h), but "+f.item_name+" needs "+f.storage_temp+"\u00b0C and the open boat leg can't hold cold chain.";
    if(hrs!=null&&hrs<=COLDBOX_WINDOW_H){
      fix='<div class="fix"><span class="fixh">\u2713 RECOMMENDED FIX</span>'
        +'Load a WHO passive cold box (holds '+f.storage_temp+'\u00b0C for ~'+COLDBOX_WINDOW_H+'h without power). '
        +'The boat leg is only '+(hrs!=null?hrs.toFixed(1):"?")+'h \u2014 well inside that window. '
        +'<b>With a cold box, this delivery becomes feasible.</b></div>';
    }
  }
  else{verdict="\u2715 can't reach in time";reason="Window "+win+"h exceeded or clinic isolated after disruption.";}
  const el=document.getElementById("ccCard");el.className="cc "+(ok?"ok":"fail");
  el.innerHTML='<div class="mani">CARRYING</div>'
    +'<div class="row"><span class="big">'+f.item_name+'</span><span class="tp">'+(f.cold_chain?f.storage_temp+"\u00b0C":"ambient")+'</span></div>'
    +'<div class="row"><span class="tp">must arrive within</span><span class="tp" style="color:var(--pale)">'+win+'h</span></div>'
    +'<div class="row"><span class="tp">this route</span><span class="tp" style="color:var(--pale)">'+(hrs!=null?hrs.toFixed(1)+"h":"\u2014")+'</span></div>'
    +'<div class="row"><span class="tp">margin</span><span class="tp" style="color:'+((margin==null||margin>=0)?"var(--go)":"var(--hot)")+'">'+(margin!=null?(margin>=0?"+":"")+margin+"h":"\u2014")+'</span></div>'
    +'<div class="gauge"><i style="width:'+pct+'%;background:'+(ok?"#3fd08a":"linear-gradient(90deg,#ffb03a,#ff5a3c)")+'"></i></div>'
    +'<div class="verdict '+(ok?"ok":"fail")+'">'+verdict+'</div><div class="reason">'+reason+'</div>'+fix;
}
function drawCCLive(hrs, usesWater, destName){
  // CARRYING card for a live custom-destination route + selected medicine.
  const p=BUNDLE.payloads.find(x=>x.item_id===S.payload);if(!p)return;
  let win=parseFloat(p.max_transit_hours);
  const cold=(p.cold_chain===true||String(p.cold_chain).toUpperCase()==="TRUE");
  if(isNaN(win))win=cold?48:720;
  const COLDBOX_WINDOW_H=72;
  // feasible if within window AND (not cold, OR route doesn't break cold chain on water)
  const withinTime=hrs!=null&&hrs<=win;
  const coldBreak=cold&&usesWater;
  const ok=withinTime&&!coldBreak;
  const margin=hrs!=null?+(win-hrs).toFixed(1):null;
  const pct=hrs!=null?Math.min(100,(hrs/win)*100):0;
  let verdict,reason,fix="";
  // A WHO passive cold box holds 2-8C for ~72h without power. So it rescues ANY
  // cold-chain failure where the route fits inside that 72h window -- whether the
  // failure is a boat leg breaking cold chain, or the item's own short window
  // being exceeded. Show the recommendation consistently in every such case.
  const coldBoxWouldHelp = cold && hrs!=null && hrs<=COLDBOX_WINDOW_H && !ok;
  const coldboxFix =
    '<div class="fix"><span class="fixh">\u2713 RECOMMENDED FIX</span>'
    +'Load a WHO passive cold box (holds 2\u20138\u00b0C for ~'+COLDBOX_WINDOW_H+'h without power). '
    +'This route is '+(hrs!=null?hrs.toFixed(1):"?")+'h \u2014 inside the cold-box window. '
    +'<b>With a cold box, this delivery becomes feasible.</b></div>';
  if(ok){verdict="\u2713 delivers in time, cold chain intact";reason="Arrives with "+margin+"h to spare, within the "+win+"h window.";}
  else if(coldBreak&&withinTime){
    verdict="\u2715 arrives in time \u2014 but spoiled";
    reason="Route is "+hrs.toFixed(1)+"h (inside "+win+"h), but "+p.item_name+" needs "+p.storage_temp+"\u00b0C and the open boat leg can't hold cold chain.";
    if(coldBoxWouldHelp)fix=coldboxFix;
  }
  else{
    verdict="\u2715 can't reach in time";
    reason="Route is "+(hrs!=null?hrs.toFixed(1):"?")+"h, past the "+win+"h window for "+p.item_name+".";
    if(coldBoxWouldHelp)fix=coldboxFix;
  }
  const dnote='<div class="reason" style="margin-top:6px;font-style:italic;opacity:.8">Live route on the current network. Bridge-blockage failover is modelled for the default scenario clinic.</div>';
  const el=document.getElementById("ccCard");el.className="cc "+(ok?"ok":"fail");
  el.innerHTML='<div class="mani">CARRYING \u00b7 '+(destName||"")+'</div>'
    +'<div class="row"><span class="big">'+p.item_name+'</span><span class="tp">'+(cold?p.storage_temp+"\u00b0C":"ambient")+'</span></div>'
    +'<div class="row"><span class="tp">must arrive within</span><span class="tp" style="color:var(--pale)">'+win+'h</span></div>'
    +'<div class="row"><span class="tp">this route</span><span class="tp" style="color:var(--pale)">'+(hrs!=null?hrs.toFixed(1)+"h":"\u2014")+'</span></div>'
    +'<div class="row"><span class="tp">margin</span><span class="tp" style="color:'+((margin==null||margin>=0)?"var(--go)":"var(--hot)")+'">'+(margin!=null?(margin>=0?"+":"")+margin+"h":"\u2014")+'</span></div>'
    +'<div class="gauge"><i style="width:'+pct+'%;background:'+(ok?"#3fd08a":"linear-gradient(90deg,#ffb03a,#ff5a3c)")+'"></i></div>'
    +'<div class="verdict '+(ok?"ok":"fail")+'">'+verdict+'</div><div class="reason">'+reason+'</div>'+fix+dnote;
}
function drawTriage(){
  const boost=S.tele==="boost";
  // Stock only = pure days-of-stock, lowest first (most urgent).
  // + Comms blackout = telecom-boosted priority (blackout clinics rise).
  const list=SC.triage.slice().sort((a,b)=>{
    if(boost){
      // boosted_priority is saturated in the data, so order explicitly:
      // 1) blackout clinics first (they can't call -> we push to them)
      // 2) then by urgency (lowest days-of-stock first)
      if(a.blackout!==b.blackout)return a.blackout?-1:1;
      return a.days_of_stock-b.days_of_stock;
    }
    // Stock only: pure days-of-stock, lowest first.
    return a.days_of_stock-b.days_of_stock;
  });
  const el=document.getElementById("triage");el.innerHTML="";
  list.slice(0,15).forEach((t,i)=>{
    const pr=boost?t.boosted_priority:t.base_priority,moved=boost&&t.rank_delta>0;
    const d=document.createElement("div");d.className="tr";
    // in blackout mode, show WHY a clinic ranks where it does: blackout clinics
    // get a priority boost, so a blackout clinic can outrank one with less stock.
    const meta=boost&&t.blackout
      ? t.top_item+' \u00b7 '+t.days_of_stock+'d \u00b7 <span style="color:var(--blackout)">blackout boost</span>'
      : t.top_item+' \u00b7 '+t.days_of_stock+'d stock';
    d.innerHTML='<div class="rank">'+(i+1)+'</div><div class="bar" style="background:'+colorFor(pr)+'"></div>'
      +'<div class="bo">'+(t.blackout?"\u25cc":"")+'</div>'
      +'<div class="who"><div class="n">'+t.clinic_name+'</div><div class="m">'+meta+'</div></div>'
      +'<div class="delta'+(moved?" show":"")+'">'+(moved?"\u25b2"+t.rank_delta:"")+'</div>';el.appendChild(d);
  });
}
function drawOffgrid(){
  const el=document.getElementById("offgrid");if(!el)return;
  // off-grid = blackout clinics: cut off from the network, can't call for resupply.
  // The system recommends satellite (Starlink) deployment for the highest-priority ones.
  const bo=SC.triage.filter(t=>t.blackout)
    .sort((a,b)=>b.boosted_priority-a.boosted_priority);
  if(!bo.length){el.innerHTML='<div class="og"><div class="ogsub">No comms-blackout clinics in this hub\u2019s service area.</div></div>';return;}
  const top=bo.slice(0,4);
  let rows="";
  top.forEach(t=>{rows+='<div class="ogrow"><span class="nm">\u25cc '+t.clinic_name+'</span>'
    +'<span class="pri">P '+t.boosted_priority.toFixed(2)+'</span></div>';});
  el.innerHTML='<div class="og">'
    +'<div class="oghd"><span class="satdish"></span><span class="ogt">'+bo.length+' clinics off the network</span></div>'
    +'<div class="ogsub">These clinics are in comms-blackout townships \u2014 no phone or internet. '
    +'They physically cannot call for resupply, so a reactive system never hears from them.</div>'
    +rows
    +'<div class="ogrec">\u2192 RECOMMEND: satellite terminal (Starlink) deployment</div>'
    +'<div class="ognote">MediRoute recommends where off-grid connectivity is most needed \u2014 '
    +'it does not provide the link. Blackout data: Access Now / #KeepItOn / Myanmar Shutdown Tracker.</div>'
    +'</div>';
}
function tog(id,key,dkey,cb){document.querySelectorAll("#"+id+" button").forEach(b=>{
  b.onclick=()=>{document.querySelectorAll("#"+id+" button").forEach(x=>x.classList.remove("on"));
    b.classList.add("on");S[key]=b.dataset[dkey];cb();};});}
tog("scenTog","scenario","s",()=>{stopAnim();
  if(S.dest&&S.dest!=="__scenario__"){applyDestination();}else{drawChain();drawCC();}});
tog("teleTog","tele","t",()=>{drawClinics();drawTriage();});
initSelectors();loadScenario();
</script></body></html>"""

html = HTML.replace("__DATA__", BUNDLE)
out = os.path.join(ROOT, "demo_data", "index.html")
with open(out, "w") as f:
    f.write(html)
print("wrote", out, f"{os.path.getsize(out)} bytes  ({len(scenarios)} scenarios)")
