// Switch pages when a sidebar item is clicked.
// For now every page is empty and only shows its title.

const navItems = document.querySelectorAll(".nav-item");
const pageTitle = document.getElementById("page-title");

function showPage(button) {
  navItems.forEach((item) => item.classList.toggle("active", item === button));
  pageTitle.textContent = button.textContent.trim();
}

navItems.forEach((button) => {
  button.addEventListener("click", () => showPage(button));
});

// Start on Overview.
showPage(navItems[0]);
