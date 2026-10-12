import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { PICK_KINDS, pickFile, send } from "../shared/bridge.js";
import {
  brainSummary, brainTiles, categoryGroups, changeSet, coerce, effectOf, fieldByKey, launchText,
  rebaseDraft, saveRequest, setDraft, shownValue, visibleCategories,
  VISION_DETAIL_KEY, VISION_DISCLAIMER, VISION_LEVELS, VISION_ORDER, afterVisionArgumentEdit,
  chooseVisionLevel, visionDetail,
} from "../settings/settings-model.js";

// A real projection from AppSettingsController (default settings), refreshed by the tests below.
const fixture = JSON.parse(readFileSync(new URL("./fixtures/settings-projection.json", import.meta.url)));
const clone = () => structuredClone(fixture);

function managed(projection, { model = "C:/Models/gemma.gguf", state = "ready" } = {}) {
  for (const field of projection.fields) {
    if (field.key === "dialogue.backend") field.value = field.active_value = "managed-llama";
    if (field.key === "llama.model_path") field.value = field.active_value = model;
    if (field.key === "llama.mmproj_path") field.value = field.active_value = "C:/Models/mmproj-F16.gguf";
  }
  projection.model_state = state;
  return projection;
}

test("every field Core lists is reachable from a visible category", () => {
  const p = clone();
  const ids = visibleCategories(p).map((c) => c.id);
  assert.ok(ids.includes("Models") && ids.includes("General"));
  let reachable = 0;
  for (const id of ids) {
    const { groups, advanced } = categoryGroups(p, id);
    reachable += advanced.length + groups.reduce((sum, g) => sum + g.fields.length, 0);
  }
  assert.equal(reachable, p.fields.length);
  assert.ok(categoryGroups(p, "Models").groups.some((g) => g.name === "Brain (local model)"));
  // Her avatar (2026-10-11) is the first field in Core's Appearance category.
  assert.deepEqual(ids.slice(0, 3), ["General", "Appearance", "Models"]);
  const avatar = fieldByKey(p, "avatar.vrm_path");
  assert.equal(avatar.category, "Appearance");
  assert.equal(avatar.type, "path-file");
  assert.equal(avatar.tier, "next_boot");
});

test("inputs are converted to what Core expects, with readable errors", () => {
  const p = clone();
  const field = (key) => fieldByKey(p, key);
  assert.equal(coerce(field("llama.gpu_layers"), "ALL"), "all");
  assert.equal(coerce(field("llama.gpu_layers"), "33"), 33);
  assert.throws(() => coerce(field("llama.gpu_layers"), "lots"), /auto, all/);
  assert.equal(coerce(field("llama.context_size"), "8192"), 8192);
  assert.throws(() => coerce(field("llama.context_size"), "8192.5"), /whole number/);
  assert.throws(() => coerce(field("llama.context_size"), ""), /number/);
  assert.equal(coerce(field("llama.model_path"), "  "), null); // optional path cleared
  assert.equal(coerce(field("llama.model_path"), " C:/m.gguf "), "C:/m.gguf");
  assert.throws(() => coerce(field("dialogue.backend"), "magic"), /choose/);
  assert.deepEqual(coerce(field("agents.codex.model_choices"),
    [{ id: " gpt ", purpose: "fast" }, { id: "", purpose: "" }]), [{ id: "gpt", purpose: "fast" }]);
});

test("the draft holds only real edits and becomes an exact save request", () => {
  const p = clone();
  let draft = setDraft(p, {}, "llama.context_size", 16384);
  draft = setDraft(p, draft, "voice.speech_speed", fieldByKey(p, "voice.speech_speed").value);
  assert.deepEqual(Object.keys(draft), ["llama.context_size"]);
  assert.equal(shownValue(p, draft, "llama.context_size"), 16384);
  draft = setDraft(p, draft, "llama.context_size", fieldByKey(p, "llama.context_size").value);
  assert.deepEqual(draft, {});
  draft = setDraft(p, draft, "llama.context_size", 16384);
  draft = setDraft(p, draft, "dialogue.backend", "managed-llama");
  assert.deepEqual(saveRequest(p, draft), {
    version: p.settings_version, expected_revision: p.settings_revision,
    changes: { "llama.context_size": 16384, "dialogue.backend": "managed-llama" },
  });
  assert.deepEqual(effectOf(p, draft), { restart: true, reload: true, count: 2 });
});

test("after a save or conflict, only edits that still differ are kept", () => {
  const p = clone();
  const draft = { "llama.context_size": 16384, "voice.speech_speed": 1.2 };
  const saved = clone();
  fieldByKey(saved, "llama.context_size").value = 16384;
  saved.settings_revision += 1;
  assert.deepEqual(rebaseDraft(saved, draft), { "voice.speech_speed": 1.2 });
  assert.deepEqual(changeSet(p, { "no.such.key": 1 }), {});
});

test("the Models card shows the model SORA is actually using", () => {
  const p = managed(clone());
  const brain = brainSummary(p);
  assert.equal(brain.title, "gemma");
  assert.equal(brain.state.label, "Loaded");
  assert.equal(brain.projector, "mmproj-F16.gguf");
  assert.equal(brain.nextModel, "");
  fieldByKey(p, "llama.model_path").value = "C:/Models/other.gguf";
  assert.equal(brainSummary(p).nextModel, "C:/Models/other.gguf");
  const notManaged = brainSummary(clone());
  assert.equal(notManaged.managed, false);
  assert.match(notManaged.title, /None/);
});

test("information tiles only use values Core reports", () => {
  const p = managed(clone());
  const tiles = brainTiles(p);
  const labels = tiles.map((t) => t.label);
  assert.ok(labels.includes("Context length") && labels.includes("Vision projector"));
  assert.ok(!labels.some((label) => /VRAM|Capabilities/.test(label)));
  assert.equal(launchText(p), "");
  p.launch_details.active.argv = ["llama-server.exe", "--ctx-size", "8192"];
  assert.equal(launchText(p), "llama-server.exe --ctx-size 8192");
});

test("file pick requests are validated before reaching the host", async () => {
  assert.deepEqual(PICK_KINDS, ["gguf", "exe", "dir", "file", "attachment"]);
  assert.deepEqual(send("file.pick", { kind: "gguf", requestId: "pick-1" }),
    { type: "file.pick", kind: "gguf", requestId: "pick-1" });
  assert.throws(() => send("file.pick", { kind: "anything", requestId: "pick-1" }), /Invalid file/);
  assert.throws(() => send("file.pick", { kind: "gguf", requestId: "bad id!" }), /Invalid file/);
  assert.deepEqual(send("file.pick", { kind: "gguf", requestId: "pick-2", start: "C:/Models" }),
    { type: "file.pick", kind: "gguf", requestId: "pick-2", start: "C:/Models" });
  assert.throws(() => send("file.pick", { kind: "gguf", requestId: "pick-3", start: 5 }), /Invalid file/);
  // Outside SoraShell the picker falls back to a typed path.
  assert.equal(await pickFile("gguf", { prompt: () => "  C:/m.gguf " }), "C:/m.gguf");
  assert.equal(await pickFile("gguf", { prompt: () => null }), null);
});

test("the vision detail slider sets llama.cpp's image arguments; a hand edit makes it custom", () => {
  const p = clone();
  assert.deepEqual(visionDetail(p, {}).level, "medium");
  assert.equal(fieldByKey(p, VISION_DETAIL_KEY).category, "Vision");
  let draft = chooseVisionLevel(p, {}, "high");
  assert.deepEqual(changeSet(p, draft), {
    "llama.vision_detail": "high", "llama.image_max_tokens": 2048,
    "llama.ubatch_size": 2048, "llama.context_size": 16384,
  });
  assert.equal(effectOf(p, draft).reload, true);
  draft = setDraft(p, draft, "llama.context_size", 20000);
  draft = afterVisionArgumentEdit(p, draft, "llama.context_size");
  assert.equal(visionDetail(p, draft).level, "custom");
  assert.equal(visionDetail(p, draft).index, -1);
  // Choosing a level again replaces the hand edit with that level's values.
  assert.deepEqual(changeSet(p, chooseVisionLevel(p, draft, "medium")), {});
  assert.deepEqual(changeSet(p, chooseVisionLevel(p, {}, "medium")), {});
  assert.match(VISION_DISCLAIMER, /response times and context usage/);
  for (const level of VISION_ORDER) assert.ok(VISION_LEVELS[level]["llama.ubatch_size"] >= VISION_LEVELS[level]["llama.image_max_tokens"]);
});
