const state = {
  abilities: [],
  items: [],
  selectedBonuses: [],
  facilityNames: {},
  baseWeeklyLimit: 0,
};

const elements = {
  abilityInputs: document.getElementById("ability-inputs"),
  bonusSearch: document.getElementById("bonus-search"),
  bonusOptions: document.getElementById("bonus-options"),
  selectedBonuses: document.getElementById("selected-bonuses"),
  addBonus: document.getElementById("add-bonus"),
  craftingSlots: document.getElementById("crafting-slots"),
  calculate: document.getElementById("calculate"),
  status: document.getElementById("status"),
  summarySection: document.getElementById("summary-section"),
  summaryMetrics: document.getElementById("summary-metrics"),
  facilitySummary: document.getElementById("facility-summary"),
  planSection: document.getElementById("plan-section"),
  planBody: document.getElementById("plan-body"),
  planMessage: document.getElementById("plan-message"),
  facilityBody: document.getElementById("facility-body"),
  detailSection: document.getElementById("detail-section"),
  itemSelect: document.getElementById("item-select"),
  itemDetails: document.getElementById("item-details"),
};

const FACILITY_ORDER = ["plant_plot", "fish_pond", "crafting"];

document.addEventListener("DOMContentLoaded", () => {
  elements.addBonus.addEventListener("click", handleAddBonus);
  elements.bonusSearch.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAddBonus();
    }
  });
  elements.calculate.addEventListener("click", handleCalculate);
  elements.itemSelect.addEventListener("change", () => {
    const itemId = Number(elements.itemSelect.value);
    renderItemDetails(itemId);
  });

  loadInitialData().catch((error) => {
    setStatus(`Failed to initialise optimiser: ${error.message}`, true);
  });
});

async function loadInitialData() {
  setStatus("Loading game data from GitHub…");
  const response = await fetch("/api/init");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const data = await response.json();
  state.abilities = data.abilities || [];
  state.items = data.items || [];
  state.facilityNames = data.facility_names || {};
  state.baseWeeklyLimit = data.base_weekly_limit || 0;
  renderAbilityInputs();
  renderBonusOptions();
  renderItemSelect();
  elements.detailSection.classList.remove("hidden");
  setStatus("Ready. Choose your ability levels, boosted items, and compute the plan.");
}

function renderAbilityInputs() {
  elements.abilityInputs.innerHTML = "";
  state.abilities.forEach((ability) => {
    const wrapper = document.createElement("div");
    wrapper.className = "form-row ability";

    const label = document.createElement("label");
    label.textContent = `${ability.label} level`;
    label.setAttribute("for", `ability-${ability.id}`);

    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = String(ability.max_level || 60);
    input.value = String(Math.min(ability.max_level || 0, 10));
    input.id = `ability-${ability.id}`;
    input.dataset.abilityId = String(ability.id);

    wrapper.appendChild(label);
    wrapper.appendChild(input);
    elements.abilityInputs.appendChild(wrapper);
  });
}

function renderBonusOptions() {
  elements.bonusOptions.innerHTML = "";
  const fragment = document.createDocumentFragment();
  state.items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.label = item.category ? `${item.name} (${capitalize(item.category)})` : item.name;
    fragment.appendChild(option);
  });
  elements.bonusOptions.appendChild(fragment);
}

function handleAddBonus() {
  const query = elements.bonusSearch.value.trim();
  if (!query) {
    return;
  }
  const match = findItemByName(query);
  if (!match) {
    setStatus(`No item found matching “${query}”.`, true);
    return;
  }
  addBonus(match);
  elements.bonusSearch.value = "";
}

function findItemByName(query) {
  const lower = query.toLowerCase();
  return (
    state.items.find((item) => item.name.toLowerCase() === lower) ||
    state.items.find((item) => item.name.toLowerCase().includes(lower)) ||
    null
  );
}

function addBonus(item) {
  if (state.selectedBonuses.some((entry) => entry.item_id === item.item_id)) {
    return;
  }
  if (state.selectedBonuses.length >= 4) {
    setStatus("Only four items can receive the weekly bonus.", true);
    return;
  }
  state.selectedBonuses.push({ item_id: item.item_id, name: item.name });
  updateSelectedBonuses();
}

function removeBonus(itemId) {
  state.selectedBonuses = state.selectedBonuses.filter((entry) => entry.item_id !== itemId);
  updateSelectedBonuses();
}

function updateSelectedBonuses() {
  elements.selectedBonuses.innerHTML = "";
  if (!state.selectedBonuses.length) {
    return;
  }
  const fragment = document.createDocumentFragment();
  state.selectedBonuses.forEach((entry) => {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.textContent = entry.name;

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.setAttribute("aria-label", `Remove ${entry.name}`);
    removeButton.textContent = "×";
    removeButton.addEventListener("click", () => removeBonus(entry.item_id));

    chip.appendChild(removeButton);
    fragment.appendChild(chip);
  });
  elements.selectedBonuses.appendChild(fragment);
}

function gatherAbilityLevels() {
  const inputs = elements.abilityInputs.querySelectorAll("input[data-ability-id]");
  const levels = {};
  inputs.forEach((input) => {
    const abilityId = Number(input.dataset.abilityId);
    const value = Number(input.value || 0);
    levels[abilityId] = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  });
  return levels;
}

async function handleCalculate() {
  const abilityLevels = gatherAbilityLevels();
  const craftingSlots = Math.max(1, Math.floor(Number(elements.craftingSlots.value || 1)));
  const bonusItemIds = state.selectedBonuses.map((entry) => entry.item_id);

  elements.calculate.disabled = true;
  setStatus("Calculating optimal plan…");

  try {
    const response = await fetch("/api/optimise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ability_levels: abilityLevels, bonus_item_ids: bonusItemIds, crafting_slots: craftingSlots }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    renderResults(data);
    setStatus(`Optimisation complete — status: ${data.status}`);
  } catch (error) {
    console.error(error);
    setStatus(`Failed to optimise: ${error.message}`, true);
  } finally {
    elements.calculate.disabled = false;
  }
}

function renderResults(data) {
  renderSummary(data);
  renderPlanTable(data);
}

function renderSummary(data) {
  elements.summaryMetrics.innerHTML = "";
  elements.facilitySummary.innerHTML = "";

  const metrics = [
    createMetric("Weekly Astralite limit", formatNumber(data.weekly_limit || state.baseWeeklyLimit)),
    createMetric("Ability evaluation", formatNumber(data.ability_total || 0)),
    createMetric("Weekly bonus", formatNumber(data.weekly_bonus || 0)),
    createMetric("Plant plots", formatNumber(data.plant_plots || 0)),
    createMetric("Fish ponds", formatNumber(data.fish_ponds || 0)),
    createMetric("Crafting slots", formatNumber(data.crafting_slots || 0)),
  ];
  metrics.forEach((metric) => elements.summaryMetrics.appendChild(metric));

  const facilityUsage = data.facility_usage || {};
  const capacities = data.capacities || {};
  FACILITY_ORDER.forEach((key) => {
    if (!(key in capacities)) {
      return;
    }
    const usage = facilityUsage[key] || { minutes: 0, hours: 0 };
    const capacity = capacities[key] || { minutes: 0, hours: 0 };
    const utilisation = capacity.hours ? ((usage.hours / capacity.hours) * 100).toFixed(1) : "0.0";
    const metric = createMetric(state.facilityNames[key] || key, `${formatHours(usage.hours)} / ${formatHours(capacity.hours)} hrs (${utilisation}% used)`);
    elements.facilitySummary.appendChild(metric);
  });

  elements.summarySection.classList.remove("hidden");
}

function renderPlanTable(data) {
  elements.planBody.innerHTML = "";
  const items = data.items || [];
  if (!items.length) {
    elements.planMessage.textContent = data.message || "No production items selected yet.";
    elements.planSection.classList.remove("hidden");
    elements.planBody.innerHTML = "";
    elements.facilityBody.innerHTML = "";
    return;
  }

  elements.planMessage.textContent = "";
  const fragment = document.createDocumentFragment();
  items.forEach((item) => {
    const row = document.createElement("tr");
    appendCell(row, item.name);
    appendCell(row, capitalize(item.category));
    appendCell(row, formatNumber(item.units));
    appendCell(row, formatNumber(item.astralite));
    appendCell(row, formatNumber(item.per_unit_value));

    FACILITY_ORDER.forEach((facility) => {
      const minutes = item.facility_minutes?.[facility] || 0;
      appendCell(row, formatHours(minutes / 60));
    });

    appendCell(row, item.multiplier > 1 ? "Yes" : "No");
    fragment.appendChild(row);
  });
  elements.planBody.appendChild(fragment);
  elements.planSection.classList.remove("hidden");

  const facilityUsage = data.facility_usage || {};
  const capacities = data.capacities || {};
  elements.facilityBody.innerHTML = "";
  const facilityFragment = document.createDocumentFragment();
  FACILITY_ORDER.forEach((facility) => {
    if (!(facility in capacities)) {
      return;
    }
    const usage = facilityUsage[facility] || { hours: 0 };
    const capacity = capacities[facility] || { hours: 0 };
    const usedHours = usage.hours || 0;
    const capacityHours = capacity.hours || 0;
    const utilisation = capacityHours ? ((usedHours / capacityHours) * 100).toFixed(1) : "0.0";

    const row = document.createElement("tr");
    appendCell(row, state.facilityNames[facility] || facility);
    appendCell(row, formatHours(usedHours));
    appendCell(row, formatHours(capacityHours));
    appendCell(row, `${utilisation}%`);
    facilityFragment.appendChild(row);
  });
  elements.facilityBody.appendChild(facilityFragment);
}


function renderItemSelect() {
  elements.itemSelect.innerHTML = "";
  const fragment = document.createDocumentFragment();
  state.items
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach((item) => {
      const option = document.createElement("option");
      option.value = String(item.item_id);
      option.textContent = item.name;
      fragment.appendChild(option);
    });
  elements.itemSelect.appendChild(fragment);
  if (state.items.length) {
    elements.itemSelect.value = String(state.items[0].item_id);
    renderItemDetails(state.items[0].item_id);
  }
}

function renderItemDetails(itemId) {
  const profile = state.items.find((item) => item.item_id === Number(itemId));
  if (!profile) {
    elements.itemDetails.innerHTML = "<p>Select an item to inspect.</p>";
    return;
  }
  const ability = state.abilities.find((entry) => entry.id === profile.ability_id);
  const abilityLabel = ability ? ability.label : `Ability ${profile.ability_id}`;

  const summaryLines = [
    `<p><strong>Category:</strong> ${capitalize(profile.category)} · <strong>Sale value:</strong> ${formatNumber(profile.sale_value)} Astralite</p>`,
    `<p><strong>Requirement:</strong> ${abilityLabel} level ${profile.ability_level}</p>`,
  ];

  const facilityList = formatFacilityList(profile.facility_minutes);
  if (facilityList.length) {
    summaryLines.push(`<p><strong>Per-unit facility time:</strong> ${facilityList.join(", ")}</p>`);
  } else {
    summaryLines.push("<p>No facility timing data available.</p>");
  }

  const detail = profile.detail || {};
  if (detail.category === "plant" && detail.growth_minutes) {
    summaryLines.push(
      `<p>Growth cycle: ${formatNumber(detail.growth_minutes)} minutes (~${formatHours(detail.growth_minutes / 60)} hrs) for an average yield of ${formatNumber(detail.average_yield || 0)}.</p>`
    );
  } else if (detail.category === "fish" && detail.growth_minutes) {
    summaryLines.push(
      `<p>Growth time: ${formatNumber(detail.growth_minutes)} minutes (~${formatHours(detail.growth_minutes / 60)} hrs) per fish.</p>`
    );
  } else if (detail.category === "furniture" && detail.craft_minutes) {
    summaryLines.push(
      `<p>Crafting queue time: ${formatNumber(detail.craft_minutes)} minutes (~${formatHours(detail.craft_minutes / 60)} hrs) per item.</p>`
    );
  }

  let componentsHtml = "<p>No crafting prerequisites.</p>";
  if (profile.components && profile.components.length) {
    const rows = profile.components
      .map((component) => formatComponentRow(component))
      .join("");
    componentsHtml = `
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Qty</th>
              <th>Category</th>
              <th>Plant hrs</th>
              <th>Fish hrs</th>
              <th>Craft hrs</th>
              <th>Exchange cost</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  let notesHtml = "";
  if (profile.notes && profile.notes.length) {
    const notes = profile.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
    notesHtml = `<div><h4>Notes</h4><ul>${notes}</ul></div>`;
  }

  elements.itemDetails.innerHTML = `
    <div>
      <h3>${escapeHtml(profile.name)}</h3>
      ${summaryLines.join("")}
      <h4>Components</h4>
      ${componentsHtml}
      ${notesHtml}
    </div>
  `;
}

function formatComponentRow(component) {
  const facilityMinutes = component.total_facility_minutes || {};
  const perUnitMinutes = component.facility_minutes || {};
  const notes = component.notes && component.notes.length ? component.notes.map(escapeHtml).join("; ") : "";
  const exchange = component.exchange_cost ? `${formatNumber(component.exchange_cost)} Astralite` : "—";

  const cells = [
    `<td>${escapeHtml(component.name)}</td>`,
    `<td>${formatNumber(component.quantity)}</td>`,
    `<td>${component.category ? capitalize(component.category) : "—"}</td>`,
  ];

  FACILITY_ORDER.forEach((facility) => {
    const total = facilityMinutes[facility] || 0;
    const perUnit = perUnitMinutes[facility] || 0;
    const value = total ? `${formatHours(total / 60)} hrs` : "—";
    const title = perUnit ? `Per unit: ${formatHours(perUnit / 60)} hrs` : "";
    cells.push(`<td title="${title}">${value}</td>`);
  });

  cells.push(`<td>${exchange}</td>`);
  cells.push(`<td>${notes}</td>`);
  return `<tr>${cells.join("")}</tr>`;
}

function createMetric(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "metric";
  const heading = document.createElement("h3");
  heading.textContent = label;
  const text = document.createElement("p");
  text.textContent = value;
  wrapper.appendChild(heading);
  wrapper.appendChild(text);
  return wrapper;
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value;
  row.appendChild(cell);
}

function formatFacilityList(minutesMap) {
  if (!minutesMap) {
    return [];
  }
  return FACILITY_ORDER.filter((facility) => facility in minutesMap).map((facility) => {
    const minutes = minutesMap[facility];
    return `${state.facilityNames[facility] || capitalize(facility)}: ${formatNumber(minutes)} min (${formatHours(minutes / 60)} hrs)`;
  });
}

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", Boolean(isError));
}

function capitalize(value) {
  if (!value) {
    return "";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatNumber(value) {
  const number = Number(value) || 0;
  if (Math.abs(number) >= 1000) {
    return number.toLocaleString("en-US", { maximumFractionDigits: 1 });
  }
  return number.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: number % 1 === 0 ? 0 : 2 });
}

function formatHours(value) {
  const number = Number(value) || 0;
  return number.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
