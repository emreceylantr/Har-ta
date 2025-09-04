/* ====== config ====== */
const API_BASE = "http://localhost:8000";
const OSRM_URL = "https://router.project-osrm.org/route/v1";

/* ====== tiny helpers ====== */
const $  = s => document.querySelector(s);
const el = id => document.getElementById(id);
const show = (n, v=true) => (n.style.display = v ? "block" : "none", n);
const toast = (m,ms=2200)=>{ const t=el("toast"); t.textContent=m; show(t); clearTimeout(t._tid); t._tid=setTimeout(()=>show(t,false),ms); };
const jget = async (u,opt)=>{ const r=await fetch(u,opt); if(!r.ok) throw new Error("net"); return r.json(); };
const toLatLng = (p)=> Array.isArray(p) ? [p[1], p[0]] : [p.lat, p.lon];
const mapLatLng = (arr)=> arr.map(toLatLng);
const on = (t,e,f)=> t.addEventListener(e,f);

/* ====== map ====== */
const map = L.map("map",{zoomControl:false}).setView([41.01,28.97],12);
L.control.zoom({position:"bottomleft"}).addTo(map);

// ⭐️ Çoklu basemap
map.createPane('labels');
map.getPane('labels').style.zIndex = 650;
map.getPane('labels').style.pointerEvents = 'none';

const baseLayers = {
  streets: L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "&copy; OpenStreetMap" }
  ),
  dark: L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    { maxZoom: 19, attribution: "&copy; OpenStreetMap, &copy; CARTO" }
  ),
  topo: L.tileLayer(
    "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    { maxZoom: 17, attribution: "Map data: &copy; OpenStreetMap, SRTM | Style: &copy; OpenTopoMap (CC-BY-SA)" }
  ),
  satellite: L.tileLayer(
    "https://{s}.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      subdomains: ["server", "services"],
      maxZoom: 19,
      attribution:
        "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
    }
  ),
  labelsLight: L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png",
    { pane: "labels", maxZoom: 19, attribution: "&copy; OpenStreetMap, &copy; CARTO" }
  ),
};
let currentBase = baseLayers.streets.addTo(map);
let currentLabels = null;

function setBasemap(mode) {
  if (currentBase) map.removeLayer(currentBase);
  if (currentLabels) { map.removeLayer(currentLabels); currentLabels = null; }

  if (mode === "hybrid") {
    currentBase = baseLayers.satellite.addTo(map);
    currentLabels = baseLayers.labelsLight.addTo(map);
  } else {
    currentBase = (baseLayers[mode] || baseLayers.streets).addTo(map);
  }
}
el("basemapSel").onchange = (e) => setBasemap(e.target.value);

const clusters = (L.markerClusterGroup ? L.markerClusterGroup({disableClusteringAtZoom:16}) : L.layerGroup()).addTo(map);
const hatLayer = L.layerGroup().addTo(map);
const stopIcon = L.divIcon({className:"stop-pin",iconSize:[24,24]});
const meIcon   = L.divIcon({className:"me-pin",  iconSize:[18,18]});

/* ====== waypoint model ====== */
const start = {input: el("startInput"), coord:null};
const dest  = {input: el("destInput"),  coord:null};
const via   = []; // { key, el, input, coord }
const wpList = el("wpList"), destItem = el("destItem");
const getPts = () => {
  const pts=[]; const push=(c)=>c&&pts.push(L.latLng(c.lat,c.lon));
  push(start.coord); via.forEach(v=>push(v.coord)); push(dest.coord);
  return pts;
};

/* ====== routing ====== */
const router = L.Routing.control({
  position:"topright", waypoints:[], collapsible:true, addWaypoints:true, draggableWaypoints:true,
  router: L.Routing.osrmv1({serviceUrl:OSRM_URL, profile:"car"})
})
.on("routesfound", e=>{
  const s=e.routes[0]?.summary||{totalDistance:0,totalTime:0};
  el("routeInfo").innerHTML=`📏 ${(s.totalDistance/1000).toFixed(2)} km · ⏱️ ${Math.round(s.totalTime/60)} dk`;
  show(el("routeInfo"), true);
})
.on("waypointschanged", e=>{
  const w=e.waypoints||[];
  if(w[0]?.latLng) start.coord={lat:w[0].latLng.lat,lon:w[0].latLng.lng};
  w.slice(1,-1).forEach((m,i)=>m?.latLng && (via[i].coord={lat:m.latLng.lat,lon:m.latLng.lng}));
  const last=w.at(-1); if(last?.latLng) dest.coord={lat:last.latLng.lat,lon:last.latLng.lng};
})
.on("routingerror", ()=>toast("Rota bulunamadı."))
.addTo(map);
const reroute = ()=>{ const pts=getPts(); if(pts.length>=2) router.setWaypoints(pts); };

/* ====== geocode ====== */
async function geocode(q){
  const m=q.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  if(m) return {lat:+m[1], lon:+m[2]};
  const j=await jget(`https://nominatim.openstreetmap.org/search?format=json&accept-language=tr&limit=1&q=${encodeURIComponent(q)}`);
  return j[0]?{lat:+j[0].lat, lon:+j[0].lon}:null;
}

/* ====== VIA rows (add/remove/drag) ====== */
const newKey = ()=>"v"+Math.random().toString(36).slice(2,8);
function addVia(value=""){
  const key=newKey();
  const rowEl=document.createElement("div"); rowEl.className="wp-item"; rowEl.dataset.key=key;
  rowEl.innerHTML=`<div class="drag" title="Sürükle"></div>
    <input type="text" class="via-input" placeholder="Ara durak (adres veya 41.0, 28.9)" value="${value}"/>
    <button class="del" title="Sil">✕</button>`;
  wpList.insertBefore(rowEl, destItem);
  const row={key, el:rowEl, input: rowEl.querySelector(".via-input"), coord:null};
  via.push(row);
  rowEl.querySelector(".del").onclick=()=>{ const i=via.findIndex(x=>x.key===key); if(i>-1){ via.splice(i,1); rowEl.remove(); reroute(); } };
  return row;
}
el("addStop").onclick=()=>addVia("");
new Sortable(wpList,{
  handle:".drag", draggable:".wp-item", animation:150,
  onEnd(){
    const order=[...wpList.children].map(x=>x.dataset.key), nv=[];
    order.forEach(k=>{ if(k!=="start" && k!=="dest"){ const f=via.find(v=>v.key===k); if(f) nv.push(f);} });
    via.splice(0,via.length,...nv); reroute();
}});

/* ====== stops (load + popup) ====== */
async function loadStops(){
  clusters.clearLayers();
  if(!el("toggleStops").checked) return;
  const b=map.getBounds(), u=new URL(API_BASE+"/stops/geojson");
  [["minLon",b.getWest()],["maxLon",b.getEast()],["minLat",b.getSouth()],["maxLat",b.getNorth()],["limit",2000]]
    .forEach(([k,v])=>u.searchParams.set(k,v));
  try{
    const g=await jget(u);
    (g.features||[]).forEach(f=>{
      if(f.geometry?.type!=="Point") return;
      const [lon,lat]=f.geometry.coordinates, name=f.properties?.name||"-";
      const sid=f.properties?.id || f.properties?.stop_id;
      const html = `
        <div>
          <div class="popup-title">${name}</div>
          <div class="lines-title">🚍 Hatlar</div>
          <div class="stop-lines" data-stop="${sid}">Yükleniyor...</div>
          <button class="popup-nav-btn" data-lat="${lat}" data-lon="${lon}" data-name="${name}" data-stop="${sid}">
            🧭 Yol tarifi al
          </button>
        </div>`;
      L.marker([lat,lon],{icon:stopIcon}).bindPopup(html).addTo(clusters);
    });
  }catch{ toast("Duraklar yüklenemedi."); }
}
on(map,"moveend",loadStops); loadStops();

on(map,"popupopen", async e=>{
  const root=e.popup.getElement(); if(!root) return;

  // Hat listesi
  const div=root.querySelector(".stop-lines");
  if(div){
    try{
      const j=await jget(`${API_BASE}/stops/${encodeURIComponent(div.dataset.stop)}/lines`);
      const arr=j.lines||[];
      div.innerHTML = arr.length
        ? `<ul class="lines-list">${arr.map(l=>`<li><b>${l.code??"-"}</b>${l.name?" – "+l.name:""}</li>`).join("")}</ul>`
        : "Bu duraktan geçen hat yok.";
    }catch{ div.textContent="Hatlar yüklenemedi."; }
  }

  // Rota + toplu taşıma önerisi
  const btn=root.querySelector(".popup-nav-btn");
  if(btn){
    btn.onclick=()=>{
      dest.input.value = btn.dataset.name || "Durak";
      dest.coord = {lat:+btn.dataset.lat, lon:+btn.dataset.lon};

      const afterStartReady = async () => {
        // kırmızı rota
        reroute(); map.closePopup();
        // mavi hat önerisi
        const fromId = await nearestStopId(start.coord.lat,start.coord.lon);
        fromId ? suggestTransit(fromId, btn.dataset.stop) : toast("Yakın durak bulunamadı.");
      };

      if("geolocation" in navigator){
        navigator.geolocation.getCurrentPosition(
          async pos=>{
            start.input.value="Konumum";
            start.coord={lat:pos.coords.latitude, lon:pos.coords.longitude};
            await afterStartReady();
          },
          async ()=>{
            const s=start.input.value.trim();
            if(s){
              const c=await geocode(s);
              if(c){ start.coord=c; await afterStartReady(); }
              else toast("Başlangıç konumu anlaşılamadı.");
            } else {
              toast("Başlangıç girin veya konumu açın.");
            }
          },
          {enableHighAccuracy:true, maximumAge:5000, timeout:10000}
        );
      } else {
        (async ()=>{
          const s=start.input.value.trim();
          if(s){
            const c=await geocode(s);
            if(c){ start.coord=c; await afterStartReady(); }
            else toast("Başlangıç konumu anlaşılamadı.");
          } else {
            toast("Başlangıç için adres girin.");
          }
        })();
      }
    };
  }
});

/* ====== controls ====== */
el("nearBtn").onclick=()=>{
  if(!("geolocation" in navigator)) return toast("Tarayıcı konumu desteklemiyor.");
  navigator.geolocation.getCurrentPosition(pos=>{
    const {latitude:lat, longitude:lon}=pos.coords;
    if(!window.meMarker) window.meMarker=L.marker([lat,lon],{icon:meIcon}).addTo(map).bindTooltip("Canlı konum");
    else window.meMarker.setLatLng([lat,lon]);
    map.setView([lat,lon],15);
  },()=>toast("Konum alınamadı."),{enableHighAccuracy:true,maximumAge:5000,timeout:10000});
};
el("toggleStops").onchange=loadStops;
el("useLoc").onclick=()=>navigator.geolocation.getCurrentPosition(pos=>{
  start.input.value="Konumum";
  start.coord={lat:pos.coords.latitude, lon:pos.coords.longitude};
  if(!window.meMarker) window.meMarker=L.marker([start.coord.lat,start.coord.lon],{icon:meIcon}).addTo(map).bindTooltip("Canlı konum");
  else window.meMarker.setLatLng([start.coord.lat,start.coord.lon]);
},()=>toast("Konum izni gerekli."));

el("drawBtn").onclick=async ()=>{
  if(!start.coord){ const s=start.input.value.trim(); if(s) start.coord=await geocode(s); }
  for (const r of via){ if(!r.coord){ const v=r.input.value.trim(); if(v) r.coord=await geocode(v); } }
  if(!dest.coord){ const d=dest.input.value.trim(); if(d) dest.coord=await geocode(d); }
  if(!start.coord || !dest.coord) return toast("Başlangıç ve varış gerekli.");
  router.setWaypoints(getPts());
};

el("clearBtn").onclick=()=>{
  start.coord=dest.coord=null; via.forEach(r=>r.coord=null);
  start.input.value=""; dest.input.value="";
  [...wpList.querySelectorAll(".wp-item")].forEach(e=>{ if(!["start","dest"].includes(e.dataset.key)) e.remove(); });
  via.splice(0); router.setWaypoints([]); show(el("routeInfo"), false); hatLayer.clearLayers();
};

/* ====== route search (hat çizimi) ====== */
el("routeSearchBtn").onclick=async ()=>{
  const q=el("routeInput").value.trim(); if(!q) return toast("Hat kodu gir.");
  hatLayer.clearLayers();
  try{
    const j=await jget(`${API_BASE}/routes/search?q=${encodeURIComponent(q)}`);
    const best=(j.results||[])[0]; if(!j.ok || !best) return toast("Hat bulunamadı.");
    const coords=mapLatLng(best.guzergah||[]);
    if(!coords.length) return toast("Bu hat için güzergah verisi yok.");
    const line=L.polyline(coords,{color:"red",weight:5,opacity:.85}).addTo(hatLayer);
    map.fitBounds(line.getBounds()); toast(`Çizildi: ${best.hat_kodu||q}`);
  }catch{ toast("Hat arama hata verdi."); }
};

/* ====== nearest stop + transit suggestion ====== */
async function nearestStopId(lat,lon){
  const d=0.02, u=new URL(API_BASE+"/stops/geojson");
  [["minLon",lon-d],["maxLon",lon+d],["minLat",lat-d],["maxLat",lat+d],["limit",1000]]
    .forEach(([k,v])=>u.searchParams.set(k,v));
  try{
    const g=await jget(u), feats=g.features||[];
    if(!feats.length) return null;
    let best=null,bestD=Infinity;
    for(const f of feats){
      const [LON,LAT]=f.geometry.coordinates;
      const dist=haversine(lat,lon,LAT,LON);
      if(dist<bestD){bestD=dist; best=f;}
    }
    return best?.properties?.id || best?.properties?.stop_id || null;
  }catch{ return null; }
}
function haversine(lat1,lon1,lat2,lon2){
  const R=6371000,toRad=d=>d*Math.PI/180, dLat=toRad(lat2-lat1), dLon=toRad(lon2-lon1);
  const a=Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(a));
}
async function suggestTransit(fromId,toId){
  try{
    const j=await jget(`${API_BASE}/routes/between?from_stop=${encodeURIComponent(fromId)}&to_stop=${encodeURIComponent(toId)}`);
    const best=(j.results||[])[0]; if(!best) return toast("Bu iki durak arasında hat bulunamadı.");
    hatLayer.clearLayers();
    const coords=mapLatLng(best.guzergah||[]);
    const line=L.polyline(coords,{color:"blue",weight:5,opacity:.8}).addTo(hatLayer);
    map.fitBounds(line.getBounds()); toast(`Toplu taşıma önerisi: ${best.hat_kodu}`);
  }catch{ toast("Hat önerisi alınamadı."); }
}
