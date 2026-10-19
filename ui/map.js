// Map page: mills, plots and sourcing areas on a Leaflet map.
// Uses helpers from app.js (api, el, formatHectares, certification badges).

const MAP_COLOURS = {
  land: "#e9e4d6",
  landBorder: "#c9c1aa",
  plot: "#4f6283",      // neutral slate blue: "not checked yet"
  mill: "#26302a",
  sourcing: "#6b746e",
};

const RISK_LABELS = {
  not_checked: "Not checked yet",
};

let map = null;
let dataLayer = null;

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

  dataLayer = L.featureGroup().addTo(map);
}

function createLegend() {
  const legend = L.control({ position: "bottomright" });
  legend.onAdd = () => {
    const box = el("div", "map-legend");
    const rows = [
      ["legend-mill", "Mill"],
      ["legend-plot", "Plot (not checked yet)"],
      ["legend-sourcing", "Plot data missing: possible sourcing area (50 km)"],
    ];
    for (const [symbolClass, label] of rows) {
      const row = el("div", "legend-row");
      row.append(el("span", `legend-symbol ${symbolClass}`), el("span", null, label));
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
    el("p", "muted", `${plot.name} · ${formatHectares(plot.area_ha)}`),
    el("p", "muted", `Risk check: ${RISK_LABELS[plot.risk_status] || plot.risk_status}`),
    certificationBadge(plot.certification)
  );
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
    L.geoJSON(plot.geometry, {
      style: { color: MAP_COLOURS.plot, weight: 2, fillColor: MAP_COLOURS.plot, fillOpacity: 0.25 },
    })
      .bindPopup(plotPopup(plot))
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
