(function () {
  function currentQuery() {
    return document.body.dataset.query || "";
  }

  function buildPageUrl(path, params = new URLSearchParams(window.location.search)) {
    const query = params.toString();
    return query ? `${path}?${query}` : path;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  async function apiFetch(path, options = {}) {
    const apiPrefix = document.body.dataset.apiPrefix;
    const response = await fetch(`${apiPrefix}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    if (!response.ok) {
      let detail = `Request failed with ${response.status}`;
      try {
        const payload = await response.json();
        detail = payload.detail || detail;
      } catch (_error) {
        detail = await response.text();
      }
      throw new Error(detail);
    }

    if (response.status === 204) {
      return null;
    }
    return response.json();
  }

  function setLoading(button, loading, text) {
    button.disabled = loading;
    button.dataset.originalText = button.dataset.originalText || button.textContent;
    button.textContent = loading ? text : button.dataset.originalText;
  }

  function fillSelect(select, items, placeholder) {
    select.innerHTML = "";
    const first = document.createElement("option");
    first.value = "";
    first.textContent = placeholder;
    select.appendChild(first);
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      select.appendChild(option);
    });
  }

  function toAliasList(text) {
    return text
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function hydrateProjectAndName(projectInput, nameInput) {
    const params = new URLSearchParams(window.location.search);
    const storedProject = localStorage.getItem("camo-demo-project-id");
    if (projectInput) {
      projectInput.value = params.get("project_id") || storedProject || "";
    }
    if (nameInput) {
      nameInput.value = params.get("name") || "";
    }
  }

  function updateSharedLinks(projectId, name, characterId) {
    const params = new URLSearchParams();
    if (projectId) {
      params.set("project_id", projectId);
      localStorage.setItem("camo-demo-project-id", projectId);
    }
    if (name) {
      params.set("name", name);
    }
    if (characterId) {
      params.set("character_id", characterId);
    }

    const portraitHref = buildPageUrl("/demo/portrait", params);
    const chatHref = buildPageUrl("/demo/chat", params);
    const portraitTargets = ["portrait-link", "open-inspector-link", "nav-inspector-link"];
    const chatTargets = ["chat-link", "open-chat-link", "nav-chat-link"];

    portraitTargets.forEach((id) => {
      const node = document.getElementById(id);
      if (node) {
        node.href = portraitHref;
      }
    });
    chatTargets.forEach((id) => {
      const node = document.getElementById(id);
      if (node) {
        node.href = chatHref;
      }
    });
  }

  window.CamoDemo = {
    apiFetch,
    buildPageUrl,
    currentQuery,
    escapeHtml,
    fillSelect,
    hydrateProjectAndName,
    setLoading,
    toAliasList,
    updateSharedLinks,
  };
})();
