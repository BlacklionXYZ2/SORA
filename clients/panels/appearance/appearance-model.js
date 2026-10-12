// Appearance state with no DOM. These are UI preferences kept by SORA's desktop app on this PC
// (desktop-shell/preferences.json), never Core settings. The host reports them in host.preferences;
// the page keeps a draft and the values it loaded the draft from (the baseline), and saves both so
// the host can refuse a save when appearance was changed somewhere else in the meantime.

import { SHORTCUTS, THEMES, validAppearance } from "../shared/bridge.js";

export { SHORTCUTS, THEMES, validAppearance };

/** The seven preferences this page edits, in the host's field names. */
export const FIELD_KEYS = Object.freeze(["theme", "textScale", "shortcut", "chatCompact", "chatPinned",
  "showTechnicalDetail", "reducedMotion"]);

/** Panel text size, in whole percent: the classic window's 85–175 in steps of 5. */
export const TEXT_SCALE = Object.freeze({ min: 85, max: 175, step: 5 });

export const THEME_LABELS = Object.freeze({ Dark: "Dark", System: "System (Windows colours)" });
export const SHORTCUT_LABELS = Object.freeze({
  None: "None", CtrlAltSpace: "Ctrl+Alt+Space", CtrlAltS: "Ctrl+Alt+S",
});

/**
 * What each preference is called and what it really affects now that most panels are web pages.
 * `scope` is the short answer to "where does this apply?"; `help` says it in a sentence.
 */
export const FIELDS = Object.freeze([
  {
    key: "theme", group: "windows", kind: "choice", choices: THEMES, label: "Theme",
    scope: "Older windows only",
    help: "Applies to the older windows only: Note board, Content, Integrations and the Command menu. "
      + "Web panels such as this one keep SORA's glass look. Windows high contrast always wins.",
  },
  {
    key: "textScale", group: "windows", kind: "scale", label: "Panel text size", scope: "Every panel",
    help: "Applies to every panel: web panels zoom, and older windows change their font size.",
  },
  {
    key: "reducedMotion", group: "windows", kind: "toggle", label: "Reduced motion", scope: "Every panel",
    help: "Applies to every panel: web panels stop looping animations. If Windows itself is set to "
      + "show fewer animations, that still wins.",
  },
  {
    key: "shortcut", group: "chat", kind: "choice", choices: SHORTCUTS, label: "Chat shortcut",
    scope: "Chat",
    help: "Opens Chat from anywhere. With None, use the tray icon or the Command menu instead.",
  },
  {
    key: "chatCompact", group: "chat", kind: "toggle", label: "Use compact Chat", scope: "Chat's starting size",
    help: "Chat starts at 460 × 560 instead of 820 × 700 when it has no saved position, "
      + "or after Reset panel placement.",
  },
  {
    key: "chatPinned", group: "chat", kind: "toggle", label: "Pin Chat above other windows", scope: "Chat",
    help: "Keeps Chat above your other windows.",
  },
  {
    key: "showTechnicalDetail", group: "chat", kind: "toggle", label: "Show technical detail in Chat",
    scope: "Classic Chat only",
    help: "Only the classic Chat uses this (SORA started with -ClassicPanels). "
      + "The current Chat does not use it yet.",
  },
]);

export const GROUPS = Object.freeze([
  { id: "windows", title: "Every window" },
  { id: "chat", title: "Chat" },
]);

export function fieldByKey(key) { return FIELDS.find((field) => field.key === key); }

/** Shown in a browser preview, where there is no SORA app to ask. */
export const PREVIEW_TEXT = "Appearance works in SORA's app. These preferences are kept by SORA's desktop "
  + "app on this PC, so a browser preview cannot read or change them.";

// ---------- host.preferences ----------

function pick(values) {
  return Object.fromEntries(FIELD_KEYS.map((key) => [key, values[key]]));
}

function text(value) { return typeof value === "string" ? value : ""; }

/**
 * Read a host.preferences message. Returns null when its values are not the seven the page knows,
 * so a malformed message never becomes a draft.
 */
export function readPreferences(message) {
  const values = message?.values;
  if (!values || typeof values !== "object" || !validAppearance(pick(values))) return null;
  const legacy = message.legacy && typeof message.legacy === "object" ? message.legacy : {};
  const count = legacy.imported;
  return {
    revision: Number.isInteger(message.revision) && message.revision >= 0 ? message.revision : null,
    readOnly: message.readOnly === true,
    diagnostic: text(message.diagnostic).trim(),
    filePath: text(message.filePath).trim(),
    shortcutStatus: text(message.shortcutStatus).trim(),
    values: pick(values),
    legacy: {
      attempted: legacy.attempted === true,
      imported: Number.isInteger(count) && count >= 0 ? count : 0,
      invalid: legacy.invalid === true,
      topmostNotApplied: legacy.topmostNotApplied === true,
      quietOrTabRecorded: legacy.quietOrTabRecorded === true,
      legacyChatHint: legacy.legacyChatHint === true,
    },
  };
}

// ---------- draft ----------

export function sameValues(a, b) {
  return Boolean(a && b) && FIELD_KEYS.every((key) => a[key] === b[key]);
}

/** Keys whose value differs between two sets of values, in page order. */
export function changedKeys(a, b) {
  if (!a || !b) return [];
  return FIELD_KEYS.filter((key) => a[key] !== b[key]);
}

/** Nothing loaded yet. */
export function emptyState() {
  return { prefs: null, baseline: null, draft: null, changedElsewhere: false };
}

function loaded(prefs) {
  return { prefs, baseline: { ...prefs.values }, draft: { ...prefs.values }, changedElsewhere: false };
}

export function isDirty(state) { return changedKeys(state.draft, state.baseline).length > 0; }

/**
 * A new host.preferences arrived. A clean draft follows it; an unsaved draft is kept and only the
 * status is updated, as the classic window did. If the saved values now match the draft (our own
 * save, or the same change made elsewhere), there is nothing left to save.
 */
export function receive(state, prefs) {
  if (!prefs) return state;
  if (!state.draft || !isDirty(state)) return loaded(prefs);
  if (sameValues(prefs.values, state.draft)) {
    return { prefs, baseline: { ...prefs.values }, draft: state.draft, changedElsewhere: false };
  }
  // An unreadable file reports safe defaults, not a competing edit: the read-only notice covers it.
  return { ...state, prefs, changedElsewhere: !prefs.readOnly && !sameValues(prefs.values, state.baseline) };
}

/** Whole percent within 85–175, or null when the input is not a number yet. */
export function parseTextScale(raw) {
  const value = typeof raw === "number" ? raw : String(raw ?? "").replace("%", "").trim();
  if (value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return Math.min(TEXT_SCALE.max, Math.max(TEXT_SCALE.min, Math.round(number)));
}

/** The value an edit stores, or an error for a value the host would refuse. */
export function coerceValue(key, raw) {
  const field = fieldByKey(key);
  if (!field) throw new TypeError(`Unknown preference: ${key}`);
  if (field.kind === "choice") {
    if (!field.choices.includes(raw)) throw new TypeError(`${field.label}: choose one of the options.`);
    return raw;
  }
  if (field.kind === "scale") {
    const value = parseTextScale(raw);
    if (value === null) throw new TypeError(`${field.label}: enter a number from 85 to 175.`);
    return value;
  }
  if (typeof raw !== "boolean") throw new TypeError(`${field.label}: on or off.`);
  return raw;
}

export function edit(state, key, raw) {
  if (!state.draft) return state;
  return { ...state, draft: { ...state.draft, [key]: coerceValue(key, raw) } };
}

/** Drop the draft and show the saved values again. */
export function discard(state) { return state.prefs ? loaded(state.prefs) : emptyState(); }

/**
 * The exact prefs.save detail: the draft and the values it was loaded from, the seven fields each.
 * Throws rather than send something the host would drop.
 */
export function saveDetail(state) {
  const values = pick(state.draft ?? {});
  const baseline = pick(state.baseline ?? {});
  if (!validAppearance(values) || !validAppearance(baseline)) {
    throw new TypeError("These appearance values cannot be saved.");
  }
  return { values, baseline };
}

/** Why Save is not possible right now, or "" when it is. */
export function saveBlocked(state, { busy = false } = {}) {
  if (!state.prefs) return "Not loaded yet.";
  if (state.prefs.readOnly) return "Saving is off until the preferences file is recovered.";
  if (busy) return "Working…";
  if (!isDirty(state)) return "Nothing to save.";
  return "";
}

/**
 * The host said the save worked. It broadcasts host.preferences before it answers, so normally the
 * state is already clean; if that broadcast has not arrived, what was sent is what is saved.
 */
export function afterSave(state, sent) {
  if (state.prefs && sameValues(state.prefs.values, sent.values)) return loaded(state.prefs);
  return { ...state, baseline: { ...sent.values }, draft: { ...sent.values }, changedElsewhere: false };
}

/**
 * Appearance changed elsewhere while the owner was editing. Keep the owner's own edits and take
 * everything else from the latest saved values, then compare against those from now on.
 */
export function keepMine(state) {
  if (!state.prefs || !state.draft) return state;
  const draft = { ...state.prefs.values };
  for (const key of changedKeys(state.draft, state.baseline)) draft[key] = state.draft[key];
  return { prefs: state.prefs, baseline: { ...state.prefs.values }, draft, changedElsewhere: false };
}

/** What was changed elsewhere since the draft began: [{key, label, now, alsoEdited}]. */
export function elsewhereChanges(state) {
  if (!state.prefs) return [];
  const mine = new Set(changedKeys(state.draft, state.baseline));
  return changedKeys(state.prefs.values, state.baseline).map((key) => ({
    key, label: fieldByKey(key).label, now: valueLabel(key, state.prefs.values[key]), alsoEdited: mine.has(key),
  }));
}

/** True when the host's refusal is the appearance conflict (as opposed to a file or lock problem). */
export function isConflictError(error) {
  return /^Appearance changed\b/.test(text(error));
}

// ---------- labels ----------

export function valueLabel(key, value) {
  if (key === "theme") return THEME_LABELS[value] ?? String(value);
  if (key === "shortcut") return SHORTCUT_LABELS[value] ?? String(value);
  if (key === "textScale") return `${value} %`;
  return value ? "on" : "off";
}

export function changeSummary(state) {
  const count = changedKeys(state.draft, state.baseline).length;
  return count ? `${count} unsaved change${count === 1 ? "" : "s"}` : "";
}

/**
 * The host's shortcut sentence with friendly key names, and a tone for its pill. The host reports
 * what is registered now (the saved choice), never the unsaved draft.
 */
export function shortcutStatus(sentence) {
  const raw = text(sentence).trim();
  if (!raw) return { tone: "off", text: "SORA's app did not report the shortcut." };
  const friendly = raw.replace(/\bCtrlAltSpace\b/g, SHORTCUT_LABELS.CtrlAltSpace)
    .replace(/\bCtrlAltS\b/g, SHORTCUT_LABELS.CtrlAltS);
  const tone = /unavailable|conflict/i.test(raw) ? "bad" : /disabled/i.test(raw) ? "off"
    : /\bactive\b/i.test(raw) ? "ok" : "off";
  return { tone, text: friendly };
}

/** The file status, as the classic window showed it: revision, or the problem instead. */
export function fileStatus(prefs) {
  if (!prefs) return null;
  if (prefs.readOnly) {
    return {
      tone: "bad", label: "Needs attention",
      headline: "SORA could not read this file, so it is using safe defaults for now. "
        + "The file itself has not been changed.",
      detail: prefs.diagnostic,
    };
  }
  if (prefs.diagnostic) {
    return { tone: "bad", label: "Last change refused", headline: "The last change to this file did not go through.",
      detail: prefs.diagnostic };
  }
  return { tone: "ok", label: "Saved", headline: "",
    detail: prefs.revision === null ? "" : `Preferences revision ${prefs.revision}` };
}

/** What the one-time import from the older desktop apps did, in the classic window's terms. */
export function legacyLines(legacy) {
  if (!legacy) return [];
  const lines = [];
  if (!legacy.attempted) {
    lines.push("The one-time import from the older desktop apps has not run. "
      + "Recover the preferences file first.");
  } else if (legacy.imported > 0) {
    lines.push(`Settings from the older desktop apps were imported once (${legacy.imported} `
      + `file${legacy.imported === 1 ? "" : "s"}). The original files were kept, with byte-identical backups.`);
  } else {
    lines.push("SORA looked once for settings from the older desktop apps; there were none to import.");
  }
  if (legacy.invalid) lines.push("An older settings file could not be read and was ignored.");
  if (legacy.topmostNotApplied) {
    lines.push("The old widget was set to stay on top. That was not carried over: "
      + "turn on Pin Chat above other windows if you want it.");
  }
  if (legacy.quietOrTabRecorded) {
    lines.push("The old widget's quiet mode and tab choice were recorded only; nothing in SORA uses them now.");
  }
  if (legacy.legacyChatHint) {
    lines.push("The old Chat position did not record the display scaling, so Chat's first position "
      + "was a best guess, kept on screen.");
  }
  return lines;
}
