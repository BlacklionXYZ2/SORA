// Motion window state with no DOM. Two sources, both from Core:
// - the settings projection (`motion.*` fields): what is saved and what is running;
// - the motion catalogue (GET /api/v1/motion/catalog): which engines, versions and sizes exist in
//   motion-lab, how each measured, and its preview clip.
// The page keeps a draft of the owner's choice and saves exactly the changed `motion.*` keys.

export const KEYS = Object.freeze({
  engine: "motion.engine",
  precision: "motion.ardy_precision",
  steps: "motion.ardy_steps",
  version: "motion.custom_version",
  size: "motion.custom_size",
});

export const ENGINE_ICONS = Object.freeze({ algorithmic: "gear", ardy: "bolt", custom: "cube" });

/** The saved choice, from the settings projection's fields (null when it lacks them). */
export function savedChoice(projection) {
  const fields = new Map((projection?.fields ?? []).map((field) => [field.key, field]));
  const choice = {};
  for (const [name, key] of Object.entries(KEYS)) {
    if (!fields.has(key)) return null;
    choice[name] = fields.get(key).value;
  }
  return choice;
}

/** What her player is using now (the values it started with), or null. */
export function activeChoice(projection) {
  const fields = new Map((projection?.fields ?? []).map((field) => [field.key, field]));
  const choice = {};
  for (const [name, key] of Object.entries(KEYS)) {
    if (!fields.has(key)) return null;
    choice[name] = fields.get(key).active_value;
  }
  return choice;
}

export function engineEntry(catalog, id) {
  return (catalog?.engines ?? []).find((engine) => engine.id === id) ?? null;
}

/** Custom versions in order (v1, v2, …), each with its sizes. */
export function customVersions(catalog) {
  const models = engineEntry(catalog, "custom")?.models ?? [];
  const versions = new Map();
  for (const model of models) {
    if (!versions.has(model.version)) versions.set(model.version, []);
    versions.get(model.version).push(model);
  }
  const number = (v) => Number(v.replace(/^v/, ""));
  return [...versions.entries()].sort((a, b) => number(a[0]) - number(b[0]))
    .map(([version, sizes]) => ({ version, sizes: sizes.sort((a, b) => sizeValue(a.size) - sizeValue(b.size)) }));
}

export function sizeValue(size) {
  const match = /^([0-9.]+)([MB])$/.exec(size ?? "");
  return match ? Number(match[1]) * (match[2] === "B" ? 1000 : 1) : Infinity;
}

export const SELECTABLE = new Set(["ready", "experimental"]);

/** The catalogue model a choice points at (or null). */
export function selectedModel(catalog, choice) {
  if (!choice) return null;
  const engine = engineEntry(catalog, choice.engine);
  if (!engine) return null;
  if (choice.engine === "algorithmic") return engine.models[0] ?? null;
  if (choice.engine === "ardy") {
    return engine.models.find((m) => m.version === `Core ${choice.precision}`) ?? null;
  }
  return engine.models.find((m) => m.version === choice.version && m.size === choice.size) ?? null;
}

/** Whether the draft can be saved: its model exists and isn't missing or planned. */
export function choiceUsable(catalog, choice) {
  const model = selectedModel(catalog, choice);
  return Boolean(model && SELECTABLE.has(model.state));
}

/** Pick a version: keep the size when that version has it ready, else its smallest usable size. */
export function withVersion(catalog, choice, version) {
  const sizes = customVersions(catalog).find((v) => v.version === version)?.sizes ?? [];
  const usable = sizes.filter((m) => SELECTABLE.has(m.state));
  const size = usable.some((m) => m.size === choice.size) ? choice.size : usable[0]?.size ?? choice.size;
  return { ...choice, engine: "custom", version, size };
}

export function changes(saved, draft) {
  const result = {};
  if (!saved || !draft) return result;
  for (const [name, key] of Object.entries(KEYS)) {
    if (draft[name] !== saved[name]) result[key] = draft[name];
  }
  return result;
}

export function saveRequest(projection, saved, draft) {
  return { version: projection.settings_version, expected_revision: projection.settings_revision,
    changes: changes(saved, draft) };
}

export function sameChoice(a, b) {
  return Boolean(a && b) && Object.keys(KEYS).every((name) => a[name] === b[name]);
}

export function choiceLabel(catalog, choice) {
  if (!choice) return "";
  if (choice.engine === "algorithmic") return "Algorithmic (built-in)";
  if (choice.engine === "ardy") return `ARDY Core, ${choice.precision}, ${choice.steps} steps`;
  return `Custom ${choice.version}, ${choice.size}`;
}

export const STATE_LABELS = Object.freeze({
  ready: "Ready", experimental: "Experimental", missing: "Missing files", planned: "Planned",
});

// ---------- measurements ----------

/** Rows for the comparison: the model's value beside the recordings', with bar widths scaled to
 * the largest value any catalogued model (or the recordings) has for that measure. */
export const MEASURES = Object.freeze([
  { key: "outside_limits_share", label: "Joints outside human range", unit: "%", scale: 100, better: "lower" },
  { key: "foot_slide_m_s", label: "Foot sliding", unit: "m/s", scale: 1, better: "lower" },
  { key: "energy_rad_s", label: "Liveliness (joint speed)", unit: "rad/s", scale: 1, better: "closer" },
  { key: "walk_speed_m_s", label: "Walking speed", unit: "m/s", scale: 1, better: "closer" },
  { key: "step_latency_ms", label: "Time per replan", unit: "ms", scale: 1, better: "lower" },
  { key: "video_memory_gb", label: "Video memory", unit: "GB", scale: 1, better: "lower" },
]);

export function measureRows(catalog, model) {
  const all = (catalog?.engines ?? []).flatMap((engine) => engine.models).map((m) => m.measures ?? {});
  const recordings = catalog?.recordings ?? {};
  return MEASURES.map((measure) => {
    const value = model?.measures?.[measure.key];
    if (value === null || value === undefined) return null;
    const pool = [...all.map((m) => m[measure.key]), recordings[measure.key]]
      .filter((v) => typeof v === "number");
    const max = Math.max(...pool, value, 1e-9);
    const reference = recordings[measure.key];
    return {
      ...measure, value, reference: typeof reference === "number" ? reference : null,
      width: Math.min(1, value / max),
      referenceWidth: typeof reference === "number" ? Math.min(1, reference / max) : null,
      text: format(value, measure), referenceText: typeof reference === "number" ? format(reference, measure) : "",
    };
  }).filter(Boolean);
}

export function format(value, measure) {
  const scaled = value * measure.scale;
  const digits = measure.unit === "ms" ? 0 : scaled < 0.1 ? 3 : scaled < 10 ? 2 : 1;
  return `${scaled.toFixed(digits)} ${measure.unit}`;
}

// ---------- preview ----------

/** Validated preview clip: frames of joint positions in metres, or null. */
export function readPreview(data) {
  if (!data || typeof data !== "object") return null;
  const names = data.joint_names, parents = data.joint_parents, frames = data.frames;
  if (!Array.isArray(names) || !Array.isArray(parents) || names.length !== parents.length) return null;
  if (!Array.isArray(frames) || !frames.length) return null;
  const joints = names.length;
  const fps = Number(data.fps);
  if (!Number.isFinite(fps) || fps <= 0 || fps > 120) return null;
  const out = [];
  for (const frame of frames) {
    if (!Array.isArray(frame) || frame.length !== joints * 3) return null;
    const points = [];
    for (let j = 0; j < joints; j += 1) {
      points.push([frame[3 * j] / 1000, frame[3 * j + 1] / 1000, frame[3 * j + 2] / 1000]);
    }
    out.push(points);
  }
  return { label: String(data.label ?? ""), fps, names, parents: parents.map(Number), frames: out };
}

/** Screen position of a point for a three-quarter view that follows the root horizontally. */
export function project([x, y, z], root, { yaw = 0.6, pitch = 0.18, scale = 1, cx = 0, cy = 0 } = {}) {
  const dx = x - root[0], dz = z - root[2];
  const rx = dx * Math.cos(yaw) - dz * Math.sin(yaw);
  const rz = dx * Math.sin(yaw) + dz * Math.cos(yaw);
  const sy = y * Math.cos(pitch) - rz * Math.sin(pitch);
  return [cx + rx * scale, cy - sy * scale];
}

/**
 * The motion supervisor's status (GET /api/v1/motion/status) as a banner: its text, its kind
 * ("" | "warn" | "error") and whether it is still changing (poll again soon).
 */
export function statusNotice(status, catalog) {
  if (!status) return null;
  const name = status.engine === "algorithmic" ? "the algorithmic system"
    : engineEntry(catalog, status.engine)?.name ?? status.engine;
  switch (status.state) {
    case "unavailable":
      return { text: status.error || "This Core has no motion engine.", kind: "warn", busy: false };
    case "starting":
      return { text: `Starting ${name}. She keeps moving by herself meanwhile, and her last few `
        + "seconds are recorded so the model carries on from what she was doing.", kind: "", busy: true };
    case "handover":
      return { text: `Handing her over to ${name}…`, kind: "", busy: true };
    case "running": {
      const load = typeof status.load_seconds === "number" ? ` (loaded in ${status.load_seconds.toFixed(1)} s)` : "";
      const player = status.player_connected ? "" : " Her avatar player isn't connected, so nothing is shown yet.";
      return { text: `${name} is moving her${load}.${player}`, kind: status.player_connected ? "" : "warn", busy: false };
    }
    case "failed":
      return { text: `${name} couldn't start: ${status.error || "unknown error"}. `
        + "She keeps moving with the algorithmic system.", kind: "error", busy: false };
    default:
      return { text: "She moves with the algorithmic system.", kind: "", busy: false };
  }
}
