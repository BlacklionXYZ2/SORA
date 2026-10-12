// Small line icons (24-unit grid, stroke = currentColor). Static strings only.
const paths = {
  minimize: '<path d="M6 12h12"/>',
  maximize: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  close: '<path d="M7 7l10 10M17 7L7 17"/>',
  send: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="2"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  panel: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M10 5v14"/>',
  chevron: '<path d="M8 10l4 4 4-4"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
  retry: '<path d="M20 12a8 8 0 11-2.3-5.6M20 4v4h-4"/>',
  down: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  general: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  models: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  audio: '<path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/>',
  vision: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  memory: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
  tools: '<path d="M14.5 6.5a4 4 0 00-5.2 5.2L4 17l3 3 5.3-5.3a4 4 0 005.2-5.2l-2.5 2.5-2.5-.5-.5-2.5z"/>',
  performance: '<path d="M4 20V14M10 20V9M16 20V12M22 20V5"/>',
  advanced: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  appearance: '<path d="M12 3a9 9 0 100 18c1.1 0 1.5-.8 1.5-1.5 0-1.2-1-1.5-1-2.5s.9-1.5 2-1.5h2A4.5 4.5 0 0021 11c0-4.4-4-8-9-8z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10.5" cy="7.5" r="1"/><circle cx="15" cy="7.5" r="1"/>',
  folder: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4h6v3"/>',
  attach: '<path d="M20 11.5l-8.2 8.2a5 5 0 01-7.1-7.1l8.6-8.6a3.4 3.4 0 014.8 4.8l-8.4 8.4a1.7 1.7 0 01-2.4-2.4l7.8-7.8"/>',
  file: '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5"/>',
  bolt: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
  task: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  graph: '<circle cx="12" cy="6" r="2.5"/><circle cx="6" cy="17" r="2.5"/><circle cx="18" cy="17" r="2.5"/><path d="M10.8 8.2L7.2 14.8M13.2 8.2l3.6 6.6M8.5 17h7"/>',
  walk: '<circle cx="13" cy="4" r="2"/><path d="M9 21l3-7 3 3v4M7 11l3-3 4 1 3 3M12 14l-1-5"/>',
};

export function icon(name, label = "") {
  const body = paths[name];
  if (!body) throw new TypeError(`Unknown icon: ${name}`);
  const a11y = label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"';
  return `<svg class="icon" viewBox="0 0 24 24" ${a11y}>${body}</svg>`;
}

export const ICON_NAMES = Object.freeze(Object.keys(paths));
