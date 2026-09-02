import { api, backendBase, backendGeneration, post } from "./backend.js";

const $ = (id) => document.getElementById(id);
const TERMINAL = new Set([
  "cancelled", "completed", "completed_with_errors", "partially_completed", "failed",
]);
const ROLE_LABELS = {
  company_name: "Company name",
  company_name_ar: "Company name (Arabic source value)",
  email: "Organization email",
  phone: "Organization phone",
  latitude: "Latitude",
  longitude: "Longitude",
  city: "City",
  country: "Country",
  profile_url: "Source profile URL",
  website: "Known website",
};

const params = new URLSearchParams(window.location.search);
let sourceKey = params.get("source") || "";
let siteKey = params.get("site") || "";
let model = null;
let definition = null;
let currentJob = null;
let pollTimer = null;
let pollFailures = 0;
let editMode = false;
let reviewAfter = 0;
let identityAfter = 0;
let mergeAfter = 0;

function message(text = "", kind = "") {
  const node = $("message");
  node.textContent = text;
  node.className = `message ${kind}`.trim();
  node.classList.toggle("hidden", !text);
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

function fillSelect(node, choices, selected = "", emptyLabel = "") {
  node.replaceChildren();
  if (emptyLabel) node.append(option("", emptyLabel));
  for (const item of choices) node.append(option(item.value, item.label));
  node.value = selected || "";
}

function dataset(key) {
  return (model?.datasets || []).find((item) => item.dataset_key === key) || null;
}

function fieldChoices() {
  const source = dataset($("source-dataset").value);
  const detail = dataset($("detail-dataset").value);
  const choices = [];
  for (const [group, selected] of [["Source", source], ["Detail", detail]]) {
    for (const field of selected?.fields || []) {
      choices.push({
        value: `${group.toLowerCase()}:${field.field_key}`,
        label: `${field.label || field.field_key} · ${field.field_key} · ${group}`,
      });
    }
  }
  return choices;
}

function renderJoins(proposal) {
  const source = dataset($("source-dataset").value);
  const detail = dataset($("detail-dataset").value);
  fillSelect(
    $("entity-key"),
    (source?.fields || []).map((field) => ({
      value: field.field_key,
      label: `${field.label || field.field_key} · ${field.field_key}`,
    })),
    proposal.entity_key_field,
  );
  fillSelect(
    $("detail-key"),
    (detail?.fields || []).map((field) => ({
      value: field.field_key,
      label: `${field.label || field.field_key} · ${field.field_key}`,
    })),
    proposal.detail_key_field,
    detail ? "Choose a join key" : "No detail dataset selected",
  );
  $("detail-key").disabled = !detail;
  $("detail-key").dataset.available = String(Boolean(detail));
}

function renderMappings(proposal) {
  const root = $("field-mapping");
  root.replaceChildren();
  const choices = fieldChoices();
  for (const role of model.field_roles || []) {
    const label = document.createElement("label");
    const title = document.createElement("span");
    const select = document.createElement("select");
    title.textContent = ROLE_LABELS[role] || role;
    select.dataset.role = role;
    const stored = proposal.field_mapping?.[role] || "";
    const selected = stored && !stored.includes(":") ? `source:${stored}` : stored;
    fillSelect(select, choices, selected, "Not mapped");
    label.append(title, select);
    root.append(label);
  }
}

function renderProviders(proposal) {
  const root = $("providers");
  root.replaceChildren();
  const chosen = new Set(proposal.providers || []);
  for (const provider of model.provider_availability || []) {
    const label = document.createElement("label");
    label.className = "provider-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = provider.key;
    input.dataset.provider = provider.key;
    input.dataset.available = String(provider.available);
    input.checked = provider.available && chosen.has(provider.key);
    input.disabled = !provider.available;
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    const detail = document.createElement("small");
    title.textContent = provider.label;
    detail.textContent = provider.reason;
    copy.append(title, detail);
    label.append(input, copy);
    root.append(label);
  }
}

function metric(label, value) {
  const node = document.createElement("div");
  node.className = "metric";
  const number = document.createElement("strong");
  const caption = document.createElement("span");
  number.textContent = String(value ?? 0);
  caption.textContent = label;
  node.append(number, caption);
  return node;
}

function renderCounts() {
  const counts = definition?.counts || {};
  const preflight = model?.preflight || {};
  $("dataset-counts").replaceChildren(
    metric("Organizations", counts.organizations ?? preflight.source_records),
    metric("Verified", counts.verified),
    metric("Needs review", counts.needs_review),
    metric("Estimated requests", model?.estimated_requests),
  );
}

function lockDefinition() {
  const locked = Boolean(definition) && !editMode;
  const latestStatus = definition?.latest_job?.status;
  const jobActive = Boolean(latestStatus && !TERMINAL.has(latestStatus));
  for (const node of document.querySelectorAll(
    ".config-card input, .config-card select",
  )) node.disabled = locked || node.dataset.available === "false";
  $("source-dataset").disabled = Boolean(definition);
  $("output-key").disabled = Boolean(definition);
  $("create-definition").disabled = locked || jobActive;
  $("create-definition").classList.toggle(
    "hidden", Boolean(definition) && !editMode,
  );
  $("create-definition").textContent = editMode
    ? "Save definition version" : "Create enrichment dataset";
  $("edit-definition").classList.toggle("hidden", !definition || editMode);
  $("edit-definition").disabled = jobActive;
  const definitionActive = definition?.status === "active";
  $("definition-status").classList.toggle("hidden", !definition || editMode);
  $("definition-status").disabled = jobActive;
  $("definition-status").textContent = definition && !definitionActive
    ? "Activate definition" : "Pause definition";
  $("run-enrichment").disabled = !locked || jobActive || !definitionActive;
  $("open-data").disabled = !locked;
  $("definition-state").textContent = editMode
    ? `Editing v${definition?.configuration_version || 1}`
    : definition
      ? `${definition.status || "active"} · v${definition.configuration_version || 1}`
      : "Draft";
  renderCounts();
}

function render(payload) {
  model = payload;
  definition = payload.definition || null;
  const proposal = definition ? {
    ...payload.proposal,
    ...definition,
    output_dataset_name: definition.output_dataset_name,
  } : payload.proposal;
  sourceKey = proposal.source_dataset_key;
  siteKey = payload.site.site_key;
  $("workspace-summary").textContent =
    `${payload.site.display_name} · ${sourceKey} · source rows stay unchanged`;
  fillSelect(
    $("source-dataset"),
    payload.datasets.map((item) => ({value: item.dataset_key, label: item.label})),
    proposal.source_dataset_key,
  );
  fillSelect(
    $("detail-dataset"),
    payload.datasets
      .filter((item) => item.dataset_key !== proposal.source_dataset_key)
      .map((item) => ({value: item.dataset_key, label: item.label})),
    proposal.detail_dataset_key,
    "No detail dataset",
  );
  renderJoins(proposal);
  renderMappings(proposal);
  renderProviders(proposal);
  $("output-key").value = proposal.output_dataset_key || "";
  $("output-name").value = proposal.output_dataset_name || "Organization Enrichment";
  lockDefinition();
  if (definition) {
    refreshReview();
    refreshIdentityCandidates();
    refreshMergeHistory();
    restoreLatestJob();
  }
}

async function load(nextSource = sourceKey) {
  if (!nextSource) {
    message("This page needs a source dataset. Open it from a dataset card.", "error");
    return;
  }
  await backendBase();
  const generation = backendGeneration();
  message();
  $("workspace-summary").textContent = "Reading the source definition…";
  try {
    const siteQuery = siteKey ? `?site_key=${encodeURIComponent(siteKey)}` : "";
    const payload = await api(
      `/api/enrichment/sources/${encodeURIComponent(nextSource)}${siteQuery}`,
    );
    if (generation === backendGeneration()) render(payload);
  } catch (error) {
    if (generation !== backendGeneration()) return;
    $("workspace-summary").textContent = "Source definition unavailable";
    message(error.message, "error");
  }
}

function mappingPayload() {
  return Object.fromEntries(
    [...document.querySelectorAll("#field-mapping select")]
      .filter((node) => node.value)
      .map((node) => [node.dataset.role, node.value]),
  );
}

async function createDefinition() {
  message();
  $("create-definition").disabled = true;
  const detailKey = $("detail-dataset").value || null;
  const payload = {
    site_key: siteKey || null,
    source_dataset_key: $("source-dataset").value,
    detail_dataset_key: detailKey,
    output_dataset_key: $("output-key").value.trim() || null,
    output_dataset_name: $("output-name").value.trim() || null,
    entity_key_field: $("entity-key").value,
    detail_key_field: detailKey ? $("detail-key").value : null,
    field_mapping: mappingPayload(),
    providers: [...document.querySelectorAll("[data-provider]:checked")]
      .map((node) => node.value),
  };
  try {
    const wasEditing = editMode;
    definition = wasEditing
      ? await api(`/api/enrichment/definitions/${definition.enrichment_definition_id}`, {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      })
      : await post("/api/enrichment/definitions", payload);
    editMode = false;
    message(
      wasEditing
        ? `Saved definition v${definition.configuration_version}. Run enrichment to apply it.`
        : `Created ${definition.output_dataset_key}. The source datasets were not changed.`,
      "success",
    );
    lockDefinition();
  } catch (error) {
    $("create-definition").disabled = false;
    message(error.message, "error");
  }
}

function renderJob(job) {
  currentJob = job;
  if (definition) {
    definition.latest_job = {job_ref: job.job_ref, status: job.status};
  }
  $("run-card").classList.remove("hidden");
  $("job-status").textContent = job.status.replaceAll("_", " ");
  const progress = job.progress || {};
  $("job-progress").max = Math.max(progress.total || 0, 1);
  $("job-progress").value = progress.done || 0;
  $("job-progress-text").textContent =
    `${progress.done || 0} of ${progress.total || 0} ${progress.unit || "organizations"}`
    + (job.current_source_key ? ` · ${job.current_source_key}` : "");
  const counters = job.counters || {};
  $("job-counters").replaceChildren(
    metric("Facts changed", counters.facts_changed),
    metric("Rows changed", counters.rows_changed),
    metric("Provider errors", counters.provider_errors),
    metric("Providers disabled", counters.providers_disabled),
    metric("Record errors", counters.errors),
  );
  $("pause-job").disabled = !["preparing", "running"].includes(job.status);
  $("resume-job").disabled = job.status !== "paused";
  $("cancel-job").disabled = TERMINAL.has(job.status);
  lockDefinition();
}

async function restoreLatestJob() {
  const latest = definition?.latest_job;
  if (!latest?.job_ref || currentJob?.job_ref === latest.job_ref) return;
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(latest.job_ref)}`);
    renderJob(job);
    if (!TERMINAL.has(job.status) && !pollTimer) pollJob();
  } catch (error) {
    message(error.message, "error");
  }
}

async function pollJob() {
  if (!currentJob) return;
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(currentJob.job_ref)}`);
    pollFailures = 0;
    renderJob(job);
    if (TERMINAL.has(job.status)) {
      clearTimeout(pollTimer);
      pollTimer = null;
      await load(sourceKey);
      return;
    }
  } catch (error) {
    pollFailures += 1;
    message(error.message, "error");
    pollTimer = setTimeout(pollJob, Math.min(30000, 2000 * (2 ** pollFailures)));
    return;
  }
  pollTimer = setTimeout(pollJob, 2000);
}

async function runEnrichment() {
  if (!definition) return;
  message();
  $("run-enrichment").disabled = true;
  try {
    const queued = await post(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}/runs`, {},
    );
    renderJob({
      ...queued,
      progress: {done: 0, total: 0, unit: "organizations"},
      counters: {}, current_source_key: null,
    });
    pollJob();
  } catch (error) {
    message(error.message, "error");
  } finally {
    lockDefinition();
  }
}

async function toggleDefinitionStatus() {
  if (!definition) return;
  const status = definition.status === "active" ? "paused" : "active";
  try {
    definition = await api(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}/status`,
      {
        method: "PATCH", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({status}),
      },
    );
    message(`Definition is now ${status}.`, "success");
    lockDefinition();
  } catch (error) {
    message(error.message, "error");
  }
}

async function controlJob(control) {
  if (!currentJob) return;
  try {
    renderJob(await post(`/api/jobs/${encodeURIComponent(currentJob.job_ref)}/control`, {
      control,
    }));
    if (!pollTimer) pollJob();
  } catch (error) {
    message(error.message, "error");
  }
}

async function decideReview(row, action) {
  let value = null;
  if (action === "override") {
    const entered = window.prompt("Verified replacement value", String(row.value ?? ""));
    if (entered === null) return;
    if (typeof row.value === "object") {
      try {
        value = JSON.parse(entered);
      } catch {
        message("The replacement must be valid JSON.", "error");
        return;
      }
    } else if (typeof row.value === "number") {
      value = Number(entered);
      if (!Number.isFinite(value)) {
        message("The replacement must be a valid number.", "error");
        return;
      }
    } else {
      value = entered;
    }
  }
  await post(
    `/api/enrichment/definitions/${definition.enrichment_definition_id}`
      + `/review/${row.organization_fact_id}/decision`,
    {action, value, reviewer: "owner", reason: "Reviewed in ScrapeX"},
  );
  await refreshReview(true);
  await load(sourceKey);
}

async function refreshReview(reset = true) {
  if (!definition) return;
  try {
    if (reset) reviewAfter = 0;
    const payload = await api(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}`
        + `/review?limit=100&after_id=${reviewAfter}`,
    );
    const rows = payload.items || [];
    const body = $("review-rows");
    if (reset) body.replaceChildren();
    for (const row of rows) {
      const tr = document.createElement("tr");
      const values = [
        row.organization_id,
        row.field_key,
        typeof row.value === "string" ? row.value : JSON.stringify(row.value),
        row.provider,
        Number(row.confidence || 0).toFixed(2),
        JSON.stringify(row.evidence),
      ];
      values.forEach((value, index) => {
        const td = document.createElement("td");
        if (index === 5) {
          const code = document.createElement("code");
          code.textContent = value;
          td.append(code);
        } else {
          td.textContent = value;
        }
        tr.append(td);
      });
      const actions = document.createElement("td");
      for (const [action, label] of [
        ["approve", "Approve"], ["reject", "Reject"], ["override", "Override"],
      ]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button ghost";
        button.textContent = label;
        button.addEventListener("click", () => decideReview(row, action));
        actions.append(button);
      }
      tr.append(actions);
      body.append(tr);
    }
    reviewAfter = payload.next_after_id || reviewAfter;
    $("review-count").textContent = String(body.children.length);
    $("review-empty").classList.toggle("hidden", body.children.length > 0);
    $("review-more").classList.toggle("hidden", !payload.next_after_id);
    $("review-card").classList.remove("hidden");
  } catch (error) {
    message(error.message, "error");
  }
}

async function mergeIdentity(row) {
  const confirmed = window.confirm(
    `Merge ${row.organization_id} into ${row.candidate_id}? This changes the canonical `
      + "identity but preserves facts and the merge audit trail.",
  );
  if (!confirmed) return;
  const reason = window.prompt("Reason for the identity merge");
  if (!reason?.trim()) return;
  try {
    await post(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}`
        + `/organizations/${encodeURIComponent(row.organization_id)}/merge`,
      {
        target_organization_id: row.candidate_id,
        reviewer: "owner",
        reason: reason.trim(),
      },
    );
    message("Organization identities merged with an audit record.", "success");
    await load(sourceKey);
  } catch (error) {
    message(error.message, "error");
  }
}

async function refreshIdentityCandidates(reset = true) {
  if (!definition) return;
  try {
    if (reset) identityAfter = 0;
    const payload = await api(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}`
        + `/identity-candidates?limit=100&after_id=${identityAfter}`,
    );
    const body = $("identity-rows");
    if (reset) body.replaceChildren();
    for (const row of payload.items || []) {
      const tr = document.createElement("tr");
      for (const value of [
        row.organization_id,
        row.alias_type,
        row.normalized_value,
        row.candidate_id,
        Math.min(Number(row.confidence || 0), Number(row.candidate_confidence || 0))
          .toFixed(2),
      ]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      const actions = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button ghost";
      button.textContent = "Merge";
      button.addEventListener("click", () => mergeIdentity(row));
      actions.append(button);
      tr.append(actions);
      body.append(tr);
    }
    identityAfter = payload.next_after_id || identityAfter;
    $("identity-count").textContent = String(body.children.length);
    $("identity-empty").classList.toggle("hidden", body.children.length > 0);
    $("identity-more").classList.toggle("hidden", !payload.next_after_id);
    $("identity-card").classList.remove("hidden");
  } catch (error) {
    message(error.message, "error");
  }
}

async function reverseMerge(row) {
  const reason = window.prompt(
    "Reason for reversing this canonical merge",
  );
  if (!reason?.trim()) return;
  try {
    await post(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}`
        + `/merges/${row.organization_merge_id}/reverse`,
      {reviewer: "owner", reason: reason.trim()},
    );
    message("Canonical merge reversed and outputs rebuilt.", "success");
    await load(sourceKey);
  } catch (error) {
    message(error.message, "error");
  }
}

async function refreshMergeHistory(reset = true) {
  if (!definition) return;
  try {
    if (reset) mergeAfter = 0;
    const payload = await api(
      `/api/enrichment/definitions/${definition.enrichment_definition_id}`
        + `/merges?limit=100&after_id=${mergeAfter}`,
    );
    const body = $("merge-rows");
    if (reset) body.replaceChildren();
    for (const row of payload.items || []) {
      const tr = document.createElement("tr");
      for (const value of [
        row.source_organization_id,
        row.target_organization_id,
        row.merged_at,
        row.reversed_at ? "reversed" : "active",
      ]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      const actions = document.createElement("td");
      if (!row.reversed_at) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button ghost";
        button.textContent = "Reverse";
        button.addEventListener("click", () => reverseMerge(row));
        actions.append(button);
      }
      tr.append(actions);
      body.append(tr);
    }
    mergeAfter = payload.next_after_id || mergeAfter;
    $("merge-empty").classList.toggle("hidden", body.children.length > 0);
    $("merge-more").classList.toggle("hidden", !payload.next_after_id);
  } catch (error) {
    message(error.message, "error");
  }
}

$("reload").addEventListener("click", () => load(sourceKey));
$("source-dataset").addEventListener("change", (event) => load(event.target.value));
$("detail-dataset").addEventListener("change", () => {
  const proposal = {...model.proposal, detail_dataset_key: $("detail-dataset").value};
  renderJoins(proposal);
  renderMappings(proposal);
});
$("create-definition").addEventListener("click", createDefinition);
$("edit-definition").addEventListener("click", () => {
  editMode = true;
  lockDefinition();
});
$("definition-status").addEventListener("click", toggleDefinitionStatus);
$("review-more").addEventListener("click", () => refreshReview(false));
$("identity-more").addEventListener("click", () => refreshIdentityCandidates(false));
$("merge-more").addEventListener("click", () => refreshMergeHistory(false));
$("run-enrichment").addEventListener("click", runEnrichment);
$("open-data").addEventListener("click", () => {
  if (!definition) return;
  chrome.tabs.create({url: chrome.runtime.getURL(
    `data.html?source=${encodeURIComponent(definition.output_dataset_key)}`
      + `&site=${encodeURIComponent(definition.site_key)}`,
  )});
});
$("pause-job").addEventListener("click", () => controlJob("pause"));
$("resume-job").addEventListener("click", () => controlJob("resume"));
$("cancel-job").addEventListener("click", () => controlJob("cancel"));
$("refresh-review").addEventListener("click", refreshReview);

load();
