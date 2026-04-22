const chatState = {
  projectId: "",
  characterId: "",
  characterName: "",
  history: [],
  memoryCount: 0,
};

const chatEls = {
  projectId: document.getElementById("project-id"),
  characterId: document.getElementById("character-id"),
  loadProject: document.getElementById("load-project"),
  loadCharacter: document.getElementById("load-character"),
  statusLine: document.getElementById("status-line"),
  errorLine: document.getElementById("error-line"),
  characterHeading: document.getElementById("character-heading"),
  characterBadge: document.getElementById("character-badge"),
  characterSummary: document.getElementById("character-summary"),
  memoryCount: document.getElementById("memory-count"),
  chatToneText: document.getElementById("chat-tone-text"),
  chatTone: document.getElementById("chat-tone"),
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  sendChat: document.getElementById("send-chat"),
};

function chatSetStatus(message) {
  chatEls.statusLine.textContent = message;
}

function chatSetError(message) {
  chatEls.errorLine.textContent = message || "";
}

function buildChatMessage(role, content, extraClass = "") {
  const div = document.createElement("div");
  div.className = `chat-message ${role}${extraClass ? ` ${extraClass}` : ""}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = content;
  div.appendChild(paragraph);
  return div;
}

function scrollChatToBottom() {
  chatEls.chatLog.scrollTop = chatEls.chatLog.scrollHeight;
}

function appendChat(role, content) {
  const div = buildChatMessage(role, content);
  chatEls.chatLog.appendChild(div);
  scrollChatToBottom();
}

function resetChat() {
  chatState.history = [];
  chatEls.chatLog.innerHTML = "";
  const introMessage = chatState.characterName
    ? `You can now speak with ${chatState.characterName}.`
    : "Load a character first, then start the conversation.";
  chatEls.chatLog.appendChild(buildChatMessage("assistant", introMessage, "intro"));
  scrollChatToBottom();
}

function renderChatCharacter(detail, memories) {
  chatState.characterId = detail.character_id;
  chatState.characterName = detail.name;
  chatState.memoryCount = memories.length;
  chatEls.characterHeading.textContent = detail.name;
  chatEls.characterBadge.textContent = detail.aliases?.length ? detail.aliases.join(" · ") : "Ready to chat";
  chatEls.characterSummary.textContent =
    detail.description ||
    (detail.character_core?.motivation_profile?.primary || []).join(" · ") ||
    "Character loaded.";
  chatEls.memoryCount.textContent = String(memories.length);
  chatEls.chatToneText.textContent = detail.character_core?.communication_profile?.tone || "-";
  chatEls.chatTone.textContent = `${detail.name} active`;
  resetChat();
  window.CamoDemo.updateSharedLinks(chatState.projectId, detail.name, detail.character_id);
}

async function loadProjectData() {
  const projectId = chatEls.projectId.value.trim();
  if (!projectId) {
    chatSetError("Project ID is required.");
    return;
  }

  chatSetError("");
  chatSetStatus("Loading project data...");
  window.CamoDemo.setLoading(chatEls.loadProject, true, "Loading...");

  try {
    chatState.projectId = projectId;
    const characters = await window.CamoDemo.apiFetch(`/projects/${projectId}/characters`);
    window.CamoDemo.fillSelect(
      chatEls.characterId,
      characters.map((item) => ({
        value: item.character_id,
        label: item.name,
      })),
      "Select a character",
    );
    const params = new URLSearchParams(window.location.search);
    const preferredId = params.get("character_id");
    const preferredName = params.get("name")?.trim().toLowerCase();
    const preferredCharacter =
      characters.length === 1
        ? characters[0]
        : characters.find((item) => item.character_id === preferredId) ||
          characters.find((item) => item.name.trim().toLowerCase() === preferredName);
    if (preferredCharacter) {
      chatEls.characterId.value = preferredCharacter.character_id;
      await loadCharacter();
      return;
    }
    chatSetStatus(`Loaded ${characters.length} character(s).`);
    window.CamoDemo.updateSharedLinks(projectId, "", "");
  } catch (error) {
    chatSetError(error.message);
    chatSetStatus("Project load failed.");
  } finally {
    window.CamoDemo.setLoading(chatEls.loadProject, false, "Loading...");
  }
}

async function discoverDefaultProject() {
  chatSetError("");
  chatSetStatus("Looking for saved character data...");

  try {
    const projects = await window.CamoDemo.apiFetch("/projects");
    for (const project of projects) {
      const characters = await window.CamoDemo.apiFetch(`/projects/${project.project_id}/characters`);
      if (!characters.length) {
        continue;
      }

      chatEls.projectId.value = project.project_id;
      await loadProjectData();
      return;
    }

    if (projects.length) {
      chatEls.projectId.value = projects[0].project_id;
      chatSetStatus("No saved chat-ready character found yet. Load a project to continue.");
      return;
    }

    chatSetStatus("No saved projects found yet.");
  } catch (error) {
    chatSetError(error.message);
    chatSetStatus("Could not discover saved demo data.");
  }
}

async function loadCharacter() {
  if (!chatState.projectId || !chatEls.characterId.value) {
    chatSetError("Choose a character first.");
    return;
  }

  chatSetError("");
  chatSetStatus("Loading character for chat...");
  window.CamoDemo.setLoading(chatEls.loadCharacter, true, "Loading...");

  try {
    chatState.characterId = chatEls.characterId.value;
    const [detail, memories] = await Promise.all([
      window.CamoDemo.apiFetch(`/projects/${chatState.projectId}/characters/${chatState.characterId}`),
      window.CamoDemo.apiFetch(`/projects/${chatState.projectId}/characters/${chatState.characterId}/memories`),
    ]);
    renderChatCharacter(detail, memories);
    chatSetStatus(`Loaded ${detail.name} for chat.`);
  } catch (error) {
    chatSetError(error.message);
    chatSetStatus("Character load failed.");
  } finally {
    window.CamoDemo.setLoading(chatEls.loadCharacter, false, "Loading...");
  }
}

async function sendChat(event) {
  event.preventDefault();
  const message = chatEls.chatInput.value.trim();
  if (!message || !chatState.projectId || !chatState.characterId) {
    if (!chatState.characterId) {
      chatSetError("Load a character before sending a message.");
    }
    return;
  }

  appendChat("user", message);
  chatEls.chatInput.value = "";
  chatSetError("");
  window.CamoDemo.setLoading(chatEls.sendChat, true, "Sending...");

  try {
    const response = await window.CamoDemo.apiFetch(
      `/projects/${chatState.projectId}/characters/${chatState.characterId}/chat`,
      {
        method: "POST",
        body: JSON.stringify({
          message,
          history: chatState.history,
        }),
      },
    );
    chatState.history.push({ role: "user", content: message });
    chatState.history.push({ role: "assistant", content: response.reply });
    if (chatState.history.length > 16) {
      chatState.history = chatState.history.slice(-16);
    }
    appendChat("assistant", response.reply);
    const toneSummary = response.style_tags?.length ? response.style_tags.join(", ") : response.tone;
    chatEls.chatTone.textContent = `${toneSummary} · ${response.memory_count} memories`;
    chatEls.chatToneText.textContent = response.tone;
    chatEls.memoryCount.textContent = String(response.memory_count);
    chatSetStatus("Character response received.");
  } catch (error) {
    chatSetError(error.message);
    chatSetStatus("Chat request failed.");
  } finally {
    window.CamoDemo.setLoading(chatEls.sendChat, false, "Sending...");
  }
}

function handleChatInputKeydown(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) {
    return;
  }

  event.preventDefault();
  if (chatEls.sendChat.disabled) {
    return;
  }
  chatEls.chatForm.requestSubmit();
}

window.CamoDemo.hydrateProjectAndName(chatEls.projectId, null);
window.CamoDemo.updateSharedLinks(chatEls.projectId.value.trim(), "", "");

chatEls.loadProject.addEventListener("click", loadProjectData);
chatEls.loadCharacter.addEventListener("click", loadCharacter);
chatEls.chatForm.addEventListener("submit", sendChat);
chatEls.chatInput.addEventListener("keydown", handleChatInputKeydown);

if (chatEls.projectId.value.trim()) {
  loadProjectData();
} else {
  discoverDefaultProject();
}
