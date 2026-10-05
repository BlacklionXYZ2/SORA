const EMPTY_STATE = Object.freeze({
  connected: false,
  initialized: false,
  lastSequence: 0,
  messages: [],
  tasks: [],
  companion: {},
  capabilities: {},
  status: {},
  traces: [],
  lastError: "",
});

export class ProjectionStore {
  constructor() {
    this.state = { ...EMPTY_STATE };
    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  update(patch) {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener(this.state);
  }

  replaceAuthoritative({ messages, tasks, companion, capabilities, status }) {
    this.update({
      messages: Array.isArray(messages) ? messages : [],
      tasks: Array.isArray(tasks?.tasks) ? tasks.tasks : [],
      companion: companion || {},
      capabilities: capabilities || {},
      status: status || {},
      initialized: true,
      connected: true,
      lastError: "",
    });
  }

  ingestEventPage(page) {
    const events = Array.isArray(page?.events) ? page.events : [];
    const next = Number(page?.next_sequence ?? this.state.lastSequence);
    const traces = [...this.state.traces, ...events.map(toTrace)].slice(-100);
    this.update({ lastSequence: Number.isSafeInteger(next) && next >= 0 ? next : 0, traces });
    return events.length > 0 || Boolean(page?.resync_required);
  }

  disconnected(error) {
    this.update({ connected: false, lastError: error instanceof Error ? error.message : String(error || "Disconnected") });
  }
}

function toTrace(envelope) {
  return {
    sequence: Number(envelope?.sequence || 0),
    eventType: String(envelope?.event_type || envelope?.type || "event"),
    timestamp: String(envelope?.timestamp || envelope?.created_at || ""),
  };
}

export class SyncCoordinator {
  constructor(api, store, { pageLimit = 100, maxPages = 10 } = {}) {
    this.api = api;
    this.store = store;
    this.pageLimit = pageLimit;
    this.maxPages = maxPages;
  }

  async synchronize() {
    const [messages, tasks, companion, capabilities, status] = await Promise.all([
      this.api.messages(),
      this.api.tasks(),
      this.api.companion(),
      this.api.capabilities(),
      this.api.status(),
    ]);
    this.store.replaceAuthoritative({ messages, tasks, companion, capabilities, status });
  }

  async pollOnce() {
    let changed = !this.store.state.initialized || !this.store.state.connected;
    try {
      for (let pageNumber = 0; pageNumber < this.maxPages; pageNumber += 1) {
        const page = await this.api.events(this.store.state.lastSequence, this.pageLimit);
        changed = this.store.ingestEventPage(page) || changed;
        if (page.resync_required || !page.more_available) break;
        if (pageNumber === this.maxPages - 1) changed = true;
      }
      if (changed) await this.synchronize();
      else this.store.update({ connected: true, lastError: "" });
      return this.store.state;
    } catch (error) {
      this.store.disconnected(error);
      throw error;
    }
  }
}
