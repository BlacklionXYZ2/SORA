// Settings state with no DOM. Core's settings projection is authoritative: it lists every field
// with its category, group, type, effect tier and current value. The page keeps only a draft of
// the owner's unsaved edits and sends exactly those keys back with the revision it read.

/** Rail order from the concept (05-settings.jpg). Categories without fields are hidden. */
export const CATEGORIES = Object.freeze([
  { id: "General", icon: "general", blurb: "How SORA starts and talks to her model." },
  { id: "Appearance", icon: "appearance", blurb: "How she looks." },
  { id: "Models", icon: "models", blurb: "The local model SORA thinks with, and her agent colleagues." },
  { id: "Audio", icon: "audio", blurb: "Voice in and out: microphone, speakers and her voice." },
  { id: "Vision", icon: "vision", blurb: "What SORA may see on your screen, and when." },
  { id: "Memory", icon: "memory", blurb: "What SORA remembers." },
  { id: "Tools", icon: "tools", blurb: "What SORA may do on this PC, and where agents work." },
  { id: "Performance", icon: "performance", blurb: "GPU, batching and worker tuning." },
  { id: "Advanced", icon: "advanced", blurb: "Model server program, port and start-up limits." },
]);

const PATH_TYPES = new Set(["path-gguf", "path-exe", "path-dir", "path-file"]);
export const PICK_KIND = Object.freeze({
  "path-gguf": "gguf", "path-exe": "exe", "path-dir": "dir", "path-file": "file",
});

export function isPathType(type) { return PATH_TYPES.has(type); }

/** Categories that have at least one field, in rail order. */
export function visibleCategories(projection) {
  const used = new Set((projection?.fields ?? []).map((field) => field.category));
  return CATEGORIES.filter((category) => used.has(category.id));
}

/** Fields of one category split into ordinary groups and the folded "Advanced" ones. */
export function categoryGroups(projection, category) {
  const groups = new Map();
  const advanced = [];
  for (const field of projection?.fields ?? []) {
    if (field.category !== category) continue;
    if (field.advanced) { advanced.push(field); continue; }
    if (!groups.has(field.group)) groups.set(field.group, []);
    groups.get(field.group).push(field);
  }
  return { groups: [...groups].map(([name, fields]) => ({ name, fields })), advanced };
}

export function fieldByKey(projection, key) {
  return (projection?.fields ?? []).find((field) => field.key === key);
}

/** The value the page shows: the owner's draft if any, otherwise the saved value. */
export function shownValue(projection, draft, key) {
  if (Object.hasOwn(draft, key)) return draft[key];
  return fieldByKey(projection, key)?.value;
}

/**
 * Turn what an input holds into the value Core expects, or throw a readable error.
 * Text inputs give strings; Core wants numbers, booleans, null paths and so on.
 */
export function coerce(field, raw) {
  const label = field.label;
  switch (field.type) {
    case "bool":
      return Boolean(raw);
    case "int":
    case "float": {
      const text = String(raw ?? "").trim();
      const number = Number(text);
      if (text === "" || !Number.isFinite(number)) throw new Error(`${label}: enter a number.`);
      if (field.type === "int" && !Number.isInteger(number)) throw new Error(`${label}: enter a whole number.`);
      if (field.min !== undefined && number < field.min) throw new Error(`${label}: at least ${field.min}.`);
      if (field.max !== undefined && number > field.max) throw new Error(`${label}: at most ${field.max}.`);
      return number;
    }
    case "gpu": {
      const text = String(raw ?? "").trim().toLowerCase();
      if (text === "auto" || text === "all") return text;
      if (/^\d{1,3}$/.test(text)) return Number(text);
      throw new Error(`${label}: auto, all, or a number of layers (0–999).`);
    }
    case "enum": {
      if (!field.choices.includes(raw)) throw new Error(`${label}: choose one of the options.`);
      return raw;
    }
    case "agent-model-purposes": {
      if (!Array.isArray(raw)) throw new Error(`${label}: invalid list.`);
      return raw
        .map((row) => ({ id: String(row.id ?? "").trim(), purpose: String(row.purpose ?? "").trim() }))
        .filter((row) => row.id || row.purpose);
    }
    default: {
      const text = String(raw ?? "");
      // Optional paths are null when empty; Core rejects an empty path.
      if (isPathType(field.type) && text.trim() === "" && field.value === null) return null;
      return isPathType(field.type) ? text.trim() : text;
    }
  }
}

function same(a, b) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

/** Record an edit. Editing back to the saved value removes it from the draft. */
export function setDraft(projection, draft, key, value) {
  const next = { ...draft };
  const field = fieldByKey(projection, key);
  if (!field) return next;
  if (same(value, field.value)) delete next[key];
  else next[key] = value;
  return next;
}

/** The exact edit to send: only keys that differ from what Core has saved. */
export function changeSet(projection, draft) {
  const changes = {};
  for (const [key, value] of Object.entries(draft)) {
    const field = fieldByKey(projection, key);
    if (field && !same(value, field.value)) changes[key] = value;
  }
  return changes;
}

export function saveRequest(projection, draft) {
  return {
    version: projection.settings_version,
    expected_revision: projection.settings_revision,
    changes: changeSet(projection, draft),
  };
}

/**
 * After Core answers with a new projection (save, refresh or a conflict re-read), keep only the
 * draft edits that still differ from what is saved, so nothing the owner typed is lost.
 */
export function rebaseDraft(projection, draft) {
  return Object.fromEntries(Object.entries(changeSet(projection, draft)));
}

/** What saving would require: restart, model reload or nothing. */
export function effectOf(projection, draft) {
  const tiers = new Set(Object.keys(changeSet(projection, draft))
    .map((key) => fieldByKey(projection, key)?.tier));
  return { restart: tiers.has("next_boot"), reload: tiers.has("model_reload"),
    count: Object.keys(changeSet(projection, draft)).length };
}

export function fileName(path) {
  if (!path) return "";
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || String(path);
}

/** A model's display name: its file name without ".gguf". */
export function modelName(path) {
  return fileName(path).replace(/\.gguf$/i, "");
}

export function folderName(path) {
  if (!path) return "";
  const parts = String(path).split(/[\\/]/);
  return parts.slice(0, -1).join("\\");
}

const STATES = {
  ready: { label: "Loaded", tone: "ok", note: "Ready for conversation" },
  reloading: { label: "Loading…", tone: "warn", note: "The model is loading" },
  down: { label: "Not loaded", tone: "down", note: "Choose a model, then Save and reload" },
};

/**
 * The Models summary card. Only values Core supplies: the model file SORA is actually using
 * (active value), its state, and whether a different file is saved for the next reload.
 */
export function brainSummary(projection) {
  const backend = fieldByKey(projection, "dialogue.backend");
  const model = fieldByKey(projection, "llama.model_path");
  const projector = fieldByKey(projection, "llama.mmproj_path");
  const managed = backend?.active_value === "managed-llama";
  const state = STATES[projection?.model_state] ?? { label: String(projection?.model_state ?? "Unknown"),
    tone: "warn", note: "" };
  const active = model?.active_value ?? null;
  const saved = model?.value ?? null;
  return {
    managed,
    source: backend?.active_value ?? "unknown",
    title: managed ? (modelName(active) || "No model loaded") : sourceLabel(backend?.active_value),
    path: managed ? (active ?? "") : "",
    projector: managed ? fileName(projector?.active_value) : "",
    state: managed ? state : { label: "Not used", tone: "warn", note: "" },
    error: projection?.model_error || "",
    nextModel: managed && saved && saved !== active ? saved : "",
    canReload: Boolean(projection?.can_reload),
    reloadRequired: Boolean(projection?.model_reload_required),
  };
}

export function sourceLabel(backend) {
  return {
    "managed-llama": "Local (llama.cpp)",
    "openai-compatible": "External server",
    deterministic: "None (test replies)",
  }[backend] ?? String(backend ?? "Unknown");
}

/** Information tiles for Models, built only from values Core reports as active. */
export function brainTiles(projection) {
  const active = (key) => fieldByKey(projection, key)?.active_value;
  const tiles = [];
  const add = (label, value, note = "") => {
    if (value === null || value === undefined || value === "") return;
    tiles.push({ label, value: String(value), note });
  };
  add("Context length", active("llama.context_size") ? `${Number(active("llama.context_size")).toLocaleString("en-GB")} tokens` : "");
  add("GPU offload", active("llama.gpu_layers"), "layers on the GPU");
  add("Flash attention", active("llama.flash_attn"));
  const k = active("llama.cache_type_k"), v = active("llama.cache_type_v");
  if (k || v) add("KV cache", k === v ? String(k).toUpperCase() : `K ${k} · V ${v}`);
  const spec = active("llama.speculative.type");
  add("Speculative decoding", spec === "none" ? "Off" : spec);
  add("Vision projector", fileName(active("llama.mmproj_path")) || "None", "for seeing the screen");
  return tiles;
}

/** llama.cpp arguments Core captured for the running model, for display and copying. */
export function launchText(projection) {
  const argv = projection?.launch_details?.active?.argv;
  return Array.isArray(argv) && argv.length ? argv.join(" ") : "";
}

// ---------- Vision detail: one slider over llama.cpp's image arguments ----------

/** Mirrors Core's presets (src/sora/providers/vision_detail.py); Core re-applies them on save. */
export const VISION_LEVELS = Object.freeze({
  low: { "llama.image_max_tokens": 280, "llama.ubatch_size": 512, "llama.context_size": 8192 },
  medium: { "llama.image_max_tokens": 1024, "llama.ubatch_size": 1024, "llama.context_size": 12288 },
  high: { "llama.image_max_tokens": 2048, "llama.ubatch_size": 2048, "llama.context_size": 16384 },
});
export const VISION_ORDER = Object.freeze(["low", "medium", "high"]);
export const VISION_DETAIL_KEY = "llama.vision_detail";
export const VISION_ARGUMENT_KEYS = Object.freeze(Object.keys(VISION_LEVELS.low));
export const VISION_DISCLAIMER = "Higher detail increases response times and context usage, "
  + "but SORA reads your screen more reliably and guesses less.";

/** The level the page shows, and the arguments it stands for. */
export function visionDetail(projection, draft) {
  const level = shownValue(projection, draft, VISION_DETAIL_KEY) ?? "custom";
  const values = Object.fromEntries(VISION_ARGUMENT_KEYS.map((key) => [key, shownValue(projection, draft, key)]));
  return { level, values, index: VISION_ORDER.indexOf(level) };
}

/** Choosing a level on the slider sets its three arguments in the draft. */
export function chooseVisionLevel(projection, draft, level) {
  let next = setDraft(projection, draft, VISION_DETAIL_KEY, level);
  for (const [key, value] of Object.entries(VISION_LEVELS[level] ?? {})) {
    next = setDraft(projection, next, key, value);
  }
  const batch = shownValue(projection, next, "llama.batch_size");
  const ubatch = shownValue(projection, next, "llama.ubatch_size");
  if (typeof batch === "number" && typeof ubatch === "number" && batch < ubatch) {
    next = setDraft(projection, next, "llama.batch_size", ubatch);
  }
  return next;
}

/** Editing one of the level's arguments by hand turns the level into custom. */
export function afterVisionArgumentEdit(projection, draft, key) {
  if (!VISION_ARGUMENT_KEYS.includes(key)) return draft;
  const { level, values } = visionDetail(projection, draft);
  const preset = VISION_LEVELS[level];
  if (!preset || VISION_ARGUMENT_KEYS.every((name) => values[name] === preset[name])) return draft;
  return setDraft(projection, draft, VISION_DETAIL_KEY, "custom");
}
