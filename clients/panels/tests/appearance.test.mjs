import assert from "node:assert/strict";
import { test } from "node:test";

import { hostRequest, send, validAppearance } from "../shared/bridge.js";
import {
  FIELDS, FIELD_KEYS, GROUPS, PREVIEW_TEXT, SHORTCUTS, THEMES, afterSave, changeSummary, changedKeys,
  coerceValue, discard, edit, elsewhereChanges, emptyState, fileStatus, isConflictError, isDirty,
  keepMine, legacyLines, parseTextScale, readPreferences, receive, saveBlocked, saveDetail,
  shortcutStatus, valueLabel,
} from "../appearance/appearance-model.js";

// What ShellHost.PreferencesMessage sends (camelCase, as WebPanelForm serialises it).
function hostMessage(values = {}, extra = {}) {
  return {
    type: "host.preferences", revision: 7, readOnly: false, diagnostic: "",
    filePath: "C:\\Users\\owner\\AppData\\Local\\SORA\\desktop-shell\\preferences.json",
    shortcutStatus: "Chat shortcut active: CtrlAltSpace",
    values: { theme: "Dark", textScale: 100, shortcut: "CtrlAltSpace", chatCompact: false, chatPinned: false,
      showTechnicalDetail: false, reducedMotion: true, ...values },
    legacy: { attempted: true, imported: 0, invalid: false, topmostNotApplied: false, quietOrTabRecorded: false,
      legacyChatHint: false },
    ...extra,
  };
}
const prefs = (values, extra) => readPreferences(hostMessage(values, extra));
const loadedState = (values, extra) => receive(emptyState(), prefs(values, extra));

test("every preference the classic window edited is here, with what it really affects", () => {
  assert.deepEqual(FIELDS.map((field) => field.key).sort(), [...FIELD_KEYS].sort());
  assert.deepEqual(GROUPS.map((group) => group.id), ["windows", "chat"]);
  for (const field of FIELDS) {
    assert.ok(GROUPS.some((group) => group.id === field.group), field.key);
    assert.ok(field.label && field.scope && field.help.endsWith("."), field.key);
  }
  const scope = Object.fromEntries(FIELDS.map((field) => [field.key, field.scope]));
  assert.equal(scope.textScale, "Every panel");
  assert.equal(scope.reducedMotion, "Every panel");
  assert.equal(scope.theme, "Older windows only");
  assert.equal(scope.showTechnicalDetail, "Classic Chat only");
  const help = Object.fromEntries(FIELDS.map((field) => [field.key, field.help]));
  // Theme never claims to restyle web panels; high contrast always wins.
  assert.match(help.theme, /older windows only: Note board, Content, Integrations and the Command menu/);
  assert.match(help.theme, /keep SORA's glass look.*high contrast always wins/);
  assert.match(help.textScale, /every panel: web panels zoom, and older windows change their font size/);
  assert.match(help.reducedMotion, /stop looping animations.*Windows itself.*still wins/);
  assert.match(help.chatCompact, /460 × 560 instead of 820 × 700 when it has no saved position/);
  assert.match(help.showTechnicalDetail, /Only the classic Chat.*-ClassicPanels.*does not use it yet/);
  assert.deepEqual(THEMES, ["Dark", "System"]);
  assert.deepEqual(SHORTCUTS, ["None", "CtrlAltSpace", "CtrlAltS"]);
  assert.match(PREVIEW_TEXT, /works in SORA's app/);
});

test("host preferences are read strictly, and a malformed message never becomes a draft", () => {
  const read = prefs({}, { revision: 12 });
  assert.equal(read.revision, 12);
  assert.equal(read.readOnly, false);
  assert.deepEqual(Object.keys(read.values), FIELD_KEYS);
  assert.ok(read.filePath.endsWith("preferences.json"));
  // Extra host fields are ignored; the seven values are what the page keeps.
  assert.deepEqual(readPreferences(hostMessage({ boardExpanded: true })).values, read.values);
  for (const bad of [{ theme: "Light" }, { textScale: 1.1 }, { textScale: 200 }, { shortcut: "CtrlS" },
    { chatPinned: "yes" }, { reducedMotion: undefined }]) {
    assert.equal(readPreferences(hostMessage(bad)), null, JSON.stringify(bad));
  }
  assert.equal(readPreferences({ type: "host.preferences" }), null);
  assert.equal(readPreferences(null), null);
  // Status facts the host does not supply are left empty, never invented.
  const sparse = readPreferences({ values: hostMessage().values, revision: -1, legacy: { imported: "2" } });
  assert.equal(sparse.revision, null);
  assert.equal(sparse.filePath, "");
  assert.equal(sparse.shortcutStatus, "");
  assert.equal(sparse.legacy.imported, 0);
  assert.equal(sparse.legacy.attempted, false);
});

test("an edit makes the page dirty, and editing back to the saved value makes it clean", () => {
  let state = loadedState();
  assert.equal(isDirty(state), false);
  state = edit(state, "chatPinned", true);
  state = edit(state, "textScale", "112");
  assert.equal(isDirty(state), true);
  assert.deepEqual(changedKeys(state.draft, state.baseline), ["textScale", "chatPinned"]);
  assert.equal(state.draft.textScale, 112);
  assert.equal(changeSummary(state), "2 unsaved changes");
  state = edit(edit(state, "chatPinned", false), "textScale", 100);
  assert.equal(isDirty(state), false);
  assert.equal(changeSummary(state), "");
  // The draft is never edited before anything is loaded.
  assert.deepEqual(edit(emptyState(), "theme", "System"), emptyState());
});

test("only values the host accepts can be entered; text size is whole percent within 85–175", () => {
  assert.equal(parseTextScale("130"), 130);
  assert.equal(parseTextScale(" 92.6 % "), 93);
  assert.equal(parseTextScale("50"), 85);
  assert.equal(parseTextScale(400), 175);
  assert.equal(parseTextScale(""), null);
  assert.equal(parseTextScale("big"), null);
  assert.equal(coerceValue("theme", "System"), "System");
  assert.throws(() => coerceValue("theme", "Light"), /choose one/);
  assert.throws(() => coerceValue("shortcut", "CtrlAltDelete"), /choose one/);
  assert.throws(() => coerceValue("textScale", "abc"), /85 to 175/);
  assert.throws(() => coerceValue("chatCompact", "true"), /on or off/);
  assert.throws(() => coerceValue("boardExpanded", true), TypeError);
});

test("a save sends exactly the draft and the values it was loaded from, which the bridge accepts", () => {
  let state = loadedState({ textScale: 110 });
  state = edit(edit(state, "theme", "System"), "shortcut", "None");
  const detail = saveDetail(state);
  assert.deepEqual(detail.values, { theme: "System", textScale: 110, shortcut: "None", chatCompact: false,
    chatPinned: false, showTechnicalDetail: false, reducedMotion: true });
  assert.deepEqual(detail.baseline, { ...detail.values, theme: "Dark", shortcut: "CtrlAltSpace" });
  assert.ok(validAppearance(detail.values) && validAppearance(detail.baseline));
  // Exactly the seven fields, so PanelBridge.Parse does not drop it.
  assert.deepEqual(Object.keys(detail.values), FIELD_KEYS);
  const message = send("prefs.save", { ...detail, requestId: "req-1" });
  assert.equal(message.type, "prefs.save");
  assert.throws(() => send("prefs.save", { values: detail.values, baseline: {}, requestId: "req-2" }), TypeError);
  assert.throws(() => saveDetail(emptyState()), /cannot be saved/);
});

test("a browser preview never pretends to save", async () => {
  const result = await hostRequest("prefs.save", saveDetail(edit(loadedState(), "chatPinned", true)));
  assert.deepEqual(result, { ok: false, error: "This works in SORA's app, not in a browser preview." });
});

test("save is refused while read-only, busy, unchanged or not loaded, with a reason", () => {
  assert.equal(saveBlocked(emptyState()), "Not loaded yet.");
  assert.equal(saveBlocked(loadedState()), "Nothing to save.");
  const dirty = edit(loadedState(), "chatCompact", true);
  assert.equal(saveBlocked(dirty), "");
  assert.equal(saveBlocked(dirty, { busy: true }), "Working…");
  const readOnly = edit(loadedState({}, { readOnly: true, diagnostic: "UI preferences unavailable…" }),
    "chatCompact", true);
  assert.match(saveBlocked(readOnly), /recovered/);
});

test("a change arriving while the draft is clean loads it; while dirty only the status updates", () => {
  let state = loadedState();
  // A window move bumps the revision only: a clean page simply follows.
  state = receive(state, prefs({}, { revision: 8 }));
  assert.equal(state.prefs.revision, 8);
  state = receive(state, prefs({ chatCompact: true }, { revision: 9 }));
  assert.equal(state.draft.chatCompact, true);
  assert.equal(isDirty(state), false);
  // Now the owner edits, and the classic Chat's Compact button changes compact again.
  state = edit(state, "theme", "System");
  const draft = state.draft;
  state = receive(state, prefs({ chatCompact: false }, { revision: 10, shortcutStatus: "Chat shortcut disabled; use the command menu." }));
  assert.equal(state.draft, draft, "the unsaved draft is kept as it was");
  assert.equal(state.draft.chatCompact, true);
  assert.equal(state.prefs.revision, 10);
  assert.equal(state.prefs.shortcutStatus, "Chat shortcut disabled; use the command menu.");
  assert.equal(state.changedElsewhere, true);
  assert.deepEqual(elsewhereChanges(state), [{ key: "chatCompact", label: "Use compact Chat", now: "off",
    alsoEdited: false }]);
  // A placement-only change while dirty is not a conflict.
  const moved = receive(edit(loadedState(), "theme", "System"), prefs({}, { revision: 11 }));
  assert.equal(moved.changedElsewhere, false);
  assert.equal(isDirty(moved), true);
  assert.equal(receive(state, null), state);
  // An unreadable file reports safe defaults: the draft is kept, and that is not called a competing edit.
  const unreadable = receive(edit(loadedState({ textScale: 130 }), "theme", "System"),
    prefs({}, { readOnly: true, revision: 0 }));
  assert.equal(unreadable.changedElsewhere, false);
  assert.equal(unreadable.draft.theme, "System");
  assert.equal(unreadable.prefs.readOnly, true);
});

test("the host's save broadcast arrives before its answer, and the saved values become the baseline", () => {
  let state = edit(edit(loadedState(), "textScale", 125), "chatPinned", true);
  const sent = saveDetail(state);
  // ShellHost posts host.preferences inside the save, then host.result.
  state = receive(state, prefs(sent.values, { revision: 8 }));
  assert.equal(isDirty(state), false);
  assert.equal(state.changedElsewhere, false);
  state = afterSave(state, sent);
  assert.deepEqual(state.baseline, sent.values);
  assert.deepEqual(state.draft, sent.values);
  assert.equal(state.prefs.revision, 8);
  // If that broadcast has not arrived, what was sent is what is saved.
  let quiet = edit(loadedState(), "theme", "System");
  const quietSent = saveDetail(quiet);
  quiet = afterSave(quiet, quietSent);
  assert.equal(isDirty(quiet), false);
  assert.equal(quiet.baseline.theme, "System");
});

test("after a conflict the owner chooses: keep their edits on the latest values, or use the saved ones", () => {
  let state = edit(edit(loadedState(), "theme", "System"), "chatCompact", true);
  // Elsewhere: compact turned on too, and the shortcut changed.
  state = receive(state, prefs({ chatCompact: true, shortcut: "CtrlAltS" }, { revision: 9 }));
  assert.equal(state.changedElsewhere, true);
  assert.deepEqual(elsewhereChanges(state).map((change) => [change.key, change.now, change.alsoEdited]),
    [["shortcut", "Ctrl+Alt+S", false], ["chatCompact", "on", true]]);
  assert.ok(isConflictError("Appearance changed. Keep your draft; explicitly reload/reconcile before saving."));
  assert.ok(!isConflictError("UI preferences changed. Keep your draft; explicitly reload/reconcile before saving."));
  const mine = keepMine(state);
  // The owner's theme edit survives; the shortcut change made elsewhere is not reverted.
  assert.deepEqual(mine.draft, { ...state.prefs.values, theme: "System" });
  assert.deepEqual(mine.baseline, state.prefs.values);
  assert.equal(mine.changedElsewhere, false);
  assert.deepEqual(saveDetail(mine).baseline, state.prefs.values);
  const theirs = discard(state);
  assert.equal(isDirty(theirs), false);
  assert.deepEqual(theirs.draft, state.prefs.values);
});

test("the shortcut sentence is the host's, with friendly key names and an honest tone", () => {
  assert.deepEqual(shortcutStatus("Chat shortcut active: CtrlAltSpace"),
    { tone: "ok", text: "Chat shortcut active: Ctrl+Alt+Space" });
  assert.deepEqual(shortcutStatus("Chat shortcut active: CtrlAltS"),
    { tone: "ok", text: "Chat shortcut active: Ctrl+Alt+S" });
  assert.equal(shortcutStatus("Chat shortcut unavailable (registration conflict); use the command menu.").tone, "bad");
  assert.equal(shortcutStatus("Chat shortcut disabled; use the command menu.").tone, "off");
  assert.deepEqual(shortcutStatus(""), { tone: "off", text: "SORA's app did not report the shortcut." });
  assert.equal(valueLabel("shortcut", "None"), "None");
  assert.equal(valueLabel("theme", "System"), "System (Windows colours)");
  assert.equal(valueLabel("textScale", 115), "115 %");
  assert.equal(valueLabel("chatPinned", true), "on");
});

test("the file status shows the revision, or the problem in its place, as the classic window did", () => {
  assert.deepEqual(fileStatus(prefs({}, { revision: 4 })),
    { tone: "ok", label: "Saved", headline: "", detail: "Preferences revision 4" });
  const unreadable = fileStatus(prefs({}, { readOnly: true,
    diagnostic: "UI preferences unavailable; safe UI-only defaults in memory. Original is untouched. Bad JSON." }));
  assert.equal(unreadable.label, "Needs attention");
  assert.match(unreadable.headline, /safe defaults.*has not been changed/);
  assert.match(unreadable.detail, /Bad JSON/);
  const refused = fileStatus(prefs({}, { diagnostic: "Appearance changed. Keep your draft…" }));
  assert.equal(refused.label, "Last change refused");
  assert.equal(fileStatus(null), null);
});

test("the legacy import notes say what the one-time import did, and nothing more", () => {
  const legacy = (extra) => legacyLines(prefs({}, { legacy: { attempted: true, imported: 0, ...extra } }).legacy);
  assert.deepEqual(legacy({}), ["SORA looked once for settings from the older desktop apps; there were none to import."]);
  assert.match(legacy({ imported: 2 })[0], /imported once \(2 files\)\. The original files were kept, with byte-identical backups\./);
  assert.match(legacy({ imported: 1 })[0], /\(1 file\)/);
  const all = legacy({ imported: 1, invalid: true, topmostNotApplied: true, quietOrTabRecorded: true,
    legacyChatHint: true });
  assert.equal(all.length, 5);
  assert.match(all[1], /could not be read and was ignored/);
  assert.match(all[2], /stay on top.*not carried over.*Pin Chat above other windows/);
  assert.match(all[3], /recorded only/);
  assert.match(all[4], /best guess, kept on screen/);
  assert.match(legacyLines(prefs({}, { legacy: { attempted: false } }).legacy)[0],
    /has not run\. Recover the preferences file first\./);
  assert.deepEqual(legacyLines(null), []);
});

test("Appearance links to Settings for her avatar, and only through a valid panel.open", () => {
  assert.deepEqual(send("panel.open", { panel: "settings", select: "Appearance" }),
    { type: "panel.open", panel: "settings", select: "Appearance" });
  assert.deepEqual(send("panel.dirty", { dirty: true }), { type: "panel.dirty", dirty: true });
  assert.deepEqual(send("panel.busy", { busy: false }), { type: "panel.busy", busy: false });
});
