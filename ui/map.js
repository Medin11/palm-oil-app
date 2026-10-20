// Map page: mills, plots and sourcing areas on a Leaflet map.
// Uses helpers from app.js (api, el, formatHectares, certification badges).

const MAP_COLOURS = {
  land: "#e9e4d6",
  landBorder: "#c9c1aa",
  mill: "#26302a",
  sourcing: "#6b746e",
};

// Plot colour by overall risk status. Slate blue = not checked yet.
const PLOT_COLOURS = {
  not_checked: "#4f6283",
  green: "#2e9e57",
  amber: "#e0a526",
  red: "#d0453a",
};

const FLAME_SVG =
  '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' +
  '<path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 2 1 3 2 3 0-3-1-6 1-9.5Z" ' +
  'fill="#e8590c" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';

const fireIcon = L.divIcon({ className: "fire-icon", html: FLAME_SVG, iconSize: [18, 18], iconAnchor: [9, 12] });

// Forest layers: muted grey-green for 2020 forest, pink for loss (as on Global
// Forest Watch), so they never look like the red/amber/green results.
const FOREST_STYLE = { color: "#5f7259", weight: 0.5, fillColor: "#7d8f6f", fillOpacity: 0.35 };
const LOSS_STYLE = { color: "#c2185b", weight: 1, fillColor: "#e04f8c", fillOpacity: 0.7 };

let map = null;
let dataLayer = null;
let forestLayer = null;
let lossLayer = null;

function createMap() {
  // Start centred on Ketapang. Leaflet needs a starting view before it can
  // measure shapes such as the 50 km circles.
  map = L.map("map").setView([-1.9, 110.4], 8);

  // 1. Offline background: land outline. Always available.
  //    It gets its own layer below the online tiles (Leaflet's tiles sit at 200).
  map.createPane("offlineLand").style.zIndex = 150;
  L.geoJSON(KALIMANTAN_LAND, {
    pane: "offlineLand",
    style: { color: MAP_COLOURS.landBorder, weight: 1, fillColor: MAP_COLOURS.land, fillOpacity: 1 },
    interactive: false,
    attribution: "Land outline: Natural Earth",
  }).addTo(map);

  // 2. Online detail on top, when there is internet. If tiles fail to load,
  //    the offline outline underneath stays visible.
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  L.control.scale({ imperial: false }).addTo(map);
  createLegend().addTo(map);

  // 3. Forest layers, drawn below plots and fire icons (Leaflet's shapes sit at 400).
  map.createPane("forest2020").style.zIndex = 350;
  map.createPane("forestLoss").style.zIndex = 360;
  forestLayer = L.featureGroup().addTo(map);
  lossLayer = L.featureGroup().addTo(map);
  L.control
    .layers(
      null,
      { "Forest on 31 Dec 2020 (demo)": forestLayer, "Forest loss since 2021 (demo)": lossLayer },
      { position: "topright", collapsed: false }
    )
    .addTo(map);

  dataLayer = L.featureGroup().addTo(map);
}

function createLegend() {
  const legend = L.control({ position: "bottomright" });
  legend.onAdd = () => {
    const box = el("div", "map-legend");
    const rows = [
      ["legend-plot legend-plot-red", "Plot: risk found"],
      ["legend-plot legend-plot-amber", "Plot: possible risk"],
      ["legend-plot legend-plot-green", "Plot: no risk found"],
      ["legend-plot", "Plot: not checked yet"],
      ["legend-fire", "Fire detection (last 12 months)"],
      ["legend-forest", "Forest on 31 Dec 2020"],
      ["legend-loss", "Forest loss since 2021"],
      ["legend-mill", "Mill"],
      ["legend-sourcing", "Plot data missing: possible sourcing area (50 km)"],
    ];
    for (const [symbolClass, label] of rows) {
      const row = el("div", "legend-row");
      const symbol = el("span", `legend-symbol ${symbolClass}`);
      if (symbolClass === "legend-fire") symbol.innerHTML = FLAME_SVG; // our own fixed icon, not user data
      row.append(symbol, el("span", null, label));
      box.append(row);
    }
    return box;
  };
  return legend;
}

function certificationBadge(certification) {
  return el(
    "span",
    `badge ${certificationColour(certification)}`,
    CERTIFICATION_LABELS[certification] || certification
  );
}

function plotPopup(plot) {
  const box = el("div", "map-popup");
  box.append(
    el("strong", null, plot.supplier_name),
    el("p", "muted", `${plot.name} · ${formatHectares(plot.area_ha)}`)
  );
  for (const check of CHECKS) {
    const result = plot.checks[check.type];
    const line = el("div", "popup-check");
    line.append(
      el("span", "popup-check-label", check.label),
      result ? statusLine(result.status, result.summary) : statusLine("not_checked", "Not checked yet")
    );
    box.append(line);
  }
  box.append(certificationBadge(plot.certification));
  return box;
}

function firePopup(hotspot) {
  const box = el("div", "map-popup");
  box.append(
    el("strong", null, "Fire detection"),
    el("p", "muted", formatDate(hotspot.detected_on)),
    el("p", "muted", `${hotspot.satellite} · ${hotspot.confidence} confidence`)
  );
  if (hotspot.is_demo) box.append(el("p", "muted", "Simulated fire data (demo)"));
  return box;
}

function millPopup(mill) {
  const box = el("div", "map-popup");
  const plots =
    mill.plot_count === 0 ? "Plot data missing" : mill.plot_count === 1 ? "1 plot" : `${mill.plot_count} plots`;
  box.append(
    el("strong", null, mill.name),
    el("p", "muted", mill.supplier_name),
    el("p", "muted", plots),
    certificationBadge(mill.certification)
  );
  return box;
}

async function renderMap() {
  const data = await (await api()).get_map_data();
  const hasData = data.mills.length > 0 || data.plots.length > 0;

  document.getElementById("map").hidden = !hasData;
  document.getElementById("map-empty").hidden = hasData;
  if (!hasData) return;

  if (!map) createMap();
  map.invalidateSize(); // the map was hidden, so let Leaflet re-measure it
  dataLayer.clearLayers();
  forestLayer.clearLayers();
  lossLayer.clearLayers();

  for (const geometry of data.forest_2020) {
    L.geoJSON(geometry, { pane: "forest2020", style: FOREST_STYLE, interactive: false }).addTo(forestLayer);
  }
  for (const loss of data.forest_loss) {
    L.geoJSON(loss.geometry, { pane: "forestLoss", style: LOSS_STYLE })
      .bindTooltip(`Forest loss in ${loss.year}`)
      .addTo(lossLayer);
  }

  for (const area of data.sourcing_areas) {
    L.circle([area.latitude, area.longitude], {
      radius: area.radius_km * 1000,
      color: MAP_COLOURS.sourcing,
      weight: 1.5,
      dashArray: "6 6",
      fillOpacity: 0.06,
    })
      .bindTooltip(`${area.supplier_name}: plot data missing. Possible sourcing area (${area.radius_km} km)`)
      .addTo(dataLayer);
  }

  for (const plot of data.plots) {
    const colour = PLOT_COLOURS[plot.risk_status] || PLOT_COLOURS.not_checked;
    L.geoJSON(plot.geometry, {
      style: { color: colour, weight: 2, fillColor: colour, fillOpacity: 0.3 },
    })
      .bindPopup(plotPopup(plot))
      .addTo(dataLayer);
  }

  for (const hotspot of data.hotspots) {
    L.marker([hotspot.latitude, hotspot.longitude], { icon: fireIcon })
      .bindPopup(firePopup(hotspot))
      .addTo(dataLayer);
  }

  for (const mill of data.mills) {
    L.circleMarker([mill.latitude, mill.longitude], {
      radius: 6,
      color: "#ffffff",
      weight: 2,
      fillColor: MAP_COLOURS.mill,
      fillOpacity: 1,
    })
      .bindPopup(millPopup(mill))
      .addTo(dataLayer);
  }

  map.fitBounds(dataLayer.getBounds(), { padding: [30, 30] });
}
