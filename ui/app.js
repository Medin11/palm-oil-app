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

async function renderSuppliers() {
  const suppliers = await (await api()).get_suppliers();
  supplierList.replaceChildren(...suppliers.map(supplierCard));
  suppliersEmpty.hidden = suppliers.length > 0;
}

// ---------- Start ----------

showPage("overview");
