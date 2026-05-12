const fields = [
  "date",
  "check_days",
  "check_dates",
  "check_times",
  "borough_ids",
  "facility_type_ids"
];

const statusEl = document.querySelector("#status");
const progressLogEl = document.querySelector("#progressLog");
const progressLinesEl = document.querySelector("#progressLines");
const progressScrollbarThumbEl = document.querySelector("#progressScrollbarThumb");
const summaryEl = document.querySelector("#summary");
const resultsEl = document.querySelector("#results");
const checkNowButton = document.querySelector("#checkNowButton");
const dateEl = document.querySelector("#date");
const dayButtonsEl = document.querySelector("#dayButtons");
const checkDatesEl = document.querySelector("#check_dates");
const checkTimesEl = document.querySelector("#check_times");
const timeButtons = Array.from(document.querySelectorAll(".time-button"));
const boroughEl = document.querySelector("#borough_ids");
const siteIdsEl = document.querySelector("#site_ids");
const facilityTypeEl = document.querySelector("#facility_type_ids");
const facilityTypeButtons = Array.from(document.querySelectorAll(".facility-type-button"));

const locationData = window.locationData || { boroughs: [], sites: [] };
const defaultLocations = Array.isArray(locationData.sites) ? locationData.sites : [];
// Pinned boroughs sort before the rest. The star state is selection, not pinning.
const pinnedBoroughIds = ["7", "5", "3", "1", "15", "19"];
const progressLines = [];
let locationFilterButtons = [];

function configFromForm() {
  const value = (id) => document.querySelector(`#${id}`).value;
  return {
    date: value("date"),
    check_days: Number(value("check_days")),
    check_dates: selectedDates(),
    check_times: selectedTimes(),
    time_window_hours: 1,
    borough_ids: selectedBoroughs(),
    facility_type_ids: selectedFacilityTypes(),
    site_ids: selectedLocations().map((location) => location.site_id).filter(Boolean),
    site_names: selectedLocations().map((location) => location.site).filter(Boolean),
    sort_column: "facility.name",
    open_when_found: false
  };
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function postJsonStream(url, body, onEvent) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  if (!response.body) return response.json();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      onEvent(event);
      if (event.type === "result") finalResult = event.result;
      if (event.type === "error") throw new Error(event.message);
    }

    if (done) break;
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer);
    onEvent(event);
    if (event.type === "result") finalResult = event.result;
    if (event.type === "error") throw new Error(event.message);
  }

  return finalResult;
}

function renderResults(results) {
  const list = Array.isArray(results) ? results : [results];
  resultsEl.replaceChildren();
  const availableCount = list.reduce((total, result) => total + (result.available_count || 0), 0);
  summaryEl.textContent = `${availableCount} reservable slot${availableCount === 1 ? "" : "s"} from latest grid check.`;

  for (const result of list) {
    const item = document.createElement("article");
    item.className = `result ${result.status}`;
    const slots = Array.isArray(result.slots) ? result.slots : [];
    item.innerHTML = `
      <h3>${result.status.toUpperCase()} · ${formatQueryLabel(result)} · ${result.checked_at}</h3>
      <p>${result.available_count || 0} reservable in time window, ${result.record_count || 0} returned by API</p>
      ${result.error ? `<p>${escapeHtml(result.error)}</p>` : ""}
      ${renderSlots(slots)}
      <a class="official-link" href="${result.search_url}" target="_blank" rel="noreferrer">Open official search</a>
    `;
    resultsEl.appendChild(item);
  }
}

function renderSiteMap(slot) {
  return `
    <iframe
      class="facility-map-frame"
      title="Google map for ${escapeHtml(slot.site)}"
      src="${googleMapEmbedUrl(slot)}"
      loading="lazy"
      referrerpolicy="no-referrer-when-downgrade"
      allowfullscreen
    ></iframe>
  `;
}

function formatQueryLabel(result) {
  const dates = Array.isArray(result.query_dates) && result.query_dates.length
    ? result.query_dates
    : [result.query_date].filter(Boolean);
  const start = dates.length > 1
    ? `${formatDateLabel(dates[0])} to ${formatDateLabel(dates[dates.length - 1])}`
    : formatDateLabel(dates[0] || "");
  const times = Array.isArray(result.query_times) && result.query_times.length
    ? result.query_times
    : [result.query_time].filter(Boolean);
  return `${start} at ${times.join(", ")} (${times.length} x 1h)`;
}

function renderSlots(slots) {
  if (!slots.length) return `<p>No reservable slots found.</p>`;
  const groups = groupSlotsByLocation(slots);

  return `
    <div class="slots">
      ${groups.map((locationGroup) => `
        <section class="location-slot-group">
          <h4>${escapeHtml(locationGroup.site)}</h4>
          <p>${escapeHtml(locationGroup.borough)}</p>
          ${locationGroup.hourGroups.map((hourGroup) => `
            <section class="slot-group">
              <h5>${escapeHtml(formatHourHeading(hourGroup.hour))}</h5>
              ${hourGroup.slots.map((slot) => `
                <div class="slot-row">
                  <div>
                    <strong>${escapeHtml(formatCourtLabel(slot))}</strong>
                    <span>${escapeHtml(slot.facility)}</span>
                    <small>${formatPrice(slot.price)} | schedule ${escapeHtml(slot.facility_schedule_id)} | ${escapeHtml(formatSlotHour(slot))}</small>
                  </div>
                  <div class="slot-actions">
                    <a href="${slot.reservation_url}" target="_blank" rel="noreferrer">Reserve</a>
                  </div>
                </div>
              `).join("")}
            </section>
          `).join("")}
        </section>
      `).join("")}
    </div>
  `;
}

function formatSlotHour(slot) {
  const start = new Date(slot.start);
  return start.toLocaleTimeString("en-CA", { hour: "numeric" }).toLowerCase().replace(/\s/g, " ");
}

function groupSlotsByLocation(slots) {
  const groups = new Map();
  for (const slot of slots) {
    const key = slot.site_id ? `site-id:${slot.site_id}` : `site-name:${slot.site}`;
    if (!groups.has(key)) {
      groups.set(key, {
        site: slot.site,
        borough: slot.borough,
        firstSlot: slot,
        slots: [],
      });
    }
    groups.get(key).slots.push(slot);
  }

  return Array.from(groups.values())
    .sort((left, right) => String(left.site).localeCompare(String(right.site)))
    .map((group) => ({
      ...group,
      hourGroups: groupSlotsByHour(group.slots),
    }));
}

function groupSlotsByHour(slots) {
  const groups = new Map();
  for (const slot of slots) {
    const hour = slot.hour || slot.start;
    if (!groups.has(hour)) groups.set(hour, []);
    groups.get(hour).push(slot);
  }

  return Array.from(groups, ([hour, groupedSlots]) => ({
    hour,
    slots: groupedSlots.sort(compareSlotsByCourt),
  })).sort((left, right) => String(left.hour).localeCompare(String(right.hour)));
}

function compareSlotsByCourt(left, right) {
  const leftCourt = left.court_number ?? 10000;
  const rightCourt = right.court_number ?? 10000;
  return leftCourt - rightCourt || String(left.facility).localeCompare(String(right.facility));
}

function formatHourHeading(hour) {
  const startDate = new Date(hour);
  const date = startDate.toLocaleDateString("en-CA", { weekday: "long", month: "short", day: "numeric" });
  const startTime = startDate.toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit" });
  return `${date} ${startTime}`;
}

function formatDateLabel(dateValue) {
  if (!dateValue) return "";
  const date = dateFromInputValue(dateValue);
  return date.toLocaleDateString("en-CA", { weekday: "long", month: "short", day: "numeric" });
}

function formatDayButtonLabel(dateValue) {
  const date = dateFromInputValue(dateValue);
  const weekday = date.toLocaleDateString("en-CA", { weekday: "short" });
  const monthDay = date.toLocaleDateString("en-CA", { month: "short", day: "numeric" });
  return `${weekday} ${monthDay}`;
}

function dateFromInputValue(dateValue) {
  const [year, month, day] = dateValue.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function buildDayButtons() {
  const today = new Date();
  const selected = new Set(selectedDates().length ? selectedDates() : [dateToInputValue(addDays(today, 2))]);
  dayButtonsEl.replaceChildren();
  for (let offset = 0; offset < 3; offset += 1) {
    const dateValue = dateToInputValue(addDays(today, offset));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "day-button";
    button.dataset.date = dateValue;
    button.textContent = formatDayButtonLabel(dateValue);
    button.classList.toggle("selected", selected.has(dateValue));
    button.addEventListener("click", () => toggleSelectedDate(dateValue));
    dayButtonsEl.appendChild(button);
  }
  syncSelectedDates();
}

function toggleSelectedDate(dateValue) {
  const selected = new Set(selectedDates());
  if (selected.has(dateValue)) {
    selected.delete(dateValue);
  } else {
    selected.add(dateValue);
  }
  if (!selected.size) selected.add(dateValue);
  setSelectedDates(Array.from(selected));
  statusEl.textContent = "Unsaved changes";
}

function selectedDates() {
  return checkDatesEl.value.split(",").map((item) => item.trim()).filter(Boolean);
}

function setSelectedDates(dates) {
  const normalized = Array.from(new Set(dates)).sort();
  checkDatesEl.value = normalized.join(",");
  dateEl.value = normalized[0];
  document.querySelector("#check_days").value = normalized.length;
  for (const button of dayButtonsEl.querySelectorAll(".day-button")) {
    button.classList.toggle("selected", normalized.includes(button.dataset.date));
  }
}

function syncSelectedDates() {
  const selected = [...dayButtonsEl.querySelectorAll(".day-button.selected")].map((button) => button.dataset.date);
  setSelectedDates(selected.length ? selected : [dateToInputValue(addDays(new Date(), 2))]);
}

function addDays(date, offset) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + offset);
  return copy;
}

function dateToInputValue(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0")
  ].join("-");
}

function selectedTimes() {
  return checkTimesEl.value.split(",").map((item) => item.trim()).filter(Boolean);
}

function currentHourSlot() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:00`;
}

function selectedBoroughs() {
  return boroughEl.value.split(",").map((item) => item.trim()).filter(Boolean);
}

function savedSiteIds() {
  return siteIdsEl.value.split(",").map((item) => item.trim()).filter(Boolean);
}

function renderLocationFilters() {
  const groupedLocations = groupLocationsByBorough();
  const fragment = document.createDocumentFragment();

  for (const group of groupedLocations) {
    const section = document.createElement("details");
    section.className = "location-group";
    section.open = group.selected;

    const summary = document.createElement("summary");
    const heading = document.createElement("h3");
    const star = document.createElement("button");
    star.type = "button";
    star.className = "group-star-button";
    star.dataset.groupId = group.id;
    star.title = "Select all sites in this borough";
    star.setAttribute("aria-label", `Select or clear all sites in ${group.name}`);
    star.textContent = "★";
    star.addEventListener("click", (event) => toggleLocationGroup(event, group));
    heading.appendChild(star);
    heading.append(group.name);
    const count = document.createElement("span");
    count.className = "location-count";
    count.textContent = String(group.locations.length);
    summary.append(heading, count);
    section.appendChild(summary);

    const buttons = document.createElement("div");
    buttons.className = "location-filter-buttons";
    for (const location of group.locations) {
      const cell = document.createElement("div");
      cell.className = "location-cell";

      const row = document.createElement("div");
      row.className = "location-cell-row";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "location-filter-button";
      button.dataset.siteKey = location.site_key;
      button.title = location.site;
      button.textContent = locationLabel(location.site);
      row.appendChild(button);

      const mapToggle = document.createElement("button");
      mapToggle.type = "button";
      mapToggle.className = "map-icon-toggle";
      mapToggle.setAttribute("aria-expanded", "false");
      mapToggle.setAttribute("aria-label", `Show map for ${location.site}`);
      mapToggle.dataset.embed = googleMapEmbedUrl(location);
      mapToggle.dataset.satellite = satelliteDetailUrl(location);
      mapToggle.dataset.site = location.site;
      mapToggle.textContent = "🌎";
      row.appendChild(mapToggle);

      cell.appendChild(row);

      const mapEl = document.createElement("div");
      mapEl.className = "site-map";
      mapEl.hidden = true;
      cell.appendChild(mapEl);

      buttons.appendChild(cell);
    }

    section.appendChild(buttons);
    fragment.appendChild(section);
  }

  document.querySelector("#locationFilterButtons").replaceChildren(fragment);
  locationFilterButtons = Array.from(document.querySelectorAll(".location-filter-button"));
}

function groupLocationsByBorough() {
  const groups = new Map();
  const boroughNames = new Map((locationData.boroughs || []).map((borough) => [String(borough.id), borough.name]));
  const selected = new Set(savedSiteIds());

  for (const location of defaultLocations) {
    const boroughId = String(location.borough_id || "");
    const groupKey = boroughId || "unmapped";
    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        id: groupKey,
        name: boroughNames.get(boroughId) || location.borough || "Other sites",
        locations: [],
        pinned: pinnedBoroughIds.includes(groupKey),
        selected: false,
      });
    }
    groups.get(groupKey).locations.push(location);
  }

  for (const group of groups.values()) {
    group.selected = group.locations.length > 0 && group.locations.every((location) => selected.has(location.site_id));
  }

  return Array.from(groups.values()).sort((left, right) => {
    if (left.selected !== right.selected) return left.selected ? -1 : 1;
    const leftPinnedRank = pinnedBoroughIds.indexOf(left.id);
    const rightPinnedRank = pinnedBoroughIds.indexOf(right.id);
    if (leftPinnedRank !== -1 || rightPinnedRank !== -1) {
      if (leftPinnedRank === -1) return 1;
      if (rightPinnedRank === -1) return -1;
      return leftPinnedRank - rightPinnedRank;
    }
    if (left.id === "unmapped") return 1;
    if (right.id === "unmapped") return -1;
    return left.name.localeCompare(right.name);
  });
}

function locationLabel(name) {
  return String(name)
    .replace(/,?\s*terrains? sportifs?/i, "")
    .replace(/,?\s*terrain de sport/i, "")
    .replace(/^Terrains de sport -\s*/i, "")
    .replace(/^Parc\s+/i, "")
    .trim();
}

function selectedLocationKeys() {
  return locationFilterButtons
    .filter((button) => button.classList.contains("selected"))
    .map((button) => button.dataset.siteKey);
}

function selectedLocations() {
  const keys = new Set(selectedLocationKeys());
  return defaultLocations.filter((location) => keys.has(location.site_key));
}

function setSelectedLocations(siteKeys) {
  const normalized = new Set(siteKeys.map(String));
  for (const button of locationFilterButtons) {
    button.classList.toggle("selected", normalized.has(button.dataset.siteKey));
  }
  const selected = defaultLocations.filter((location) => normalized.has(location.site_key));
  const boroughIds = new Set(
    selected
      .filter((location) => location.borough_id)
      .map((location) => location.borough_id)
  );
  boroughEl.value = Array.from(boroughIds).sort().join(",");
  siteIdsEl.value = selected.map((location) => location.site_id).filter(Boolean).sort().join(",");
  updateGroupStarStates();
}

function updateGroupStarStates() {
  const selected = new Set(selectedLocationKeys());
  for (const star of document.querySelectorAll(".group-star-button")) {
    const groupKeys = defaultLocations
      .filter((location) => locationGroupId(location) === star.dataset.groupId)
      .map((location) => location.site_key);
    const active = groupKeys.length > 0 && groupKeys.every((siteKey) => selected.has(siteKey));
    star.classList.toggle("active", active);
    star.title = active ? "Clear all sites in this borough" : "Select all sites in this borough";
  }
}

function locationGroupId(location) {
  return String(location.borough_id || "") || "unmapped";
}

function mapSiteKey(slot) {
  if (slot.site_id) return `site-id:${slot.site_id}`;
  return `site-name:${String(slot.site || "").trim().toLowerCase()}`;
}

function toggleLocation(button) {
  const siteKeys = new Set(selectedLocationKeys());
  const value = button.dataset.siteKey;
  if (siteKeys.has(value)) {
    siteKeys.delete(value);
  } else {
    siteKeys.add(value);
  }
  setSelectedLocations(Array.from(siteKeys));
  statusEl.textContent = "Unsaved changes";
}

async function toggleLocationGroup(event, group) {
  event.preventDefault();
  event.stopPropagation();

  const selected = new Set(selectedLocationKeys());
  const groupKeys = group.locations.map((location) => location.site_key);
  const allSelected = groupKeys.every((siteKey) => selected.has(siteKey));

  for (const siteKey of groupKeys) {
    if (allSelected) {
      selected.delete(siteKey);
    } else {
      selected.add(siteKey);
    }
  }

  setSelectedLocations(Array.from(selected));
  renderLocationFilters();
  setSelectedLocations(Array.from(selected));
  bindLocationButtons();
  statusEl.textContent = "Saving defaults...";
  try {
    await postJson("/api/config", configFromForm());
    statusEl.textContent = "Defaults saved";
  } catch (error) {
    statusEl.textContent = "Save failed";
    summaryEl.textContent = error.message;
  }
}

function resetProgressLog() {
  progressLines.splice(0);
  progressLinesEl.replaceChildren();
  updateProgressScrollbar();
}

function appendProgressLine(message) {
  progressLines.push(message);
  progressLinesEl.replaceChildren(
    ...progressLines.map((line) => {
      const item = document.createElement("div");
      item.className = "progress-line";
      item.textContent = line;
      return item;
    })
  );
  progressLinesEl.scrollTop = progressLinesEl.scrollHeight;
  updateProgressScrollbar();
}

function updateProgressScrollbar() {
  const scrollable = progressLinesEl.scrollHeight - progressLinesEl.clientHeight;
  if (scrollable <= 0) {
    progressScrollbarThumbEl.style.height = "100%";
    progressScrollbarThumbEl.style.transform = "translateY(0)";
    return;
  }

  const trackHeight = progressLinesEl.clientHeight;
  const thumbHeight = Math.max(18, (progressLinesEl.clientHeight / progressLinesEl.scrollHeight) * trackHeight);
  const travel = trackHeight - thumbHeight;
  const top = (progressLinesEl.scrollTop / scrollable) * travel;
  progressScrollbarThumbEl.style.height = `${thumbHeight}px`;
  progressScrollbarThumbEl.style.transform = `translateY(${top}px)`;
}

function setSelectedTimes(times) {
  const normalized = new Set(times);
  for (const button of timeButtons) {
    button.classList.toggle("selected", normalized.has(button.dataset.time));
  }
  checkTimesEl.value = Array.from(normalized).sort().join(",");
}

function selectedFacilityTypes() {
  return facilityTypeEl.value.split(",").map((item) => item.trim()).filter(Boolean);
}

function setSelectedFacilityTypes(typeIds) {
  const normalized = new Set(typeIds.map(String));
  for (const button of facilityTypeButtons) {
    button.classList.toggle("selected", normalized.has(button.dataset.typeId));
  }
  facilityTypeEl.value = Array.from(normalized).sort().join(",");
}

function toggleFacilityType(button) {
  const typeIds = new Set(selectedFacilityTypes());
  const value = button.dataset.typeId;
  if (typeIds.has(value)) {
    typeIds.delete(value);
  } else {
    typeIds.add(value);
  }
  if (!typeIds.size) typeIds.add(value);
  setSelectedFacilityTypes(Array.from(typeIds));
  statusEl.textContent = "Unsaved changes";
}

function toggleTime(button) {
  const times = new Set(selectedTimes());
  const value = button.dataset.time;
  if (times.has(value)) {
    times.delete(value);
  } else {
    times.add(value);
  }
  if (!times.size) {
    times.add(value);
  }
  setSelectedTimes(Array.from(times));
  statusEl.textContent = "Unsaved changes";
}

function formatCourtLabel(slot) {
  if (slot.court_number !== null && slot.court_number !== undefined) {
    return `Court ${slot.court_number}`;
  }
  return "Court";
}

function formatPrice(price) {
  if (price === null || price === undefined || Number(price) === 0) return "free";
  return `$${Number(price).toFixed(2)}`;
}

function satelliteDetailUrl(slot) {
  if (slot.detail_url) return slot.detail_url;
  const lat = Number(slot.latitude);
  const lon = Number(slot.longitude);
  const query = Number.isFinite(lat) && Number.isFinite(lon)
    ? `${lat},${lon}`
    : `${slot.site} Montreal`;
  return `https://www.google.com/maps?q=${encodeURIComponent(query)}&t=k&z=20`;
}

function googleMapEmbedUrl(slot) {
  const lat = Number(slot.latitude);
  const lon = Number(slot.longitude);
  const query = Number.isFinite(lat) && Number.isFinite(lon)
    ? `${lat},${lon}`
    : `${slot.site} Montreal`;
  return `https://maps.google.com/maps?q=${encodeURIComponent(query)}&t=k&z=17&output=embed`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelector("#saveButton").addEventListener("click", async () => {
  const saveButton = document.querySelector("#saveButton");
  const originalText = saveButton.textContent;
  saveButton.disabled = true;
  saveButton.textContent = "Saving...";
  statusEl.textContent = "Saving...";
  try {
    await postJson("/api/config", configFromForm());
    statusEl.textContent = "Defaults saved";
    saveButton.textContent = "Saved";
    setTimeout(() => {
      saveButton.textContent = originalText;
      saveButton.disabled = false;
    }, 1400);
  } catch (error) {
    statusEl.textContent = "Save failed";
    summaryEl.textContent = error.message;
    saveButton.textContent = originalText;
    saveButton.disabled = false;
  }
});

progressLinesEl.addEventListener("scroll", updateProgressScrollbar);
window.addEventListener("resize", updateProgressScrollbar);

checkNowButton.addEventListener("click", async () => {
  const originalText = checkNowButton.textContent;
  checkNowButton.disabled = true;
  checkNowButton.textContent = "Checking...";
  statusEl.textContent = "Checking Loisirs...";
  resetProgressLog();
  try {
    const result = await postJsonStream("/api/check-stream", configFromForm(), (event) => {
      if (event.type === "progress") appendProgressLine(event.message);
    });
    renderResults(result);
    statusEl.textContent = "Check complete";
    setFiltersCollapsed(true);
  } catch (error) {
    statusEl.textContent = "Check failed";
    summaryEl.textContent = error.message;
  } finally {
    checkNowButton.disabled = false;
    checkNowButton.textContent = originalText;
  }
});

const filtersPanel = document.querySelector("#filtersPanel");
const filtersToggle = document.querySelector("#filtersToggle");

function setFiltersCollapsed(collapsed) {
  filtersPanel.classList.toggle("collapsed", collapsed);
  filtersToggle.setAttribute("aria-expanded", String(!collapsed));
}

filtersToggle.addEventListener("click", () => {
  setFiltersCollapsed(!filtersPanel.classList.contains("collapsed"));
});

document.querySelector("#locationFilterButtons").addEventListener("click", (event) => {
  const button = event.target.closest(".map-icon-toggle");
  if (!button) return;
  const cell = button.closest(".location-cell");
  const mapEl = cell && cell.querySelector(".site-map");
  if (!mapEl) return;
  const expanded = button.getAttribute("aria-expanded") === "true";
  if (expanded) {
    mapEl.hidden = true;
    mapEl.replaceChildren();
    button.setAttribute("aria-expanded", "false");
    return;
  }
  mapEl.innerHTML = `
    <iframe
      class="facility-map-frame"
      title="Google map for ${button.dataset.site}"
      src="${button.dataset.embed}"
      loading="lazy"
      referrerpolicy="no-referrer-when-downgrade"
      allowfullscreen
    ></iframe>
    <a class="satellite-link" href="${button.dataset.satellite}" target="_blank" rel="noreferrer">Satellite detail</a>
  `;
  mapEl.hidden = false;
  button.setAttribute("aria-expanded", "true");
});

for (const id of fields) {
  document.querySelector(`#${id}`).addEventListener("change", () => {
    statusEl.textContent = "Unsaved changes";
  });
}

for (const button of timeButtons) {
  button.addEventListener("click", () => toggleTime(button));
}
renderLocationFilters();
bindLocationButtons();
for (const button of facilityTypeButtons) {
  button.addEventListener("click", () => toggleFacilityType(button));
}
setSelectedTimes([currentHourSlot()]);
const initialSiteIds = savedSiteIds();
setSelectedLocations(defaultLocations
  .filter((location) => initialSiteIds.length
    ? initialSiteIds.includes(location.site_id)
    : selectedBoroughs().includes(location.borough_id))
  .map((location) => location.site_key));
setSelectedFacilityTypes(selectedFacilityTypes());
buildDayButtons();
renderFacilityMaps();
updateProgressScrollbar();

function bindLocationButtons() {
  for (const button of locationFilterButtons) {
    button.addEventListener("click", () => toggleLocation(button));
  }
}
