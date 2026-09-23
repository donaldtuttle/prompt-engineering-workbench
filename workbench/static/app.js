"use strict";
const $ = id => document.getElementById(id);
let artifacts = [], providerCatalog = [], selectedRecord = null, activeId = null, pollTimer = null;
const terminal = new Set(["COMPLETED", "PARTIAL", "FAILED", "INTERRUPTED"]);
const CLOUD_PROVIDERS = new Set(["openai", "claude"]);
const PROVIDER_LABEL = {openai: "OpenAI", claude: "Claude", ollama: "Ollama"};
const example = "A study reports improved answers after adding a detailed instruction block.\n\nIdentify what the result supports, two alternative explanations, and one controlled follow-up test. Separate observations from speculation.";

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function badge(text) { return node("span", text, "badge " + text.toLowerCase()); }
function showError(error) { $("error").textContent = error.message || String(error); $("error").hidden = false; }
async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = Array.isArray(data.detail) ? data.detail.map(e => e.msg).join("; ") : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}
function updateCount() { $("char-count").textContent = `${$("task").value.length.toLocaleString()} characters`; }
function hashField(parent, label, value) {
  parent.append(node("label", label), node("div", value ?? "Unavailable", "hash"));
}
function renderArtifact() {
  const artifact = artifacts.find(a => a.artifact_id === $("artifact").value);
  const detail = $("artifact-detail"), verification = $("verification-details");
  detail.replaceChildren(); verification.replaceChildren();
  $("artifact-status").textContent = artifact?.status || "BASELINE ONLY";
  $("artifact-status").className = "badge " + (artifact?.status || "").toLowerCase();
  const conditions = artifact?.status === "VALID" ? 3 : 1;
  const replicas = Number($("replicates").value) || 1;
  const calls = conditions * replicas * ($("delivery").value === "USER_PASTE_WITH_HANDSHAKE" ? 2 : 1);
  $("lane-preview").textContent = (conditions === 3 ? "Baseline + Injector + Neutral control" : "Baseline only" + (artifact ? " · other conditions blocked" : "")) + ` · ${calls} calls before retries`;
  if (!artifact) {
    detail.append(node("p", "Only the task is submitted. No injector is loaded or included."));
    return;
  }
  const description = artifact.artifact_id.startsWith("DEMO") ? "Dedicated software-test fixture. Not QOFT material." : artifact.artifact_id.startsWith("QOFT_XI_HEX") ? "QOFT reference · original injector hash pins retained. Integrity status does not indicate model effectiveness." : "Local artifact checked against its declared manifest.";
  detail.append(node("p", description));
  const metrics = node("div", undefined, "artifact-metrics");
  for (const [label, value] of [["EXACT BYTE LENGTH", artifact.byte_length?.toLocaleString() ?? "—"], ["LINE ENDINGS", artifact.line_endings ?? "—"]]) {
    const metric = node("div", undefined, "metric"); metric.append(node("label", label), node("strong", value)); metrics.append(metric);
  }
  detail.append(metrics); hashField(detail, "ACTUAL SHA-256", artifact.sha256);
  hashField(verification, "EXPECTED FULL-FILE SHA-256", artifact.expected_sha256);
  if (artifact.expected_scoped_sha256) {
    hashField(verification, "EXPECTED SCOPED SHA-256", artifact.expected_scoped_sha256);
    hashField(verification, "ACTUAL SCOPED SHA-256", artifact.scoped_sha256);
  }
  verification.append(node("p", `Expected bytes: ${artifact.expected_byte_length ?? "unavailable"}. Source: ${artifact.source_path ?? "unavailable"}`));
  if (artifact.diagnostics.length) {
    const list = node("ul"); artifact.diagnostics.forEach(d => list.append(node("li", d))); verification.append(list);
    detail.append(node("p", "Integrity mismatch. Baseline can run; injector and neutral-control lanes will be blocked and the diagnostics saved.", "response-errors"));
  } else verification.append(node("p", "All declared checks passed. Source bytes are not rewritten."));
}
async function history() {
  const entries = await api("/api/experiments");
  $("history").replaceChildren();
  if (!entries.length) $("history").append(node("p", "Your saved runs will appear here.", "muted"));
  entries.forEach(entry => {
    const b = node("button", undefined, "history-item" + (entry.experiment_id === activeId ? " selected" : ""));
    b.type = "button"; b.dataset.experimentId = entry.experiment_id;
    b.append(node("strong", entry.title), node("small", `${entry.status} · ${new Date(entry.created_at).toLocaleString()}`));
    b.addEventListener("click", () => openRecord(entry.experiment_id).catch(showError));
    $("history").append(b);
  });
}
function renderRecord(exp) {
  selectedRecord = exp;
  $("experiment-status").hidden = false;
  $("experiment-status").textContent = exp.status;
  $("experiment-status").className = "badge " + exp.status.toLowerCase();
  $("record-meta").textContent = `${exp.request.title} · ${exp.experiment_id} · ${new Date(exp.created_at).toLocaleString()}`;
  $("results").replaceChildren();
  exp.runs.forEach(run => {
    const card = node("article", undefined, "response-card");
    card.dataset.condition = run.condition_id;
    const head = node("div", undefined, "response-head"), title = node("h3", `${run.condition_id.replaceAll("_", " ")} · R${(run.replicate_index ?? 0) + 1}`);
    title.append(node("span", `· ${run.provider}`)); head.append(title, badge(run.status));
    const body = node("div", undefined, "response-body");
    body.append(node("pre", run.result?.raw_response ?? (run.status === "BLOCKED" ? "Treatment not submitted.\nThe artifact failed integrity verification.\n\nIts original bytes and diagnostics are preserved in this record." : `${run.status} — no response available.`)));
    const foot = node("div", undefined, "response-foot"), stats = node("div", undefined, "response-stats");
    for (const text of [`${run.latency_ms ?? "—"} ms`, `Tokens: ${run.result?.token_usage ? JSON.stringify(run.result.token_usage) : "unavailable"}`, `Cost: ${run.result?.cost_usd ?? "unavailable"}`, `Retries: ${run.retries}`]) stats.append(node("span", text));
    foot.append(stats);
    if (run.errors.length) foot.append(node("div", run.errors.join("\n"), "response-errors"));
    foot.append(node("p", `${run.delivery_mode || "SYSTEM_SLOT"} · requested: ${run.model} · resolved: ${run.resolved_model || "unavailable"}`));
    hashField(foot, "FINAL PROMPT SHA-256", (run.final_condition || run.condition)?.prompt_hash);
    if (run.condition?.control_metadata) foot.append(node("p", `Length control: ${run.condition.control_metadata.control_tokens} o200k_base context tokens`));
    if (run.calls?.some(c => c.phase === "HANDSHAKE")) {
      const d = node("details"), p = node("pre", run.calls.filter(c => c.phase === "HANDSHAKE").map(c => c.result?.raw_response || c.error_type || "pending").join("\n"));
      d.append(node("summary", "Stored handshake response"), p); foot.append(d);
    }
    card.append(head, body, foot); $("results").append(card);
  });
  $("audit-note").hidden = false; $("input-snapshot").hidden = false;
  $("snapshot-content").replaceChildren(node("p", `Probe: ${exp.request.probe_id} · ${exp.evidence_scope}`), node("pre", exp.request.task));
  hashField($("snapshot-content"), "TASK SHA-256", exp.task_sha256);
  if (exp.artifact) {
    const a = exp.artifact.identity;
    hashField($("snapshot-content"), "STORED INJECTOR SHA-256", a.sha256);
    $("snapshot-content").append(node("p", `${a.byte_length} original bytes · ${a.line_endings} · ${a.status}. Export includes exact bytes as Base64 plus the original manifest.`));
  }
  for (const id of ["export-json", "export-jsonl", "reuse"]) $(id).disabled = false;
  $("replay").disabled = exp.schema_version !== "workbench-experiment-v2" || !terminal.has(exp.status);
}
async function openRecord(id) {
  clearTimeout(pollTimer); activeId = id;
  const exp = await api(`/api/experiments/${encodeURIComponent(id)}`);
  if (id !== activeId) return;
  renderRecord(exp); await history();
  if (id === activeId && !terminal.has(exp.status)) pollTimer = setTimeout(() => openRecord(id).catch(showError), 300);
}
$("experiment-form").addEventListener("submit", async event => {
  event.preventDefault(); $("error").hidden = true;
  const selected = providerCatalog.find(p => p.id === $("provider").value);
  if ($("provider").value !== "mock" && !selected?.enabled) {
    showError(new Error(selected?.reason || "Provider is disabled"));
    return;
  }
  if (CLOUD_PROVIDERS.has($("provider").value) && !$("cloud-consent").checked) {
    showError(new Error("Cloud runs require the confirmation checkbox"));
    return;
  }
  const button = $("run-button"); button.disabled = true; button.textContent = "Creating experiment…";
  try {
    const result = await api("/api/experiments", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      task: $("task").value, title: $("title").value, probe_id: $("probe-id").value,
      artifact_id: $("artifact").value || null, provider: $("provider").value,
      model: $("model").value, delivery_mode: $("delivery").value,
      replicates: Number($("replicates").value), cloud_consent: $("cloud-consent").checked,
      sampling: {temperature: optionalNumber("temperature"), top_p: optionalNumber("top-p"),
        seed: optionalNumber("seed"), max_output_tokens: Number($("max-tokens").value)},
      concurrency: Number($("concurrency").value),
      timeout_seconds: Number($("timeout").value), max_retries: Number($("retries").value)
    })});
    await openRecord(result.experiment_id);
    $("record-meta").scrollIntoView({behavior: "smooth", block: "center"});
  } catch (error) { showError(error); }
  finally { button.disabled = false; button.textContent = "Run experiment ↗"; }
});
$("reuse").addEventListener("click", () => {
  if (!selectedRecord) return;
  const r = selectedRecord.request;
  $("title").value = r.title; $("probe-id").value = r.probe_id; $("task").value = r.task;
  $("artifact").value = r.artifact_id || ""; $("concurrency").value = r.concurrency;
  $("timeout").value = r.timeout_seconds; $("retries").value = r.max_retries;
  $("provider").value = r.provider; providerChanged();
  $("model").value = r.model || "fixture-echo-v2";
  $("delivery").value = r.delivery_mode || "SYSTEM_SLOT"; $("replicates").value = r.replicates || 1;
  $("temperature").value = r.sampling?.temperature ?? ""; $("top-p").value = r.sampling?.top_p ?? "";
  $("seed").value = r.sampling?.seed ?? ""; $("max-tokens").value = r.sampling?.max_output_tokens ?? 512;
  $("cloud-consent").checked = false;
  updateCount(); renderArtifact(); $("task").focus();
});
$("load-example").addEventListener("click", () => { $("task").value = example; updateCount(); });
$("task").addEventListener("input", updateCount);
$("artifact").addEventListener("change", renderArtifact);
for (const id of ["replicates", "delivery"]) $(id).addEventListener("change", renderArtifact);
$("refresh-history").addEventListener("click", () => history().catch(showError));
$("new-experiment").addEventListener("click", () => {
  $("title").value = "Untitled experiment"; $("task").value = ""; updateCount(); $("task").focus();
});
for (const format of ["json", "jsonl"]) $("export-" + format).addEventListener("click", () => {
  if (activeId) window.location.assign(`/api/experiments/${encodeURIComponent(activeId)}/export?format=${format}`);
});
function optionalNumber(id) { return $(id).value === "" ? null : Number($(id).value); }
function providerChanged() {
  const id = $("provider").value;
  const entry = providerCatalog.find(p => p.id === id);
  const cloud = CLOUD_PROVIDERS.has(id);
  const localModel = id === "ollama";
  const name = PROVIDER_LABEL[id] || id;
  $("model").readOnly = !(cloud || localModel);
  if (!cloud && !localModel) $("model").value = "fixture-echo-v2";
  else if ($("model").value.startsWith("fixture-")) $("model").value = "";
  $("model").placeholder = localModel
    ? "Exact local model name, such as llama3.1:8b"
    : cloud ? "Enter an exact model or snapshot ID" : "";
  $("cloud-confirmation").hidden = !cloud;
  $("cloud-consent").required = cloud;
  $("cloud-consent").checked = false;
  $("cloud-consent-label").textContent = `Send this probe and its context to ${name}. API charges apply, including handshake calls and retries.`;
  $("seed").disabled = cloud;
  if (cloud) $("seed").value = "";
  $("mode-badge").textContent = cloud
    ? `● ${name.toUpperCase()} CLOUD`
    : localModel ? "● OLLAMA LOCAL" : "● OFFLINE FIXTURE MODE";
  $("charge-note").textContent = cloud
    ? `${name} API charges apply`
    : localModel ? "Loopback only · no API key" : "No API keys · no API charges";
  $("mode-notice").textContent = cloud
    ? "The selected cloud provider receives every lane's probe and context. Evaluation is not performed."
    : localModel
      ? "Ollama runs on this machine. The limit is that model's reported context length. A longer prompt is refused, not truncated."
      : "Mock mode runs locally. Synthetic responses test the workbench; no language model is called.";
  $("run-button").disabled = id !== "mock" && !entry?.enabled;
}
function providerOptionLabel(entry) {
  const name = PROVIDER_LABEL[entry.id] || entry.id;
  if (entry.enabled) return CLOUD_PROVIDERS.has(entry.id) ? `${name} · cloud API` : `${name} · available`;
  return `${name} · ${entry.reason || "unavailable"}`;
}
function renderProviders(providers) {
  providerCatalog = providers;
  const select = $("provider");
  const current = select.value;
  for (const option of [...select.options]) if (option.value !== "mock") option.remove();
  for (const entry of providers) {
    if (entry.id === "mock") continue;
    const option = node("option", providerOptionLabel(entry));
    option.value = entry.id;
    option.disabled = entry.enabled !== true;
    if (entry.reason) option.title = entry.reason;
    select.append(option);
  }
  const chosen = [...select.options].find(option => option.value === current && !option.disabled);
  select.value = chosen ? current : "mock";
}
$("provider").addEventListener("change", providerChanged);
$("replay").addEventListener("click", async () => {
  if (!selectedRecord) return;
  const providerId = selectedRecord.request.provider;
  const cloud = CLOUD_PROVIDERS.has(providerId);
  const name = PROVIDER_LABEL[providerId] || providerId;
  if (cloud && !window.confirm(`Replay the stored prompts through ${name}? API charges apply.`)) return;
  $("replay").disabled = true;
  try {
    const result = await api(`/api/experiments/${encodeURIComponent(selectedRecord.experiment_id)}/replay`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({cloud_consent:cloud})});
    await openRecord(result.experiment_id);
  } catch (error) { showError(error); $("replay").disabled = false; }
});
async function init() {
  renderProviders(await api("/api/providers"));
  providerChanged();
  artifacts = await api("/api/artifacts");
  for (const artifact of artifacts) {
    const label = artifact.artifact_id.startsWith("DEMO") ? "Demo fixture · software validation" : artifact.artifact_id.startsWith("QOFT_XI_HEX") ? "QOFT Ξ-HEX v1.1 · restored LF" : artifact.artifact_id;
    const option = node("option", label);
    option.value = artifact.artifact_id; $("artifact").append(option);
  }
  const none = node("option", "No injector · baseline only"); none.value = ""; $("artifact").append(none);
  renderArtifact(); $("task").value = example; updateCount(); await history();
}
init().catch(showError);
