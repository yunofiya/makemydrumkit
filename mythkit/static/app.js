(() => {
  const state = {
    producerName: "",
    worldText: "",
    stashMode: false,
    projectsRoot: "",
    selectedFolders: new Set(),
    libraryRoots: "",
    outputRoot: "",
    useAudioAnalysis: true,
    useAudioDedupe: true,
  };

  const screens = {
    splash: document.getElementById("screen-splash"),
    name: document.getElementById("screen-name"),
    mode: document.getElementById("screen-mode"),
    world: document.getElementById("screen-world"),
    source: document.getElementById("screen-source"),
    processing: document.getElementById("screen-processing"),
    results: document.getElementById("screen-results"),
  };

  function goTo(key) {
    Object.values(screens).forEach((s) => s.classList.remove("active"));
    screens[key].classList.add("active");
  }

  // ---------- Screen 0: splash ----------
  document.getElementById("btn-start").addEventListener("click", () => goTo("name"));

  // ---------- Screen 1: name ----------
  const inputName = document.getElementById("input-name");
  const btnNameNext = document.getElementById("btn-name-next");
  inputName.addEventListener("input", () => {
    btnNameNext.disabled = inputName.value.trim().length === 0;
  });
  inputName.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !btnNameNext.disabled) btnNameNext.click();
  });
  btnNameNext.addEventListener("click", () => {
    state.producerName = inputName.value.trim();
    goTo("mode");
  });

  // ---------- Screen 1.5: mode (themed vs stash) ----------
  const modeThemed = document.getElementById("mode-themed");
  const modeStash = document.getElementById("mode-stash");
  const btnModeNext = document.getElementById("btn-mode-next");
  const sourceStepLabel = document.getElementById("source-step-label");
  let modeChosen = null;

  function selectMode(mode) {
    modeChosen = mode;
    modeThemed.classList.toggle("selected", mode === "themed");
    modeStash.classList.toggle("selected", mode === "stash");
    btnModeNext.disabled = false;
  }
  modeThemed.addEventListener("click", () => selectMode("themed"));
  modeStash.addEventListener("click", () => selectMode("stash"));

  btnModeNext.addEventListener("click", () => {
    state.stashMode = modeChosen === "stash";
    if (state.stashMode) {
      state.worldText = "";
      sourceStepLabel.textContent = "// STEP 03";
      goTo("source");
    } else {
      goTo("world");
    }
  });

  // ---------- Screen 2: world ----------
  const inputWorld = document.getElementById("input-world");
  const btnWorldNext = document.getElementById("btn-world-next");
  inputWorld.addEventListener("input", () => {
    btnWorldNext.disabled = inputWorld.value.trim().length === 0;
  });
  btnWorldNext.addEventListener("click", () => {
    state.worldText = inputWorld.value.trim();
    sourceStepLabel.textContent = "// STEP 04";
    goTo("source");
  });

  // ---------- Screen 3: source ----------
  const inputProjectsRoot = document.getElementById("input-projects-root");
  const inputLibraryRoots = document.getElementById("input-library-roots");
  const inputOutputRoot = document.getElementById("input-output-root");
  const btnScan = document.getElementById("btn-scan");
  const folderListWrap = document.getElementById("folder-list-wrap");
  const folderList = document.getElementById("folder-list");
  const folderCountLabel = document.getElementById("folder-count-label");
  const btnBuild = document.getElementById("btn-build");
  const sourceError = document.getElementById("source-error");
  const toggleAudioAnalysis = document.getElementById("toggle-audio-analysis");
  const toggleAudioDedupe = document.getElementById("toggle-audio-dedupe");

  function showSourceError(msg) {
    sourceError.textContent = msg;
    sourceError.classList.toggle("hidden", !msg);
  }

  function updateBuildEnabled() {
    btnBuild.disabled = state.selectedFolders.size === 0 || !inputOutputRoot.value.trim();
  }

  btnScan.addEventListener("click", async () => {
    const root = inputProjectsRoot.value.trim();
    if (!root) return;
    showSourceError("");
    btnScan.disabled = true;
    btnScan.textContent = "SCANNING...";
    try {
      const resp = await fetch(`/api/list-project-folders?root=${encodeURIComponent(root)}`);
      const data = await resp.json();
      if (!resp.ok) {
        showSourceError(data.error || "Scan failed.");
        folderListWrap.classList.add("hidden");
        return;
      }
      state.projectsRoot = data.root;
      state.selectedFolders = new Set(data.folders.map((f) => f.name));

      folderList.innerHTML = "";
      data.folders.forEach((f) => {
        const row = document.createElement("div");
        row.className = "folder-row";
        row.innerHTML = `
          <label>
            <input type="checkbox" checked data-folder="${escapeHtml(f.name)}" />
            <span>${escapeHtml(f.name)}</span>
          </label>
          <span class="count">${f.flp_count} .flp</span>
        `;
        const checkbox = row.querySelector("input");
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) state.selectedFolders.add(f.name);
          else state.selectedFolders.delete(f.name);
          updateBuildEnabled();
        });
        folderList.appendChild(row);
      });

      folderCountLabel.textContent = `${data.folders.length} FOLDERS FOUND`;
      folderListWrap.classList.remove("hidden");
      updateBuildEnabled();
    } catch (err) {
      showSourceError("Could not reach the server.");
    } finally {
      btnScan.disabled = false;
      btnScan.textContent = "SCAN";
    }
  });

  document.getElementById("select-all").addEventListener("click", (e) => {
    e.preventDefault();
    folderList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.checked = true;
      state.selectedFolders.add(cb.dataset.folder);
    });
    updateBuildEnabled();
  });
  document.getElementById("select-none").addEventListener("click", (e) => {
    e.preventDefault();
    folderList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.checked = false;
      state.selectedFolders.delete(cb.dataset.folder);
    });
    updateBuildEnabled();
  });

  inputOutputRoot.addEventListener("input", updateBuildEnabled);

  const processingMessages = [
    "PARSING PROJECT FILES...",
    "INDEXING SAMPLE LIBRARY...",
    "RANKING YOUR MOST-USED SOUNDS...",
    "REMOVING DUPLICATES...",
    "NAMING EACH SOUND...",
    "COMPILING KIT...",
  ];
  let processingInterval = null;

  function startProcessingAnimation() {
    const el = document.getElementById("processing-text");
    let i = 0;
    el.textContent = processingMessages[0];
    processingInterval = setInterval(() => {
      i = (i + 1) % processingMessages.length;
      el.textContent = processingMessages[i];
    }, 1400);
  }

  function stopProcessingAnimation() {
    if (processingInterval) clearInterval(processingInterval);
    processingInterval = null;
  }

  btnBuild.addEventListener("click", async () => {
    showSourceError("");
    goTo("processing");
    startProcessingAnimation();

    const payload = {
      producer_name: state.producerName,
      world_text: state.worldText,
      projects_root: state.projectsRoot,
      selected_folders: Array.from(state.selectedFolders),
      library_roots: inputLibraryRoots.value.trim(),
      output_root: inputOutputRoot.value.trim(),
      use_audio_analysis: toggleAudioAnalysis.checked,
      use_audio_dedupe: toggleAudioDedupe.checked,
      stash_mode: state.stashMode,
    };

    try {
      const resp = await fetch("/api/build-kit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      stopProcessingAnimation();
      if (!resp.ok) {
        goTo("source");
        showSourceError(data.error || "Build failed.");
        return;
      }
      renderResults(data);
      goTo("results");
    } catch (err) {
      stopProcessingAnimation();
      goTo("source");
      showSourceError("Could not reach the server.");
    }
  });

  // ---------- Screen 5: results ----------
  let lastOutputPath = "";

  function renderResults(data) {
    document.getElementById("results-kit-name").textContent = data.kit_name.toUpperCase();
    document.getElementById("results-path").textContent = data.output_path;
    document.getElementById("results-mode-badge").textContent = data.stash_mode
      ? "STASH — ORIGINAL FILENAMES"
      : "THEMED — RENAMED";
    lastOutputPath = data.output_path;

    const stats = [
      { num: data.total_unique, label: "sounds in kit" },
      { num: data.total_flps_scanned, label: "beats scanned" },
      { num: data.total_unique_samples_resolved, label: "unique samples found" },
      { num: data.total_missing_refs, label: "refs missing" },
    ];
    const statsRow = document.getElementById("stats-row");
    statsRow.innerHTML = stats
      .map((s) => `<div class="stat"><div class="num">${s.num}</div><div class="label">${s.label}</div></div>`)
      .join("");

    const wrap = document.getElementById("categories-wrap");
    wrap.innerHTML = "";
    Object.values(data.categories).forEach((cat, idx) => {
      const card = document.createElement("div");
      card.className = "category-card" + (idx === 0 ? " open" : "");
      const soundsHtml = cat.sounds
        .map((s) => {
          const shown = s.used_in.slice(0, 3).map(escapeHtml).join(", ");
          const more = s.used_in.length > 3 ? ` +${s.used_in.length - 3} more` : "";
          return `
          <div class="sound-row">
            <div class="new-name">${escapeHtml(s.new_name)}</div>
            <div class="orig-name">was: ${escapeHtml(s.original_name)}${s.resolution_method === "library_search" ? " · found via library search" : ""}</div>
            <div class="usage">used ${s.usage_count}x · ${formatRecency(s.days_since_last_used)}${shown ? " · " + shown + more : ""}</div>
          </div>`;
        })
        .join("");

      card.innerHTML = `
        <div class="category-head">
          <span class="tag">${escapeHtml(cat.tag)}</span>
          <span class="count">${cat.count} / ${data.max_per_category}${cat.duplicates_skipped ? ` · ${cat.duplicates_skipped} dupes skipped` : ""}</span>
        </div>
        <div class="category-body">${soundsHtml || '<p class="step-hint">No sounds found for this category.</p>'}</div>
      `;
      card.querySelector(".category-head").addEventListener("click", () => {
        card.classList.toggle("open");
      });
      wrap.appendChild(card);
    });
  }

  document.getElementById("btn-reveal").addEventListener("click", async () => {
    if (!lastOutputPath) return;
    await fetch("/api/reveal-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: lastOutputPath }),
    });
  });

  document.getElementById("btn-restart").addEventListener("click", () => {
    goTo("splash");
  });

  function formatRecency(days) {
    if (days === null || days === undefined) return "unknown date";
    if (days <= 0) return "today";
    if (days === 1) return "1 day ago";
    if (days < 30) return `${days} days ago`;
    if (days < 60) return "~1 month ago";
    if (days < 365) return `~${Math.round(days / 30)} months ago`;
    const years = days / 365;
    return years < 1.5 ? "~1 year ago" : `~${Math.round(years)} years ago`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
