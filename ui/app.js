// ---------- Page switching ----------

const navItems = document.querySelectorAll(".nav-item");
const pages = document.querySelectorAll(".page");

function showPage(name) {
  navItems.forEach((item) => item.classList.toggle("active", item.dataset.page === name));
  pages.forEach((page) => (page.hidden = page.dataset.page !== name));
  if (name === "suppliers") renderSuppliers();
  if (name === "map") renderMap(); // defined in map.js
}

navItems.forEach((button) => {
  button.addEventListener("click", () => showPage(button.dataset.page));
});

// ---------- Helpers ----------

// The Python functions become available a moment after the page loads.
const apiReady = new Promise((resolve) => {
  if (window.pywebview && window.pywebview.api) resolve();
  else window.addEventListener("pywebviewready", resolve, { once: true });
});

async function api() {
  await apiReady;
  return window.pywebview.api;
}

// Build an element with a class and text. Using textContent (not innerHTML)
// means names from imported files can never break the page.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const CERTIFICATION_LABELS = {
  "RSPO+ISPO": "RSPO + ISPO",
  RSPO: "RSPO",
  ISPO: "ISPO",
  none: "No certification",
};

// Both certificates = green, one = yellow, none = red.
function certificationColour(certification) {
  if (certification === "RSPO+ISPO") return "badge-green";
  if (certification === "RSPO" || certification === "ISPO") return "badge-amber";
  return "badge-red";
}

function formatHectares(value) {
  return `${Math.round(value).toLocaleString("en-GB")} ha`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-09-14" or "2026-09-14T10:05:00" -> "14 Sep 2026"
function formatDate(isoText) {
  const [year, month, day] = isoText.slice(0, 10).split("-").map(Number);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

// 1 -> "1 fire", 3 -> "3 fires"
function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

// A small coloured dot plus plain text, e.g. (amber) "Fires detected nearby".
function statusLine(status, text) {
  const line = el("span", "status-line");
  line.append(el("span", `status-dot status-${status}`), el("span", null, text));
  return line;
}

// ---------- Overview: load example data ----------

const loadButton = document.getElementById("load-example");
const loadStatus = document.getElementById("load-status");
const viewSuppliersButton = document.getElementById("view-suppliers");

loadButton.addEventListener("click", async () => {
  loadButton.disabled = true;
  loadStatus.textContent = "Loading…";
  try {
    const result = await (await api()).load_example_data();
    loadStatus.textContent = `${result.suppliers_loaded} suppliers loaded`;
    viewSuppliersButton.hidden = false;
  } catch (error) {
    loadStatus.textContent = "Could not load the example data.";
    console.error(error);
  } finally {
    loadButton.disabled = false;
  }
});

viewSuppliersButton.addEventListener("click", () => showPage("suppliers"));

// ---------- Suppliers page ----------

const supplierList = document.getElementById("supplier-list");
const suppliersEmpty = document.getElementById("suppliers-empty");

function supplierCard(supplier) {
  const card = el("article", "card supplier-card");

  const header = el("div", "supplier-header");
  header.append(el("h2", null, supplier.name));
  if (supplier.is_demo) header.append(el("span", "tag", "Demo"));
  card.append(header);

  card.append(el("p", "muted", supplier.mill_name ? `Mill: ${supplier.mill_name}` : "No mill added"));

  card.append(fireRiskSection(supplier.fire));

  const footer = el("div", "supplier-footer");
  if (supplier.plot_count > 0) {
    const plots = supplier.plot_count === 1 ? "1 plot" : `${supplier.plot_count} plots`;
    footer.append(el("span", null, `${plots} · ${formatHectares(supplier.total_area_ha)}`));
  } else {
    footer.append(el("span", "tag", "Plot data missing"));
  }

  footer.append(
    el(
      "span",
      `badge ${certificationColour(supplier.certification)}`,
      CERTIFICATION_LABELS[supplier.certification] || supplier.certification
    )
  );
  card.append(footer);

  return card;
}

// FIRE RISK                Details
// (dot) Fires detected nearby
// ...with a hidden details list underneath.
function fireRiskSection(fire) {
  const section = el("div", "risk-section");
  const header = el("div", "risk-header");
  header.append(el("span", "risk-label", "Fire risk"));
  section.append(header);

  if (!fire) {
    section.append(statusLine("not_checked", "Not checked yet"));
    return section;
  }

  const detailsButton = el("button", "link-button details-button", "Details");
  header.append(detailsButton);
  section.append(statusLine(fire.status, fire.summary));

  const details = el("ul", "risk-details");
  details.hidden = true;
  for (const result of fire.results) details.append(fireDetailItem(result));

  detailsButton.addEventListener("click", () => {
    details.hidden = !details.hidden;
    detailsButton.textContent = details.hidden ? "Details" : "Hide details";
  });

  section.append(details);
  return section;
}

function fireDetailItem(result) {
  const d = result.details;
  const item = el("li");
  const heading = el("div", "detail-heading");
  heading.append(el("strong", null, result.place_name), statusLine(result.status, result.summary));
  item.append(heading);

  let count;
  if (result.is_mill) {
    count = d.fires_in_sourcing_area
      ? `${plural(d.fires_in_sourcing_area, "fire")} within ${d.radius_km} km of the mill`
      : `No fires within ${d.radius_km} km of the mill`;
  } else if (d.fires_on_plot) {
    count = `${plural(d.fires_on_plot, "fire")} on the plot`;
  } else if (d.fires_nearby) {
    count = `${plural(d.fires_nearby, "fire")} within ${d.nearby_km} km`;
  } else {
    count = `No fires within ${d.nearby_km} km`;
  }
  item.append(el("p", "muted", count));

  const nearest =
    d.nearest_km === null
      ? "No fires detected in the last 12 months"
      : `Nearest fire: ${d.nearest_km === 0 ? "on the plot" : `${d.nearest_km} km away`}, ` +
        `${formatDate(d.nearest_date)} (${d.nearest_satellite})`;
  item.append(el("p", "muted", nearest));
  return item;
}

const checkInfo = document.getElementById("check-info");
const runChecksButton = document.getElementById("run-checks");

function showCheckInfo(lastCheck) {
  if (!lastCheck.checked_at) {
    checkInfo.textContent = "Not checked yet. Click “Check suppliers” to screen for fire risk.";
    return;
  }
  const time = lastCheck.checked_at.slice(11, 16);
  const source = lastCheck.uses_demo_data ? " · Simulated fire data (demo)" : "";
  checkInfo.textContent = `Last checked ${formatDate(lastCheck.checked_at)}, ${time}${source}`;
}

runChecksButton.addEventListener("click", async () => {
  runChecksButton.disabled = true;
  checkInfo.textContent = "Checking…";
  try {
    showCheckInfo(await (await api()).run_checks());
    await renderSuppliers();
  } catch (error) {
    checkInfo.textContent = "The check could not be completed.";
    console.error(error);
  } finally {
    runChecksButton.disabled = false;
  }
});

async function renderSuppliers() {
  const pywebviewApi = await api();
  const [suppliers, lastCheck] = await Promise.all([pywebviewApi.get_suppliers(), pywebviewApi.get_last_check()]);
  supplierList.replaceChildren(...suppliers.map(supplierCard));
  suppliersEmpty.hidden = suppliers.length > 0;
  runChecksButton.hidden = suppliers.length === 0;
  checkInfo.hidden = suppliers.length === 0;
  showCheckInfo(lastCheck);
}

// ---------- Start ----------

showPage("overview");
