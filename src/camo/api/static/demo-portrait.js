const portraitState = {
  projectId: "",
  sourceId: "",
  characterId: "",
  characterName: "",
  portrait: null,
  events: [],
  memories: [],
  activeInspectorView: "portrait",
};

const portraitEls = {
  projectId: document.getElementById("project-id"),
  sourceId: document.getElementById("source-id"),
  characterId: document.getElementById("character-id"),
  characterName: document.getElementById("character-name"),
  aliases: document.getElementById("aliases"),
  loadProject: document.getElementById("load-project"),
  generatePortrait: document.getElementById("generate-portrait"),
  statusLine: document.getElementById("status-line"),
  errorLine: document.getElementById("error-line"),
  characterHeading: document.getElementById("character-heading"),
  characterBadge: document.getElementById("character-badge"),
  characterSummary: document.getElementById("character-summary"),
  matchedCount: document.getElementById("matched-count"),
  memoryCount: document.getElementById("memory-count"),
  eventCount: document.getElementById("event-count"),
  portraitSections: document.getElementById("portrait-sections"),
  coreSections: document.getElementById("core-sections"),
  facetSections: document.getElementById("facet-sections"),
  eventsList: document.getElementById("events-list"),
  memoriesList: document.getElementById("memories-list"),
  inspectorTabs: Array.from(document.querySelectorAll(".inspector-tab")),
  inspectorPanes: Array.from(document.querySelectorAll("[data-inspector-pane]")),
  jsonOutput: document.getElementById("json-output"),
  jsonTabs: Array.from(document.querySelectorAll(".json-tab")),
  copyJson: document.getElementById("copy-json"),
};

function portraitSetStatus(message) {
  portraitEls.statusLine.textContent = message;
}

function portraitSetError(message) {
  portraitEls.errorLine.textContent = message || "";
}

function portraitSetSkeleton(active) {
  [
    portraitEls.characterSummary,
    portraitEls.portraitSections,
    portraitEls.coreSections,
    portraitEls.facetSections,
    portraitEls.eventsList,
    portraitEls.memoriesList,
    portraitEls.jsonOutput,
  ].forEach((node) => {
    node.classList.toggle("skeleton", active);
  });
}

function renderChipRow(items) {
  if (!items || !items.length) {
    return `<p class="summary-copy">No data yet.</p>`;
  }
  return `<div class="chip-row">${items
    .map((item) => `<span class="chip">${window.CamoDemo.escapeHtml(item)}</span>`)
    .join("")}</div>`;
}

function renderKeyValueRows(rows) {
  return rows
    .map(
      ([label, value]) => `
        <p class="stack-copy">
          <strong>${window.CamoDemo.escapeHtml(label)}</strong>: ${window.CamoDemo.escapeHtml(value || "No data yet.")}
        </p>`,
    )
    .join("");
}

function buildIndexJson(detail = {}) {
  return {
    character_id: detail.character_id,
    schema_version: detail.schema_version,
    character_type: detail.character_type,
    name: detail.name,
    description: detail.description,
    aliases: detail.aliases || [],
    titles: detail.titles || [],
    identities: detail.identities || [],
    first_appearance: detail.first_appearance || null,
    confidence: detail.confidence ?? 0,
    source_segments: detail.source_segments || [],
  };
}

function renderPortraitOverview(detail = {}) {
  const firstAppearance = detail.first_appearance || "Not captured yet";

  portraitEls.portraitSections.innerHTML = `
    <section class="section-block">
      <h4>Description</h4>
      <p class="stack-copy">${window.CamoDemo.escapeHtml(detail.description || "No description yet.")}</p>
    </section>
    <section class="section-block">
      <h4>Aliases</h4>
      ${renderChipRow(detail.aliases || [])}
    </section>
    <section class="section-block">
      <h4>Titles</h4>
      ${renderChipRow(detail.titles || [])}
    </section>
    <section class="section-block">
      <h4>Identities</h4>
      ${renderChipRow((detail.identities || []).map((item) => `${item.type}: ${item.value}`))}
    </section>
    <section class="section-block">
      <h4>Source anchors</h4>
      ${renderKeyValueRows([
        ["First appearance", firstAppearance],
        ["Confidence", String(detail.confidence ?? 0)],
        ["Schema", detail.schema_version || "0.2"],
        ["Status", detail.status || "draft"],
      ])}
    </section>
  `;
}

function renderCore(core = {}) {
  portraitEls.coreSections.innerHTML = `
    <section class="section-block">
      <h4>Trait Profile</h4>
      ${renderKeyValueRows([
        ["Openness", String(core.trait_profile?.openness ?? 0)],
        ["Conscientiousness", String(core.trait_profile?.conscientiousness ?? 0)],
        ["Extraversion", String(core.trait_profile?.extraversion ?? 0)],
        ["Agreeableness", String(core.trait_profile?.agreeableness ?? 0)],
        ["Neuroticism", String(core.trait_profile?.neuroticism ?? 0)],
      ])}
    </section>
    <section class="section-block">
      <h4>Motivation</h4>
      <p class="stack-copy"><strong>Primary</strong></p>
      ${renderChipRow(core.motivation_profile?.primary || [])}
      <p class="stack-copy"><strong>Secondary</strong></p>
      ${renderChipRow(core.motivation_profile?.secondary || [])}
      <p class="stack-copy"><strong>Suppressed</strong></p>
      ${renderChipRow(core.motivation_profile?.suppressed || [])}
    </section>
    <section class="section-block">
      <h4>Behavior</h4>
      ${renderKeyValueRows([
        ["Conflict style", core.behavior_profile?.conflict_style],
        ["Risk preference", core.behavior_profile?.risk_preference],
        ["Decision style", core.behavior_profile?.decision_style],
        ["Dominance style", core.behavior_profile?.dominance_style],
      ])}
    </section>
    <section class="section-block">
      <h4>Communication</h4>
      ${renderKeyValueRows([
        ["Tone", core.communication_profile?.tone],
        ["Directness", core.communication_profile?.directness],
        ["Emotional expressiveness", core.communication_profile?.emotional_expressiveness],
        ["Verbosity", core.communication_profile?.verbosity],
        ["Politeness", core.communication_profile?.politeness],
      ])}
    </section>
    <section class="section-block">
      <h4>Constraints</h4>
      ${renderKeyValueRows([
        ["Knowledge scope", core.constraint_profile?.knowledge_scope],
        ["Role consistency", core.constraint_profile?.role_consistency],
      ])}
      ${renderChipRow(
        (core.constraint_profile?.forbidden_behaviors || []).map(
          (item) => `${item.namespace}.${item.tag}: ${item.description}`,
        ),
      )}
    </section>
  `;
}

function renderFacet(facet = {}) {
  portraitEls.facetSections.innerHTML = `
    <section class="section-block">
      <h4>Biographical Notes</h4>
      ${renderKeyValueRows([
        ["Appearance", facet.biographical_notes?.appearance],
        ["Backstory", facet.biographical_notes?.backstory],
      ])}
      <p class="stack-copy"><strong>Signature habits</strong></p>
      ${renderChipRow(facet.biographical_notes?.signature_habits || [])}
      <p class="stack-copy"><strong>Catchphrases</strong></p>
      ${renderChipRow(facet.biographical_notes?.catchphrases || [])}
    </section>
    <section class="section-block">
      <h4>Temporal Snapshots</h4>
      ${
        (facet.temporal_snapshots || []).length
          ? (facet.temporal_snapshots || [])
              .map(
                (item) => `
                  <div class="section-block">
                    <h4>${window.CamoDemo.escapeHtml(item.period_label || "Period")}</h4>
                    <p class="stack-copy">${window.CamoDemo.escapeHtml(item.notes || "No notes yet.")}</p>
                    ${renderChipRow(item.period_source || [])}
                  </div>`,
              )
              .join("")
          : `<p class="stack-copy">No temporal snapshots yet.</p>`
      }
    </section>
    <section class="section-block">
      <h4>Evidence Map</h4>
      ${
        Object.keys(facet.evidence_map || {}).length
          ? Object.entries(facet.evidence_map || {})
              .map(
                ([fieldPath, entries]) => `
                  <div class="section-block">
                    <h4>${window.CamoDemo.escapeHtml(fieldPath)}</h4>
                    ${(entries || [])
                      .map(
                        (entry) => `
                          <p class="stack-copy">${window.CamoDemo.escapeHtml(entry.reasoning || "")}</p>
                          <p class="stack-copy">${window.CamoDemo.escapeHtml(entry.excerpt || "")}</p>
                          ${renderChipRow(entry.segment_ids || [])}`,
                      )
                      .join("")}
                  </div>`,
              )
              .join("")
          : `<p class="stack-copy">No evidence map yet.</p>`
      }
    </section>
    <section class="section-block">
      <h4>Extraction Meta</h4>
      ${renderKeyValueRows([
        ["Extracted at", facet.extraction_meta?.extracted_at],
        ["Reviewer status", facet.extraction_meta?.reviewer_status],
        ["Reviewer notes", facet.extraction_meta?.reviewer_notes],
        ["Schema", facet.extraction_meta?.schema_version],
      ])}
      <p class="stack-copy"><strong>Source texts</strong></p>
      ${renderChipRow(facet.extraction_meta?.source_texts || [])}
    </section>
  `;
}

function setInspectorView(view) {
  portraitState.activeInspectorView = view;
  portraitEls.inspectorTabs.forEach((tab) => {
    const active = tab.dataset.inspectorView === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  portraitEls.inspectorPanes.forEach((pane) => {
    const active = pane.dataset.inspectorPane === view;
    pane.classList.toggle("active", active);
    pane.hidden = !active;
  });
}

function renderEvents(events = []) {
  if (!events.length) {
    portraitEls.eventsList.className = "timeline empty-state";
    portraitEls.eventsList.textContent = "No events yet.";
    return;
  }

  portraitEls.eventsList.className = "timeline";
  portraitEls.eventsList.innerHTML = events
    .map(
      (event) => `
        <article class="event-card">
          <h4>${window.CamoDemo.escapeHtml(event.title)}</h4>
          <p>${window.CamoDemo.escapeHtml(event.description || "No event description.")}</p>
          <div class="event-meta">
            <span>Timeline ${window.CamoDemo.escapeHtml(String(event.timeline_pos ?? "-"))}</span>
            <span>${window.CamoDemo.escapeHtml(event.location || "Location unknown")}</span>
            <span>${window.CamoDemo.escapeHtml(event.emotion_valence || "Neutral")}</span>
          </div>
        </article>`,
    )
    .join("");
}

function renderMemories(memories = []) {
  if (!memories.length) {
    portraitEls.memoriesList.className = "memory-list empty-state";
    portraitEls.memoriesList.textContent = "No memories yet.";
    return;
  }

  portraitEls.memoriesList.className = "memory-list";
  portraitEls.memoriesList.innerHTML = memories
    .map(
      (memory) => `
        <article class="memory-card">
          <h4>${window.CamoDemo.escapeHtml(memory.memory_type)}</h4>
          <p>${window.CamoDemo.escapeHtml(memory.content)}</p>
          <div class="memory-meta">
            <span>Salience ${window.CamoDemo.escapeHtml(String(memory.salience))}</span>
            <span>Recency ${window.CamoDemo.escapeHtml(String(memory.recency))}</span>
            <span>${window.CamoDemo.escapeHtml(memory.emotion_valence || "Neutral")}</span>
          </div>
        </article>`,
    )
    .join("");
}

function updateRawJson(view) {
  portraitEls.jsonTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.jsonView === view);
  });

  let payload = {};
  if (view === "portrait") {
    payload = {
      index: buildIndexJson(portraitState.portrait || {}),
      core: portraitState.portrait?.core || {},
      facet: portraitState.portrait?.facet || {},
    };
  } else if (view === "events") {
    payload = portraitState.events;
  } else if (view === "memories") {
    payload = portraitState.memories;
  } else {
    payload = {
      index: buildIndexJson(portraitState.portrait || {}),
      core: portraitState.portrait?.core || {},
      facet: portraitState.portrait?.facet || {},
      events: portraitState.events,
      memories: portraitState.memories,
    };
  }
  portraitEls.jsonOutput.textContent = JSON.stringify(payload, null, 2);
}

function syncPortraitSelection() {
  if (!portraitState.characterId) {
    return;
  }
  const options = Array.from(portraitEls.characterId.options);
  if (!options.some((option) => option.value === portraitState.characterId)) {
    const option = document.createElement("option");
    option.value = portraitState.characterId;
    option.textContent = portraitState.characterName || portraitState.characterId;
    portraitEls.characterId.appendChild(option);
  }
  portraitEls.characterId.value = portraitState.characterId;
}

function renderPortrait(detail, events, memories, matchedCount) {
  portraitState.characterId = detail.character_id;
  portraitState.characterName = detail.name;
  portraitState.portrait = detail;
  portraitState.events = events;
  portraitState.memories = memories;

  portraitEls.characterHeading.textContent = detail.name;
  portraitEls.characterBadge.textContent = detail.aliases?.length ? detail.aliases.join(" · ") : "Saved character";
  portraitEls.characterSummary.textContent =
    detail.description ||
    (detail.core?.motivation_profile?.primary || []).join(" · ") ||
    "Portrait loaded.";
  portraitEls.matchedCount.textContent = String(matchedCount ?? detail.source_segments?.length ?? 0);
  portraitEls.memoryCount.textContent = String(memories.length);
  portraitEls.eventCount.textContent = String(events.length);
  renderPortraitOverview(detail);
  renderCore(detail.core || {});
  renderFacet(detail.facet || {});
  renderEvents(events);
  renderMemories(memories);
  updateRawJson("snapshot");
  setInspectorView(portraitState.activeInspectorView);
  syncPortraitSelection();
  window.CamoDemo.updateSharedLinks(portraitState.projectId, detail.name, detail.character_id);
}

async function loadProjectData() {
  const projectId = portraitEls.projectId.value.trim();
  if (!projectId) {
    portraitSetError("Project ID is required.");
    return;
  }

  portraitSetError("");
  portraitSetStatus("Loading project data...");
  window.CamoDemo.setLoading(portraitEls.loadProject, true, "Loading...");

  try {
    portraitState.projectId = projectId;
    const [sources, characters] = await Promise.all([
      window.CamoDemo.apiFetch(`/projects/${projectId}/texts`),
      window.CamoDemo.apiFetch(`/projects/${projectId}/characters`),
    ]);

    window.CamoDemo.fillSelect(
      portraitEls.sourceId,
      sources.map((item) => ({
        value: item.source_id,
        label: `${item.filename || item.source_id} · ${item.source_type}`,
      })),
      "Select a source",
    );
    window.CamoDemo.fillSelect(
      portraitEls.characterId,
      characters.map((item) => ({
        value: item.character_id,
        label: item.name,
      })),
      "Select a character",
    );

    if (sources.length && !portraitEls.sourceId.value) {
      portraitEls.sourceId.value = sources[0].source_id;
    }

    const normalizedName = portraitEls.characterName.value.trim().toLowerCase();
    const preferredCharacter =
      characters.length === 1
        ? characters[0]
        : characters.find((item) => item.name.trim().toLowerCase() === normalizedName);
    if (preferredCharacter) {
      portraitEls.characterId.value = preferredCharacter.character_id;
      await loadCharacterDetail();
      return;
    }
    portraitSetStatus(`Loaded ${sources.length} text source(s) and ${characters.length} character(s).`);
    window.CamoDemo.updateSharedLinks(projectId, portraitEls.characterName.value.trim(), "");
  } catch (error) {
    portraitSetError(error.message);
    portraitSetStatus("Project load failed.");
  } finally {
    window.CamoDemo.setLoading(portraitEls.loadProject, false, "Loading...");
  }
}

async function discoverDefaultProject() {
  portraitSetError("");
  portraitSetStatus("Looking for saved character data...");

  try {
    const projects = await window.CamoDemo.apiFetch("/projects");
    for (const project of projects) {
      const characters = await window.CamoDemo.apiFetch(`/projects/${project.project_id}/characters`);
      if (!characters.length) {
        continue;
      }

      portraitEls.projectId.value = project.project_id;
      if (!portraitEls.characterName.value.trim()) {
        portraitEls.characterName.value = characters[0].name;
      }
      await loadProjectData();
      return;
    }

    if (projects.length) {
      portraitEls.projectId.value = projects[0].project_id;
      portraitSetStatus("No saved character portrait found yet. Load a project to continue.");
      return;
    }

    portraitSetStatus("No saved projects found yet.");
  } catch (error) {
    portraitSetError(error.message);
    portraitSetStatus("Could not discover saved demo data.");
  }
}

async function loadCharacterDetail() {
  if (!portraitState.projectId || !portraitEls.characterId.value) {
    return;
  }

  portraitSetError("");
  portraitSetStatus("Loading character details...");
  portraitSetSkeleton(true);

  try {
    portraitState.characterId = portraitEls.characterId.value;
    const [detail, events, memories] = await Promise.all([
      window.CamoDemo.apiFetch(`/projects/${portraitState.projectId}/characters/${portraitState.characterId}`),
      window.CamoDemo.apiFetch(`/projects/${portraitState.projectId}/characters/${portraitState.characterId}/events`),
      window.CamoDemo.apiFetch(`/projects/${portraitState.projectId}/characters/${portraitState.characterId}/memories`),
    ]);
    portraitEls.characterName.value = detail.name;
    portraitEls.aliases.value = (detail.aliases || []).join(", ");
    renderPortrait(detail, events, memories);
    portraitSetStatus(`Loaded ${detail.name}.`);
  } catch (error) {
    portraitSetError(error.message);
    portraitSetStatus("Character load failed.");
  } finally {
    portraitSetSkeleton(false);
  }
}

async function generatePortrait() {
  const projectId = portraitEls.projectId.value.trim();
  const sourceId = portraitEls.sourceId.value;
  const name = portraitEls.characterName.value.trim();
  if (!projectId || !sourceId || !name) {
    portraitSetError("Project ID, source, and character name are required.");
    return;
  }

  portraitState.projectId = projectId;
  portraitState.sourceId = sourceId;
  portraitSetError("");
  portraitSetStatus(`Generating portrait for ${name}...`);
  portraitSetSkeleton(true);
  window.CamoDemo.setLoading(portraitEls.generatePortrait, true, "Generating...");

  try {
    const generated = await window.CamoDemo.apiFetch(
      `/projects/${projectId}/texts/${sourceId}/character-portrait`,
      {
        method: "POST",
        body: JSON.stringify({
          name,
          aliases: window.CamoDemo.toAliasList(portraitEls.aliases.value),
          max_segments: 10,
        }),
      },
    );
    const detail = await window.CamoDemo.apiFetch(`/projects/${projectId}/characters/${generated.character_id}`);
    renderPortrait(detail, generated.events, generated.memories, generated.processed_segments);
    portraitSetStatus(`Portrait ready for ${generated.name}.`);
  } catch (error) {
    portraitSetError(error.message);
    portraitSetStatus("Portrait generation failed.");
  } finally {
    portraitSetSkeleton(false);
    window.CamoDemo.setLoading(portraitEls.generatePortrait, false, "Generating...");
  }
}

async function copyJson() {
  try {
    await navigator.clipboard.writeText(portraitEls.jsonOutput.textContent);
    portraitSetStatus("JSON copied to clipboard.");
  } catch (_error) {
    portraitSetError("Could not copy JSON.");
  }
}

window.CamoDemo.hydrateProjectAndName(portraitEls.projectId, portraitEls.characterName);
window.CamoDemo.updateSharedLinks(
  portraitEls.projectId.value.trim(),
  portraitEls.characterName.value.trim(),
  "",
);

portraitEls.loadProject.addEventListener("click", loadProjectData);
portraitEls.generatePortrait.addEventListener("click", generatePortrait);
portraitEls.characterId.addEventListener("change", loadCharacterDetail);
portraitEls.copyJson.addEventListener("click", copyJson);
portraitEls.inspectorTabs.forEach((tab) => {
  tab.addEventListener("click", () => setInspectorView(tab.dataset.inspectorView));
});
portraitEls.jsonTabs.forEach((tab) => {
  tab.addEventListener("click", () => updateRawJson(tab.dataset.jsonView));
});

if (portraitEls.projectId.value.trim()) {
  loadProjectData();
} else {
  discoverDefaultProject();
}
