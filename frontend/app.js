/* ====== config ====== */
const API_BASE = "http://localhost:8000";
const OSRM_URL = "https://router.project-osrm.org/route/v1";

/* ====== dom helpers ====== */
const $  = s => document.querySelector(s);
const el = id => document.getElementById(id);
const toast = (m,ms=2200)=>{const t=el("toast");t.textContent=m;t.style.display="block";clearTimeout(t._tid);t._tid=setTimeout(()=>t.style.display="none",ms);};
const jget = async (url, opt)=>{const r=await fetch(url,opt); if(!r.ok) throw new Error("net"); return r.json();};

/* ====== map & layers ====== */
const map = L.map("map",{zoomControl:false}).setView([41.01,28.97],12);
L.control.zoom({position:"bottomleft"}).addTo(map);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);

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
  const pts=[]; if(start.coord) pts.push(L.latLng(start.coord.lat,start.coord.lon));
  via.forEach(v=>v.coord && pts.push(L.latLng(v.coord.lat,v.coord.lon)));
  if(dest.coord)  pts.push(L.latLng(dest.coord.lat,dest.coord.lon));
  return pts;
};

/* ====== routing ====== */
const router = L.Routing.control({
  position:"topright", waypoints:[], collapsible:true, addWaypoints:true, draggableWaypoints:true,
  router: L.Routing.osrmv1({serviceUrl:OSRM_URL, profile:"car"})
})
.on("routesfound", e=>{
  const s=e.routes[0].summary;
  el("routeInfo").innerHTML=`📏 ${(s.totalDistance/1000).toFixed(2)} km · ⏱️ ${Math.round(s.totalTime/60)} dk`;
  el("routeInfo").style.display="block";
})
.on("waypointschanged", e=>{
  const w=e.waypoints||[];
  if(w[0]?.latLng) start.coord={lat:w[0].latLng.lat,lon:w[0].latLng.lng};
  w.slice(1,-1).forEach((m,i)=>m?.latLng && (via[i].coord={lat:m.latLng.lat,lon:m.latLng.lng}));
  const last=w[w.length-1]; if(last?.latLng) dest.coord={lat:last.latLng.lat,lon:last.latLng.lng};
})
.on("routingerror", ()=>toast("Rota bulunamadı."))
.addTo(map);
const reroute = ()=>{const pts=getPts(); if(pts.length>=2) router.setWaypoints(pts);};

/* ====== geocode / parse ====== */
async function geocode(q){
  const m=q.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  if(m) return {lat:+m[1], lon:+m[2]};
  const j=await jget(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`);
  return j[0]?{lat:+j[0].lat, lon:+j[0].lon}:null;
}

/* ====== VIA rows (add/remove/drag) ====== */
const newKey = ()=>"v"+Math.random().toString(36).slice(2,8);
function addVia(value=""){
  const key=newKey();
  const elRow=document.createElement("div"); elRow.className="wp-item"; elRow.dataset.key=key;
  elRow.innerHTML=`<div class="drag" title="Sürükle"></div>
    <input type="text" class="via-input" placeholder="Ara durak (adres veya 41.0, 28.9)" value="${value}"/>
    <button class="del" title="Sil">✕</button>`;
  wpList.insertBefore(elRow, destItem);
  const row={key, el:elRow, input: elRow.querySelector(".via-input"), coord:null};
  via.push(row);
  elRow.querySelector(".del").onclick=()=>{const i=via.findIndex(x=>x.key===key); if(i>-1){via.splice(i,1); elRow.remove(); reroute();}};
  return row;
}
el("addStop").onclick=()=>addVia("");
new Sortable(wpList,{handle:".drag", animation:150, draggable:".wp-item", onEnd(){
  const order=[...wpList.children].map(x=>x.dataset.key), nv=[];
  order.forEach(k=>{ if(k!=="start" && k!=="dest"){ const f=via.find(v=>v.key===k); if(f) nv.push(f);} });
  via.splice(0,via.length,...nv); reroute();
}});

/* ====== stops (map) ====== */
async function loadStops(){
  clusters.clearLayers();
  if(!el("toggleStops").checked) return;
  const b=map.getBounds(), u=new URL(API_BASE+"/stops/geojson");
  u.searchParams.set("minLon",b.getWest()); u.searchParams.set("maxLon",b.getEast());
  u.searchParams.set("minLat",b.getSouth()); u.searchParams.set("maxLat",b.getNorth());
  u.searchParams.set("limit",2000);
  try{
    const g=await jget(u);
    (g.features||[]).forEach(f=>{
      if(f.geometry?.type!=="Point") return;
      const [lon,lat]=f.geometry.coordinates, name=f.properties?.name||"-";
      const sid=f.properties?.id || f.properties?.stop_id;
      const m=L.marker([lat,lon],{icon:stopIcon}).bindPopup(
        `<div>
           <div class="popup-title">${name}</div>
           <div class="lines-title">🚍 Hatlar</div>
           <div class="stop-lines" data-stop="${sid}">Yükleniyor...</div>
           <button class="popup-nav-btn" data-lat="${lat}" data-lon="${lon}" data-name="${name}" data-stop="${sid}">🧭 Yol tarifi al</button>
         </div>`
      );
      clusters.addLayer(m);
    });
  }catch{ toast("Duraklar yüklenemedi."); }
}
map.on("moveend", loadStops); loadStops();

map.on("popupopen", async e=>{
  const root=e.popup.getElement(); if(!root) return;

  // hat listesi
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

  // rota + toplu taşıma önerisi
  const btn=root.querySelector(".popup-nav-btn");
  if(btn){
    btn.onclick=()=>{
      dest.input.value = btn.dataset.name || "Durak";
      dest.coord = {lat:+btn.dataset.lat, lon:+btn.dataset.lon};
      if("geolocation" in navigator){
        navigator.geolocation.getCurrentPosition(async pos=>{
          start.input.value="Konumum";
          start.coord={lat:pos.coords.latitude, lon:pos.coords.longitude};
          reroute(); map.closePopup();
          const fromId=await nearestStopId(start.coord.lat,start.coord.lon);
          fromId ? suggestTransit(fromId, btn.dataset.stop) : toast("Yakın durak bulunamadı.");
        }, async ()=>{
          const s=start.input.value.trim();
          if(s){ start.coord=await geocode(s); reroute(); map.closePopup(); }
          else toast("Başlangıç girin veya konumu açın.");
        }, {enableHighAccuracy:true, maximumAge:5000, timeout:10000});
      } else toast("Başlangıç için adres girin.");
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
  via.splice(0); router.setWaypoints([]); el("routeInfo").style.display="none"; hatLayer.clearLayers();
};

/* ====== route search (hat çizimi) ====== */
el("routeSearchBtn").onclick=async ()=>{
  const q=el("routeInput").value.trim(); if(!q) return toast("Hat kodu gir.");
  hatLayer.clearLayers();
  try{
    const j=await jget(`${API_BASE}/routes/search?q=${encodeURIComponent(q)}`);
    const best=(j.results||[])[0]; if(!j.ok || !best) return toast("Hat bulunamadı.");
    const coords=(best.guzergah||[]).map(c=>Array.isArray(c)?[c[1],c[0]]:[c.lat,c.lon]);
    if(!coords.length) return toast("Bu hat için güzergah verisi yok.");
    const line=L.polyline(coords,{color:"red",weight:5,opacity:.85}).addTo(hatLayer);
    map.fitBounds(line.getBounds()); toast(`Çizildi: ${best.hat_kodu||q}`);
  }catch{ toast("Hat arama hata verdi."); }
};

/* ====== nearest stop + transit suggestion ====== */
async function nearestStopId(lat,lon){
  const d=0.02, u=new URL(API_BASE+"/stops/geojson");
  u.searchParams.set("minLon",lon-d); u.searchParams.set("maxLon",lon+d);
  u.searchParams.set("minLat",lat-d); u.searchParams.set("maxLat",lat+d);
  u.searchParams.set("limit",1000);
  try{
    const g=await jget(u), feats=g.features||[];
    if(!feats.length) return null;
    let best=null,bestD=1e18;
    feats.forEach(f=>{
      const [LON,LAT]=f.geometry.coordinates;
      const d=haversine(lat,lon,LAT,LON);
      if(d<bestD){bestD=d; best=f;}
    });
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
    const j=await jget(`${API_BASE}/routes/between?from=${encodeURIComponent(fromId)}&to=${encodeURIComponent(toId)}`);
    const best=(j.results||[])[0]; if(!best) return toast("Bu iki durak arasında hat bulunamadı.");
    hatLayer.clearLayers();
    const coords=(best.guzergah||[]).map(c=>Array.isArray(c)?[c[1],c[0]]:[c.lat,c.lon]);
    const line=L.polyline(coords,{color:"blue",weight:5,opacity:.8}).addTo(hatLayer);
    map.fitBounds(line.getBounds()); toast(`Toplu taşıma önerisi: ${best.hat_kodu}`);
  }catch{ toast("Hat önerisi alınamadı."); }
}
