const filters = document.querySelectorAll("[data-filter]");
const cards = document.querySelectorAll("[data-family]");
const count = document.querySelector(".sheet-count");

for (const filter of filters) {
  filter.addEventListener("click", () => {
    for (const button of filters) {
      button.setAttribute("aria-pressed", String(button === filter));
    }
    let visible = 0;
    for (const card of cards) {
      card.hidden = !!filter.dataset.filter && card.dataset.family !== filter.dataset.filter;
      visible += Number(!card.hidden);
    }
    count.textContent = `${visible} ${visible === 1 ? "sheet" : "sheets"}`;
  });
}
