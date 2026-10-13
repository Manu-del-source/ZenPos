/**
 * The offline cash-sale queue: a pure state machine over plain objects.
 *
 * No DOM, no network, no axios — storage is injected and network outcomes
 * are classified by the caller, so every rule here is unit-testable and the
 * browser hook stays thin.
 *
 * The rules:
 *
 * - One entry per client reference. The reference is the idempotency key
 *   the server uses to de-duplicate replays, so the queue must never hold
 *   two entries for the same basket: a duplicated entry is a duplicate-sale
 *   risk the server constraint would only catch with a 400 in the cashier's
 *   face.
 * - FIFO. The till that rang first is the till that books first, which is
 *   also the order the customer handed over the money.
 * - Network failures retry, with a cap. Server rejections do not: once the
 *   server has answered "no" (stock gone, product delisted, branch moved) a
 *   human decides. The entry parks as a conflict instead of spinning in a
 *   retry loop, because the money has already been taken and no loop can
 *   make the stock come back.
 * - The queue is a liability: the cash has left the customer's hands. A
 *   corrupted store is quarantined, never silently dropped, and the UI is
 *   told.
 *
 * All the transition functions are pure (in -> out, no mutation, no
 * storage) so a test can assert the whole lifecycle without a browser.
 */

export const QUEUE_KEY = 'zenpos.pos.offline.queue';
export const HISTORY_KEY = 'zenpos.pos.offline.history';

/** How many sync attempts may fail with "no server answer" before a human looks. */
export const MAX_NETWORK_ATTEMPTS = 3;

/** How many "recorded from the queue" records the till keeps for display. */
export const HISTORY_LIMIT = 20;

// ---------------------------------------------------------------------------
// storage I/O (the only impure part; `storage` is a localStorage-like object)
// ---------------------------------------------------------------------------

/**
 * Read the queue. A store that cannot be parsed — or that holds something
 * that is not an array — comes back empty with `corrupted: true` and the
 * raw text, so the caller can quarantine it instead of dropping it.
 */
export const loadQueue = (storage) => {
  try {
    const raw = storage.getItem(QUEUE_KEY);
    if (raw == null) return { entries: [], corrupted: false };
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) throw new Error('queue store is not an array');
    return { entries: parsed, corrupted: false };
  } catch {
    return { entries: [], corrupted: true, raw: storage.getItem(QUEUE_KEY) };
  }
};

/** Set an unreadable store aside under its own key. Best effort. */
export const quarantineCorruptStore = (storage, raw, at = Date.now()) => {
  if (raw == null) return;
  try {
    storage.setItem(`${QUEUE_KEY}.corrupt-${at}`, raw);
  } catch {
    // Storage full or unavailable: the corrupt flag in the UI carries the
    // warning, and the raw text was already on screen in the store.
  }
};

export const saveQueue = (storage, entries) => {
  storage.setItem(QUEUE_KEY, JSON.stringify(entries));
};

export const loadHistory = (storage) => {
  try {
    const raw = storage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

export const saveHistory = (storage, history) => {
  storage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-HISTORY_LIMIT)));
};

// ---------------------------------------------------------------------------
// transitions (pure)
// ---------------------------------------------------------------------------

/**
 * Add an entry, or return the queue unchanged when the basket is already
 * queued under the same reference. Entries are normalised here so a
 * hand-built entry cannot arrive without its lifecycle fields.
 */
export const enqueueSale = (entries, entry) => {
  if (!entry || !entry.clientReference) return entries;
  if (entries.some((existing) => existing.clientReference === entry.clientReference)) {
    return entries;
  }
  return [
    ...entries,
    {
      clientReference: entry.clientReference,
      payload: entry.payload,
      snapshot: entry.snapshot || {},
      branch: entry.branch || null,
      queuedAt: entry.queuedAt || null,
      attempts: 0,
      status: 'queued',
      conflict: null,
    },
  ];
};

const withEntry = (entries, clientReference, update) =>
  entries.map((entry) => (entry.clientReference === clientReference ? update(entry) : entry));

export const markInFlight = (entries, clientReference) =>
  withEntry(entries, clientReference, (entry) => ({ ...entry, status: 'in-flight' }));

/**
 * One sync attempt got no answer from the server. The entry retries — until
 * it cannot, when it parks as a conflict for a human.
 */
export const recordNetworkFailure = (entries, clientReference, at) =>
  withEntry(entries, clientReference, (entry) => {
    const attempts = (entry.attempts || 0) + 1;
    if (attempts >= MAX_NETWORK_ATTEMPTS) {
      return {
        ...entry,
        attempts,
        status: 'conflict',
        conflict: {
          message: 'The server could not be reached after several sync attempts.',
          at,
        },
      };
    }
    return { ...entry, attempts, status: 'queued' };
  });

/** The server answered "no": the entry waits for a person, not a retry. */
export const parkConflict = (entries, clientReference, message, at) =>
  withEntry(entries, clientReference, (entry) => ({
    ...entry,
    status: 'conflict',
    conflict: { message, at },
  }));

/** A person looked at a conflict and wants another go. */
export const clearConflict = (entries, clientReference) =>
  withEntry(entries, clientReference, (entry) =>
    entry.status === 'conflict'
      ? { ...entry, status: 'queued', conflict: null, attempts: 0 }
      : entry,
  );

/**
 * The sale is booked. The entry leaves the queue and a small record goes to
 * the till's history so the cashier can see what was recovered.
 */
export const markSynced = (entries, clientReference, { saleId = null, saleNumber = '', at = null }) => {
  const entry = entries.find((existing) => existing.clientReference === clientReference) || {};
  const record = {
    clientReference,
    saleId,
    saleNumber,
    total: entry.snapshot?.total ?? null,
    at,
  };
  return {
    entries: entries.filter((existing) => existing.clientReference !== clientReference),
    record,
  };
};

// ---------------------------------------------------------------------------
// selectors
// ---------------------------------------------------------------------------

export const nextQueued = (entries) => entries.find((entry) => entry.status === 'queued') || null;

export const queuedEntries = (entries) =>
  entries.filter((entry) => entry.status === 'queued' || entry.status === 'in-flight');

export const conflictEntries = (entries) =>
  entries.filter((entry) => entry.status === 'conflict');
