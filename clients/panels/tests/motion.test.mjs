import assert from "node:assert/strict";
import { test } from "node:test";

import {
  KEYS, activeChoice, changes, choiceUsable, customVersions, measureRows, project, readPreview,
  saveRequest, savedChoice, selectedModel, statusNotice, withVersion,
} from "../motion/motion-model.js";

const field = (key, value, active = value) => ({ key, value, active_value: active });
const projection = {
  settings_version: 10, settings_revision: 7,
  fields: [
    field(KEYS.engine, "algorithmic"), field(KEYS.precision, "fp16"), field(KEYS.steps, 4),
    field(KEYS.version, "v4"), field(KEYS.size, "0.8M"), field("avatar.vrm_path", "x"),
  ],
};
const model = (version, size, state, measures = {}, extra = {}) => ({ version, size, state, measures, ...extra });
const catalog = {
  recordings: { outside_limits_share: 0.004, foot_slide_m_s: 0.08, energy_rad_s: 1.0 },
  engines: [
    { id: "algorithmic", name: "Algorithmic", models: [model("built-in", "", "ready")] },
    { id: "ardy", name: "ARDY", models: [
      model("Core fp16", "192M", "ready", { outside_limits_share: 0.001, foot_slide_m_s: 0.06, energy_rad_s: 1.2 },
        { preview: "previews/ardy-fp16.json" }),
      model("Core fp32", "192M", "missing"),
    ] },
    { id: "custom", name: "Custom", models: [
      model("v10", "0.8M", "experimental"), model("v2", "0.8M", "experimental", { outside_limits_share: 0.12 }),
      model("v2", "17.5M", "planned"), model("v4", "3M", "experimental"), model("v4", "0.8M", "experimental"),
    ] },
  ],
};

test("the saved and running choices come from the motion.* settings fields", () => {
  assert.deepEqual(savedChoice(projection),
    { engine: "algorithmic", precision: "fp16", steps: 4, version: "v4", size: "0.8M" });
  const restarted = { ...projection, fields: projection.fields.map((f) => f.key === KEYS.engine ? field(f.key, "ardy", "algorithmic") : f) };
  assert.equal(savedChoice(restarted).engine, "ardy");
  assert.equal(activeChoice(restarted).engine, "algorithmic");
  assert.equal(savedChoice({ fields: [] }), null); // an older Core without motion settings
});

test("only changed keys are saved, with the revision that was read", () => {
  const saved = savedChoice(projection);
  const draft = { ...saved, engine: "ardy", steps: 6 };
  assert.deepEqual(changes(saved, draft), { [KEYS.engine]: "ardy", [KEYS.steps]: 6 });
  assert.deepEqual(saveRequest(projection, saved, draft),
    { version: 10, expected_revision: 7, changes: { [KEYS.engine]: "ardy", [KEYS.steps]: 6 } });
  assert.deepEqual(changes(saved, { ...saved }), {});
});

test("versions sort numerically and sizes by value; planned and missing models can't be chosen", () => {
  assert.deepEqual(customVersions(catalog).map((v) => v.version), ["v2", "v4", "v10"]);
  assert.deepEqual(customVersions(catalog)[1].sizes.map((m) => m.size), ["0.8M", "3M"]);
  const base = savedChoice(projection);
  assert.ok(choiceUsable(catalog, { ...base, engine: "ardy", precision: "fp16" }));
  assert.ok(!choiceUsable(catalog, { ...base, engine: "ardy", precision: "fp32" })); // missing files
  assert.ok(!choiceUsable(catalog, { ...base, engine: "custom", version: "v2", size: "17.5M" })); // planned
  assert.ok(!choiceUsable(catalog, { ...base, engine: "custom", version: "v9", size: "0.8M" })); // unknown
  assert.equal(selectedModel(catalog, { ...base, engine: "algorithmic" }).version, "built-in");
});

test("switching version keeps the size when that version has it, else takes its smallest usable", () => {
  const base = { ...savedChoice(projection), engine: "custom", version: "v4", size: "3M" };
  assert.deepEqual(withVersion(catalog, base, "v2"), { ...base, version: "v2", size: "0.8M" });
  assert.equal(withVersion(catalog, { ...base, size: "0.8M" }, "v10").size, "0.8M");
});

test("measure rows show the model beside real motion capture, scaled to the largest value", () => {
  const ardy = selectedModel(catalog, { ...savedChoice(projection), engine: "ardy" });
  const rows = measureRows(catalog, ardy);
  assert.deepEqual(rows.map((r) => r.key), ["outside_limits_share", "foot_slide_m_s", "energy_rad_s"]);
  const outside = rows[0];
  assert.equal(outside.text, "0.10 %");
  assert.equal(outside.referenceText, "0.40 %");
  assert.ok(Math.abs(outside.width - 0.001 / 0.12) < 1e-9); // v2's 12% is the largest
  assert.deepEqual(measureRows(catalog, null), []);
});

test("preview clips are validated and converted from millimetres", () => {
  const clip = readPreview({ label: "walk", fps: 10, joint_names: ["hips", "spine"], joint_parents: [-1, 0],
    frames: [[0, 900, 0, 0, 1000, 10], [5, 900, 0, 5, 1000, 10]] });
  assert.equal(clip.frames.length, 2);
  assert.deepEqual(clip.frames[0][1], [0, 1, 0.01]);
  assert.equal(readPreview({ ...clip, fps: 10, joint_names: ["a"], joint_parents: [-1], frames: [[1, 2]] }), null);
  assert.equal(readPreview({ fps: 0, joint_names: [], joint_parents: [], frames: [] }), null);
  assert.equal(readPreview(null), null);
});

test("the preview camera follows her horizontally and draws height upwards", () => {
  const view = { yaw: 0, pitch: 0, scale: 100, cx: 50, cy: 200 };
  assert.deepEqual(project([3, 0, 7], [3, 0.9, 7], view), [50, 200]); // her root stays centred
  assert.deepEqual(project([3, 1, 7], [3, 0.9, 7], view), [50, 100]); // a metre up is 100 px up
});

test("the motion status reads as a banner, polling only while a model starts", () => {
  const status = (state, extra = {}) => ({ engine: "ardy", state, model: "", error: "",
    load_seconds: null, chunks: 0, player_connected: true, ...extra });
  assert.equal(statusNotice(null, catalog), null);
  const starting = statusNotice(status("starting"), catalog);
  assert.ok(starting.busy && /recorded/.test(starting.text));
  assert.ok(statusNotice(status("handover"), catalog).busy);
  const running = statusNotice(status("running", { load_seconds: 4.25 }), catalog);
  assert.deepEqual([running.kind, running.busy], ["", false]);
  assert.match(running.text, /is moving her \(loaded in 4\.3 s\)/);
  assert.equal(statusNotice(status("running", { player_connected: false }), catalog).kind, "warn");
  const failed = statusNotice(status("failed", { error: "load failed: no GPU" }), catalog);
  assert.equal(failed.kind, "error");
  assert.match(failed.text, /no GPU.*algorithmic/);
  assert.match(statusNotice(status("algorithmic", { engine: "algorithmic" }), catalog).text, /algorithmic system/);
  assert.equal(statusNotice({ state: "unavailable", engine: "algorithmic", error: "No player." }, catalog).text,
    "No player.");
});
