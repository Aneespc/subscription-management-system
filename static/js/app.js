(function () {
  const body = document.body;
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const backdrop = document.querySelector(".sidebar-backdrop");
  if (toggle) toggle.addEventListener("click", () => body.classList.toggle("sidebar-open"));
  if (backdrop) backdrop.addEventListener("click", () => body.classList.remove("sidebar-open"));

  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const variantMapEl = document.getElementById("variant-map");
  const variantMap = variantMapEl ? JSON.parse(variantMapEl.textContent) : null;

  function syncVariants(row) {
    if (!variantMap) return;
    const product = row.querySelector(".product-select");
    const variant = row.querySelector(".variant-select");
    if (!product || !variant) return;
    const productId = product.value;
    let visible = 0;
    Array.from(variant.options).forEach((option) => {
      if (!option.value) { option.hidden = false; return; }
      const match = variantMap[option.value] === productId;
      option.hidden = !match;
      if (match) visible += 1;
      if (!match && option.selected) variant.value = "";
    });
    variant.disabled = productId === "" || visible === 0;
    if (variant.disabled) variant.value = "";
  }

  function bindRow(row) {
    const product = row.querySelector(".product-select");
    if (product) {
      product.addEventListener("change", () => {
        syncVariants(row);
        const price = row.querySelector(".price-input");
        if (price) price.value = "";
      });
    }
    const variant = row.querySelector(".variant-select");
    if (variant) {
      variant.addEventListener("change", () => {
        const price = row.querySelector(".price-input");
        if (price) price.value = "";
      });
    }
    const remove = row.querySelector(".remove-row");
    if (remove) {
      remove.addEventListener("click", () => {
        const del = row.querySelector("input[type=checkbox][name$='-DELETE']");
        if (del) { del.checked = true; row.classList.add("d-none"); }
        else { row.remove(); }
        renumber();
      });
    }
    syncVariants(row);
  }

  function renumber() {
    const container = document.getElementById("formset-rows");
    const total = document.querySelector("input[name$='-TOTAL_FORMS']");
    if (!container || !total) return;
    const rows = Array.from(container.querySelectorAll(".formset-row"));
    const prefix = total.name.replace("-TOTAL_FORMS", "");
    rows.forEach((row, index) => {
      row.querySelectorAll("input, select, textarea, label").forEach((el) => {
        ["name", "id", "for"].forEach((attr) => {
          const value = el.getAttribute(attr);
          if (value && value.indexOf(prefix + "-") === 0) {
            el.setAttribute(attr, value.replace(/-(\d+)-/, "-" + index + "-"));
          }
        });
      });
    });
    total.value = rows.length;
  }

  const addButton = document.getElementById("add-row");
  const template = document.getElementById("empty-row-template");
  if (addButton && template) {
    addButton.addEventListener("click", () => {
      const total = document.querySelector("input[name$='-TOTAL_FORMS']");
      const index = parseInt(total.value, 10);
      const html = template.innerHTML.replace(/__prefix__/g, index);
      const container = document.getElementById("formset-rows");
      container.insertAdjacentHTML("beforeend", html);
      const row = container.lastElementChild;
      bindRow(row);
      total.value = index + 1;
    });
  }

  document.querySelectorAll(".formset-row").forEach(bindRow);
})();
