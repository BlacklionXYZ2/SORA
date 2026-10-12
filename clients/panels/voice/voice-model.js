// Voice state with no DOM: Core's local voice status checked strictly, the three status lines,
// which controls Core's state allows, the device inventory, and the hold-to-talk sequence.
// Parity with the classic Voice window (VoicePresentation.cs, the voice members of
// ShellSession.cs and VoicePanel.cs). The page never stores voice configuration: devices, models
// and listening live in Settings → Audio.

import { CoreError } from "../shared/api.js";
import { PressToTalk } from "../chat/chat-model.js";

export const VOICE_STATES = Object.freeze([
  "stopped", "loading", "ready", "listening", "recording", "transcribing", "thinking", "speaking", "error",
]);
/** The only actions POST /api/v1/voice/local accepts. */
export const VOICE_ACTIONS = Object.freeze(["start", "begin", "end", "stop", "stop_output", "close"]);
const BEGIN_STATES = ["ready", "recording", "transcribing", "thinking", "speaking"];
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/;

export const STATE_LABELS = Object.freeze({
  stopped: "Stopped", loading: "Loading", ready: "Ready", listening: "Listening", recording: "Recording",
  transcribing: "Transcribing", thinking: "Thinking", speaking: "Speaking", error: "Problem",
});
const STATE_TONES = {
  stopped: "off", loading: "active", ready: "ok", listening: "active", recording: "live",
  transcribing: "active", thinking: "active", speaking: "active", error: "bad",
};

/** What each control is called on the page (owner's words, used in outcome lines). */
export const ACTION_NAMES = Object.freeze({
  start: "Start voice", begin: "Hold to talk", end: "Release to send", stop: "Stop voice response",
  stop_output: "Stop speaking", close: "Close audio worker",
});

/** Static help, in the order the classic window gave it. */
export const HELP = Object.freeze([
  "Start voice loads the local speech models. It does not open the microphone.",
  "Hold to talk records only while you hold it (mouse or Space). Let go to send what you said. "
    + "Holding it again while she is speaking interrupts her.",
  "If the window loses focus, is hidden, or the button loses the pointer while you hold, the "
    + "recording is thrown away and nothing is sent.",
  "Closing this window only hides it. Voice keeps running until you press Close audio worker.",
  "Stop speaking silences her voice but lets her finish the answer. Stop voice response throws "
    + "away the recording and cancels her spoken answer, but not Chat or agent tasks.",
  "Devices, models and listening are chosen in Settings → Audio. The device list here is read-only.",
]);

/** Core sent something this page will not show as voice status. */
export class VoiceDataError extends Error {
  constructor(message) {
    super(message);
    this.name = "VoiceDataError";
  }
}

/**
 * A voice action that failed. `sent` is false when nothing reached Core's voice route (refused by
 * the page, or a failed preflight). `refused` means Core answered with a definite refusal, so
 * nothing changed. Otherwise the outcome is unknown.
 */
export class VoiceActionError extends Error {
  constructor(message, { sent, refused = false, cause } = {}) {
    super(message);
    this.name = "VoiceActionError";
    this.sent = sent === true;
    this.refused = this.sent && refused === true;
    this.cause = cause;
  }
}

// Core refused outright (bad request, not allowed, not found, too large). A 409 can be a worker
// timeout with no message, and a 5xx may not have reached Core, so those stay "not confirmed".
const REFUSALS = [400, 401, 403, 404, 413];

const channel = (value) => Number.isInteger(value) && value >= 0 && value <= 256;

/**
 * Core's voice status, checked exactly as the classic window did. Anything outside these bounds
 * is not shown: the page says it could not trust the status instead. `enabled` is the fallback
 * when a reply omits the Settings switch (an action reply after a good preflight).
 */
export function parseVoice(data, enabled = undefined) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new VoiceDataError("it was not a status record");
  }
  const state = typeof data.state === "string" ? data.state : "";
  const message = typeof data.message === "string" ? data.message : "";
  if (!VOICE_STATES.includes(state)) throw new VoiceDataError("its state is not one SORA knows");
  if (message.length > 1000) throw new VoiceDataError("its message is longer than 1,000 characters");
  if (typeof data.running !== "boolean") {
    throw new VoiceDataError("it did not say whether the voice worker is running");
  }
  const allowed = typeof data.enabled === "boolean" ? data.enabled : enabled;
  if (typeof allowed !== "boolean") {
    throw new VoiceDataError("it did not say whether voice is turned on in Settings");
  }
  if (!Array.isArray(data.devices) || data.devices.length > 128) {
    throw new VoiceDataError("its device list was missing or longer than 128 devices");
  }
  const devices = data.devices.map((row) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      throw new VoiceDataError("a device entry was not a record");
    }
    const key = typeof row.key === "string" ? row.key : "";
    if (key.length < 1 || key.length > 512 || CONTROL.test(key)) {
      throw new VoiceDataError("a device key was empty, too long or had control characters");
    }
    if (!channel(row.input_channels) || !channel(row.output_channels)) {
      throw new VoiceDataError("a device's channel count was not a whole number from 0 to 256");
    }
    let index = null;
    if (Object.hasOwn(row, "index")) {
      if (!Number.isInteger(row.index) || row.index < 0 || row.index > 4096) {
        throw new VoiceDataError("a device's adapter index was not a whole number from 0 to 4096");
      }
      index = row.index;
    }
    return Object.freeze({ key, inputs: row.input_channels, outputs: row.output_channels, index });
  });
  return Object.freeze({
    state, message, running: data.running, enabled: allowed,
    // Older Core has no capture field: never infer "closed" from the general state.
    microphoneOpen: typeof data.microphone_open === "boolean" ? data.microphone_open : null,
    listening: typeof data.listening === "boolean" ? data.listening : null,
    hearing: typeof data.hearing === "boolean" ? data.hearing : null,
    devices: Object.freeze(devices),
  });
}

/** The classic enablement table (VoiceProjection.Can). Close is always allowed. */
export function can(voice, action) {
  if (action === "close") return true;
  if (!voice || !voice.enabled) return false;
  if (action === "start") return voice.state === "stopped" || voice.state === "error";
  if (action === "begin") return voice.running && BEGIN_STATES.includes(voice.state);
  if (action === "end" || action === "stop" || action === "stop_output") return voice.running;
  return false;
}

/** Hold to talk: as `can("begin")`, but off while Core reports always-on listening (it refuses). */
export function canHold(voice) {
  return can(voice, "begin") && voice.listening !== true;
}

function allowed(voice, action) {
  return action === "begin" ? canHold(voice) : can(voice, action);
}

/** Why Core's current state rules an action out, in the owner's words. */
export function whyNot(voice, action) {
  if (action !== "close" && !voice.enabled) return "Voice is turned off in Settings.";
  if (action === "begin" && voice.listening === true) {
    return "Always-on listening is on, so just say her name instead.";
  }
  if (action === "start") return "Voice is already running.";
  if (!voice.running) return "Voice is not running. Start voice first.";
  if (action === "begin") return "Voice is not ready to record yet.";
  return "Core's voice state changed since the last read.";
}

/** Error detail for the owner. Core's own words are kept; empty or technical ones are explained. */
export function errorText(error) {
  if (error instanceof VoiceActionError) return error.message;
  if (error instanceof VoiceDataError) return `Core sent a voice status this page could not trust: ${error.message}.`;
  if (error instanceof CoreError) {
    if (error.code === "RUNTIME_CHANGED") {
      return "SORA's Core restarted and the app has not caught up yet. Try again in a moment.";
    }
    if (error.code === "LOCAL_VOICE_UNAVAILABLE" && /^Core returned \d+\.$/.test(error.message)) {
      return "The voice worker did not answer in time.";
    }
    return error.message;
  }
  return String(error?.message ?? error);
}

function instanceOf(identity, sent) {
  const id = identity?.instance_id;
  if (typeof id !== "string" || !id || id.length > 128) {
    throw new VoiceActionError("Core did not say which instance is running.", { sent });
  }
  return id;
}

/** Light check of GET /api/v1/projections/companion: only the fields the dialogue line uses. */
export function parseCompanion(data) {
  const companion = data?.companion;
  if (!companion || typeof companion !== "object" || Array.isArray(companion)) {
    throw new VoiceDataError("the companion status was missing");
  }
  const text = (value, max) => (typeof value === "string" && value.length <= max ? value : "");
  return Object.freeze({
    state: text(companion.state, 64),
    dialogueReady: companion.dialogue_ready === true,
    modelState: text(companion.model_state, 64),
    dialogueModel: text(companion.dialogue_model, 512).trim(),
  });
}

/**
 * Line 3: what the dialogue model is doing (derived from Core's fields as the classic window did)
 * and its name. `connected` is null before the first read, false after a failed one.
 */
export function dialogueLine(companion, connected) {
  if (!companion) {
    return connected === false
      ? { label: "Reconnecting…", model: "not reported", stale: false,
        text: "Dialogue model: Reconnecting… · not reported, because Core did not answer" }
      : { label: "", model: "not read yet", stale: false, text: "Dialogue model: not read yet" };
  }
  const label = connected === false ? "Reconnecting…"
    : companion.state === "thinking" ? "Thinking…"
    : !companion.dialogueReady
      ? (companion.modelState === "reloading" ? "Model reloading…" : "Model unavailable (see Settings)")
    : companion.state === "talking" ? "Speaking…"
    : "Ready to talk";
  const model = companion.dialogueModel || "not reported by Core";
  const stale = connected === false;
  return { label, model, stale,
    text: `Dialogue model: ${label} · ${model}${stale ? " (last reported)" : ""}` };
}

/** Line 1: the microphone, which is never shown as closed unless the worker says so. */
export function microphoneLine(voice, current) {
  if (!voice || !current) {
    return voice?.microphoneOpen === true
      ? { text: "Microphone UNKNOWN · last reported open", tone: "unknown-open" }
      : { text: "Microphone status UNKNOWN", tone: "unknown" };
  }
  if (voice.microphoneOpen === true) {
    return voice.state === "listening" || voice.listening === true
      ? { text: "Microphone on · listening for her name", tone: "listening" }
      : { text: "Microphone on · recording", tone: "live" };
  }
  if (voice.microphoneOpen === false) {
    return { text: "Microphone closed · as the voice worker reports", tone: "closed" };
  }
  return { text: "Microphone status UNKNOWN", tone: "unknown" };
}

/** The device inventory, with keys that occur more than once flagged rather than merged. */
export function deviceInventory(voice, current) {
  if (!voice) {
    return { rows: [], empty: "No device list yet: Core has not reported one.", stale: false, ambiguous: false };
  }
  const counts = new Map();
  for (const device of voice.devices) counts.set(device.key, (counts.get(device.key) ?? 0) + 1);
  const rows = voice.devices.map((device) => ({ ...device, ambiguous: counts.get(device.key) > 1 }));
  return {
    rows,
    empty: rows.length ? ""
      : "No devices reported yet. Start voice to have the voice worker list this computer's audio devices.",
    stale: !current,
    ambiguous: rows.some((row) => row.ambiguous),
  };
}

/** One device as plain text, as the classic inventory wrote it. */
export function deviceText(row) {
  return `${row.key} · input ${row.inputs} / output ${row.outputs}`
    + (row.index === null ? "" : ` · adapter index ${row.index}`)
    + (row.ambiguous ? " · AMBIGUOUS KEY (not silently selected)" : "");
}

/** Outcome line after Start voice, Stop speaking, Stop voice response or Close audio worker. */
export function actionOutcome(action, error = null, reply = null) {
  const name = ACTION_NAMES[action] ?? action;
  if (!error) {
    const loading = action === "start" && reply?.state === "loading"
      ? " It is loading the speech models, which can take a while the first time." : "";
    return { tone: "ok",
      text: `Core confirmed ${name}.${loading} The status above is what the voice worker reports now.` };
  }
  if (error.sent === false) return { tone: "bad", text: `${name} was not sent. ${errorText(error)}` };
  if (error.refused) return { tone: "bad", text: `Core refused ${name}. ${errorText(error)}` };
  return { tone: "bad",
    text: `${name} was not confirmed, and SORA will not retry it automatically. ${errorText(error)}` };
}

/** Outcome line after a hold: begin failed, release failed, sent, or discarded. */
export function holdOutcome(kind, { error = null, reason = "", safetyStop = "" } = {}) {
  if (kind === "sent") {
    return { tone: "ok", text: "Recording sent. The status above shows what she is doing with it." };
  }
  if (kind === "discarded") {
    return { tone: "info", text: `Recording discarded because ${reason || "the hold was lost"}. Nothing was sent.` };
  }
  const detail = errorText(error);
  if (kind === "begin-failed") {
    const safety = safetyStop === "confirmed"
      ? " You had already let go, so a stop was sent and Core confirmed it."
      : safetyStop === "failed"
        ? " You had already let go, so a stop was sent, but it was not confirmed either." : "";
    if (error?.sent === false) {
      return { tone: "bad", text: `The recording did not start, and nothing was sent. ${detail}` };
    }
    if (error?.refused) return { tone: "bad", text: `The recording did not start: Core refused it. ${detail}` };
    return { tone: "bad", text: "The recording was not confirmed. If the microphone status stays unknown, "
      + `use Close audio worker. ${detail}${safety}` };
  }
  const what = error?.sent === false ? "not sent" : error?.refused ? "refused by Core" : "not confirmed";
  return { tone: "bad", text: `Your release was ${what}, so the microphone status may be unknown. `
    + `Use Close audio worker if it stays unknown. ${detail}` };
}

/**
 * Hold to talk with the classic window's exact ordering. It reuses Chat's PressToTalk (press sends
 * "begin"; a release or loss during "begin" is remembered and sent once "begin" settles, as "end"
 * or "stop") and adds what the classic window also did: if "begin" reached Core but was not
 * confirmed after the owner had already let go, one safety "stop" is sent and "begin" is never
 * replayed. A begin that was never sent, or that Core refused outright, needs no stop.
 * `releasing` is the "Releasing…" state: let go while "begin" is still in flight.
 */
export class HoldToTalk extends PressToTalk {
  constructor(act) {
    // A synchronous throw becomes a rejected promise, so a failed begin never leaves the hold latched.
    super((action) => {
      try { return Promise.resolve(act(action)); } catch (error) { return Promise.reject(error); }
    });
    this.letGoAsked = false;
    this.safetyStop = "";
  }

  /** Pressed, or "begin" still in flight: work Quit must wait for. */
  get pending() { return this.held || this.beginning !== null; }
  /** The owner is holding the button now. */
  get holding() { return this.held && !this.letGoAsked; }
  /** Let go while "begin" is still in flight. */
  get releasing() { return this.beginning !== null && this.letGoAsked; }

  async press() {
    if (this.held) return;
    this.letGoAsked = false;
    this.safetyStop = "";
    try {
      await super.press();
    } catch (error) {
      if (this.letGoAsked && error?.sent !== false && !error?.refused) {
        try { await this.act("stop"); this.safetyStop = "confirmed"; } catch { this.safetyStop = "failed"; }
      }
      throw error;
    } finally {
      if (!this.held) this.letGoAsked = false;
    }
  }

  async letGo(options = {}) {
    if (!this.held) return;
    this.letGoAsked = true;
    await super.letGo(options);
  }
}

/**
 * The page's voice state. Reads are fenced by a sequence number so a slow old read never
 * overwrites a newer one; every action first re-reads Core's status and checks it still allows
 * the action, and is never retried automatically. `onChange` is called after every change.
 */
export class VoiceSession {
  constructor(api, { onChange = () => {} } = {}) {
    this.api = api;
    this.onChange = onChange;
    this.voice = null;        // last good status (shown as stale when not current)
    this.readOk = false;      // the last read or action reply was good
    this.problem = null;      // { kind: "read" | "invalid" | "action" | "core-changed", detail, unavailable }
    this.canUseCore = true;   // host.core; assumed true in a browser preview
    this.inFlight = 0;
    this.pendingAction = "";
    this.holdSending = "";    // "end" or "stop" while the hold's own release is in flight
    this.fence = 0;
    this.companion = null;
    this.companionOk = null;   // null before the first read, then whether the last read worked
    this.companionFence = 0;
    this.outcome = null;
    this.discardReason = "";
    this.holdInstance = null;
    this.hold = new HoldToTalk((action) => this.holdAction(action));
  }

  notify() { this.onChange(this); }
  get busy() { return this.inFlight > 0; }
  /** The status is fresh, nothing is pending, and the host lets panels use Core. */
  get current() { return this.voice !== null && this.readOk && !this.busy && this.canUseCore; }

  setCanUseCore(value) {
    if (this.canUseCore === value) return;
    this.canUseCore = value;
    this.notify();
  }

  async readVoice() {
    if (this.busy) return; // an action's own reply is newer than any read
    const fence = ++this.fence;
    let data = null;
    let failure = null;
    try { data = parseVoice(await this.api.voice()); } catch (error) { failure = error; }
    if (fence !== this.fence) return;
    if (failure) {
      this.readOk = false;
      if (failure instanceof CoreError && failure.code === "RUNTIME_CHANGED") {
        this.voice = null;
        this.problem = { kind: "core-changed", detail: "" };
      } else if (failure instanceof VoiceDataError) {
        this.problem = { kind: "invalid", detail: failure.message };
      } else {
        this.problem = { kind: "read", detail: errorText(failure),
          unavailable: failure instanceof CoreError && failure.unavailable };
      }
    } else {
      this.voice = data;
      this.readOk = true;
      this.problem = null;
    }
    this.notify();
  }

  async readCompanion() {
    const fence = ++this.companionFence;
    let data = null;
    try { data = parseCompanion(await this.api.companion()); } catch { data = null; }
    if (fence !== this.companionFence) return;
    if (data) this.companion = data;
    this.companionOk = data !== null;
    this.notify();
  }

  /**
   * One explicit action: preflight (Core's status and instance), the POST, then a check that
   * Core did not change underneath. `pinned` refuses unless Core is still the instance a hold
   * began on; `pin` learns that instance before "begin" is sent.
   */
  async runAction(action, { pinned, pin } = {}) {
    if (!VOICE_ACTIONS.includes(action)) throw new TypeError("Choose an exact supported voice action.");
    if (!this.canUseCore) throw new VoiceActionError("SORA has paused panel access to Core.", { sent: false });
    if (this.busy) {
      throw new VoiceActionError("Another voice request is still waiting for Core.", { sent: false });
    }
    this.inFlight += 1;
    this.fence += 1;
    this.pendingAction = action;
    this.notify();
    let sent = false;
    try {
      const [status, identity] = await Promise.all([
        this.api.voice().then((value) => ({ value }), (error) => ({ error })),
        this.api.identity(),
      ]);
      const instance = instanceOf(identity, false);
      pin?.(instance);
      if (pinned !== undefined && pinned !== instance) {
        throw new VoiceActionError("SORA's Core restarted after you pressed Hold to talk.", { sent: false });
      }
      // Close is the safety action: an unreadable status must not stop the owner closing audio.
      let current = null;
      if (status.error) {
        if (action !== "close") throw status.error;
      } else {
        try { current = parseVoice(status.value); } catch (error) { if (action !== "close") throw error; }
      }
      if (current && !allowed(current, action)) {
        throw new VoiceActionError(whyNot(current, action), { sent: false });
      }
      sent = true;
      const reply = parseVoice(await this.api.voiceAction(action), current?.enabled);
      if (instanceOf(await this.api.identity(), true) !== instance) {
        throw new VoiceActionError("Core changed after the request was sent.", { sent: true });
      }
      this.fence += 1;
      this.voice = reply;
      this.readOk = true;
      this.problem = null;
      return reply;
    } catch (error) {
      this.fence += 1;
      this.readOk = false;
      const failure = error instanceof VoiceActionError ? error
        : new VoiceActionError(errorText(error), { sent, cause: error,
          refused: error instanceof CoreError && REFUSALS.includes(error.status) });
      this.problem = { kind: "action", detail: failure.message, sent: failure.sent, refused: failure.refused };
      throw failure;
    } finally {
      this.inFlight -= 1;
      this.pendingAction = "";
      this.notify();
    }
  }

  async holdAction(action) {
    if (action === "begin") {
      this.holdInstance = null;
      await this.runAction("begin", { pin: (instance) => { this.holdInstance = instance; } });
      return;
    }
    this.holdSending = action;
    try {
      await this.runAction(action, { pinned: this.holdInstance ?? "" });
    } finally {
      this.holdSending = "";
    }
    this.outcome = action === "end" ? holdOutcome("sent")
      : holdOutcome("discarded", { reason: this.discardReason });
  }

  /** A button action (start, stop_output, stop, close). Never retried. */
  async perform(action) {
    if (action === "stop" && this.hold.pending) {
      await this.releaseHold({ discard: true, reason: "you pressed Stop voice response" });
      return;
    }
    if (action === "close") await this.releaseHold({ discard: true, reason: "you pressed Close audio worker" });
    try {
      const reply = await this.runAction(action);
      this.outcome = actionOutcome(action, null, reply);
    } catch (error) {
      this.outcome = actionOutcome(action, error);
    }
    this.notify();
  }

  async pressHold() {
    if (this.hold.pending || !this.controls().hold) return;
    this.discardReason = "";
    const pressing = this.hold.press();
    this.notify();
    try {
      await pressing;
    } catch (error) {
      this.outcome = holdOutcome("begin-failed", { error, safetyStop: this.hold.safetyStop });
    }
    this.notify();
  }

  async releaseHold({ discard = false, reason = "" } = {}) {
    if (!this.hold.held) return;
    if (discard) this.discardReason = reason;
    const releasing = this.hold.letGo({ discard });
    this.notify();
    try {
      await releasing;
    } catch (error) {
      this.outcome = holdOutcome("release-failed", { error });
    }
    this.notify();
  }

  /** Which controls Core's state allows now (the classic window's rules, plus listening). */
  controls() {
    const voice = this.voice;
    const ready = this.current;
    const hold = this.hold;
    const sending = !hold.pending && this.holdSending !== "";
    const holdState = hold.releasing ? "releasing" : hold.held ? "held" : sending ? "sending"
      : ready && canHold(voice) ? "ready" : ready && voice.listening === true ? "listening" : "off";
    return {
      start: ready && can(voice, "start"),
      // Never disable a held button: that would drop its pointer capture and its Space key-up.
      hold: hold.pending || (ready && canHold(voice)),
      holdState,
      holdLabel: { releasing: "Releasing…", held: "Release to send", listening: "Listening",
        sending: this.holdSending === "end" ? "Sending…" : "Discarding…" }[holdState] ?? "Hold to talk",
      holdHint: this.holdHint(),
      stopOutput: ready && can(voice, "stop_output"),
      stop: ready && can(voice, "stop"),
      close: this.canUseCore && !this.busy,
    };
  }

  holdHint() {
    const voice = this.voice;
    if (this.hold.releasing) return "Waiting for Core to confirm the recording started…";
    if (this.hold.held) return "Recording while you hold. Let go to send.";
    if (!this.canUseCore) return "Paused while SORA's Core is unavailable to panels.";
    if (this.busy) return "Waiting for Core…";
    if (!this.current) return "Unavailable until Core reports the voice status.";
    if (!voice.enabled) return "Voice is turned off in Settings.";
    if (voice.listening === true && voice.running) return "Always-on listening is on: just say her name.";
    if (!voice.running) return voice.state === "loading" ? "Voice is starting…" : "Start voice first.";
    if (!canHold(voice)) {
      return voice.state === "error" ? "Voice has a problem. Start voice again." : "Wait until voice is ready.";
    }
    return voice.state === "speaking" || voice.state === "thinking"
      ? "Hold to interrupt her and talk." : "Hold with the mouse or Space. Let go to send.";
  }

  /** Line 2: Core's state and message, the Settings switch, or why the status is not current. */
  statusLine() {
    const voice = this.voice;
    if (!this.canUseCore) {
      return { kind: "reason",
        text: "SORA has paused panel access to Core (it may be starting or stopping), so this status is not current." };
    }
    if (this.busy) {
      return { kind: "reason", text: "Waiting for Core to confirm. The microphone status is unconfirmed until it does." };
    }
    const problem = this.problem;
    if (problem?.kind === "core-changed") {
      return { kind: "reason", text: "SORA's Core changed, so the voice status must be read again." };
    }
    if (problem?.kind === "read") {
      const kept = voice ? ", so what you see is the last report and may be out of date" : "";
      return { kind: "reason", text: `Voice status could not be read${kept}. ${problem.detail}` };
    }
    if (problem?.kind === "invalid") {
      const kept = voice ? "; what you see is the last good report" : "";
      return { kind: "reason",
        text: `Core sent a voice status this page could not trust (${problem.detail}), so it is not shown${kept}.` };
    }
    if (problem?.kind === "action") {
      const what = !problem.sent ? "was not sent" : problem.refused ? "was refused by Core"
        : "was not confirmed and will not be retried automatically";
      return { kind: "reason", text: `The last voice action ${what}. ${problem.detail}` };
    }
    if (!voice || !this.readOk) return { kind: "reason", text: "Voice status has not been read yet." };
    if (!voice.enabled) return { kind: "disabled", text: "Voice is turned off in Settings.", message: voice.message };
    return {
      kind: "status", state: voice.state, label: STATE_LABELS[voice.state], tone: STATE_TONES[voice.state],
      message: voice.message, text: `${STATE_LABELS[voice.state]}: ${voice.message}`,
      listening: voice.listening === true, hearing: voice.hearing === true,
    };
  }

  banner() {
    if (!this.canUseCore) {
      return "SORA is starting or stopping Core, so voice controls are paused. The microphone status shown is not current.";
    }
    if (this.problem?.kind === "read" && this.problem.unavailable) {
      return "SORA's Core is not reachable. Voice controls are paused and the microphone status is unknown; retrying…";
    }
    return "";
  }

  /** Everything the page renders, from this state alone. */
  view() {
    const current = this.current;
    return {
      microphone: microphoneLine(this.voice, current),
      status: this.statusLine(),
      dialogue: dialogueLine(this.companion, this.companionOk),
      controls: this.controls(),
      devices: deviceInventory(this.voice, current),
      outcome: this.outcome,
      banner: this.banner(),
      busy: this.busy || this.hold.pending,
    };
  }
}
