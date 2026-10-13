import { describe, expect, it } from 'vitest';

import {
  HISTORY_LIMIT,
  HISTORY_KEY,
  MAX_NETWORK_ATTEMPTS,
  QUEUE_KEY,
  clearConflict,
  conflictEntries,
  enqueueSale,
  loadHistory,
  loadQueue,
  markInFlight,
  markSynced,
  nextQueued,
  parkConflict,
  quarantineCorruptStore,
  queuedEntries,
  recordNetworkFailure,
  saveHistory,
  saveQueue,
} from '../offlineQueue';

/** A localStorage double: enough of the interface, none of the browser. */
const makeStorage = () => {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => {
      map.set(key, String(value));
    },
    removeItem: (key) => {
      map.delete(key);
    },
    _dump: () => Object.fromEntries(map),
  };
};

const entry = (reference, extra = {}) => ({
  clientReference: reference,
  payload: {
    client_reference: reference,
    payment_method: 'CASH',
    items: [{ product: 1, quantity: 2 }],
  },
  snapshot: { total: 200, lines: [{ product: 1, name: 'Milk 1L', price: 100, quantity: 2 }] },
  branch: 'b-1',
  queuedAt: 1000,
  ...extra,
});

describe('enqueueSale', () => {
  it('normalises an entry with its lifecycle fields', () => {
    const [queued] = enqueueSale([], entry('ref-1'));
    expect(queued).toMatchObject({
      clientReference: 'ref-1',
      status: 'queued',
      attempts: 0,
      conflict: null,
    });
    expect(queued.payload.client_reference).toBe('ref-1');
  });

  it('keeps FIFO order for distinct baskets', () => {
    const entries = enqueueSale(enqueueSale([], entry('ref-1')), entry('ref-2'));
    expect(entries.map((e) => e.clientReference)).toEqual(['ref-1', 'ref-2']);
    expect(nextQueued(entries).clientReference).toBe('ref-1');
  });

  it('never queues the same reference twice — that would be a second sale', () => {
    const entries = enqueueSale(enqueueSale([], entry('ref-1')), entry('ref-1'));
    expect(entries).toHaveLength(1);
  });

  it('ignores an entry without a reference rather than queueing an unkeyed sale', () => {
    expect(enqueueSale([], entry('ref-1'))).toHaveLength(1);
    expect(enqueueSale([], { payload: {} })).toHaveLength(0);
    expect(enqueueSale([], entry('ref-1', { clientReference: '' }))).toHaveLength(0);
  });

  it('does not mutate the queue it is given', () => {
    const before = enqueueSale([], entry('ref-1'));
    enqueueSale(before, entry('ref-2'));
    expect(before).toHaveLength(1);
  });
});

describe('the sync lifecycle', () => {
  it('walks queued -> in-flight -> synced, in FIFO order', () => {
    let entries = enqueueSale(enqueueSale([], entry('ref-1')), entry('ref-2'));

    entries = markInFlight(entries, 'ref-1');
    expect(entries[0].status).toBe('in-flight');
    // The in-flight entry is out of rotation until it finishes.
    expect(nextQueued(entries).clientReference).toBe('ref-2');

    const { entries: after, record } = markSynced(entries, 'ref-2', {
      saleId: 42,
      saleNumber: 'ZN-0042',
      at: 2000,
    });
    expect(after.map((e) => e.clientReference)).toEqual(['ref-1']);
    expect(record).toMatchObject({ clientReference: 'ref-2', saleId: 42, saleNumber: 'ZN-0042' });
    expect(record.total).toBe(200); // the till's own money record
  });

  it('retries a network failure until the cap, then parks for a human', () => {
    let entries = enqueueSale([], entry('ref-1'));
    entries = markInFlight(entries, 'ref-1');

    for (let attempt = 1; attempt < MAX_NETWORK_ATTEMPTS; attempt += 1) {
      entries = recordNetworkFailure(entries, 'ref-1', 5000 + attempt);
      expect(entries[0].attempts).toBe(attempt);
      expect(entries[0].status).toBe('queued'); // will be asked again
    }
    entries = markInFlight(entries, 'ref-1');
    entries = recordNetworkFailure(entries, 'ref-1', 6000);
    expect(entries[0].status).toBe('conflict');
    expect(entries[0].conflict.message).toMatch(/could not be reached/);
    expect(conflictEntries(entries)).toHaveLength(1);
  });

  it('parks a server rejection immediately — a 400 is an answer, not a network fault', () => {
    let entries = enqueueSale([], entry('ref-1'));
    entries = markInFlight(entries, 'ref-1');
    entries = parkConflict(entries, 'ref-1', 'Product 7 no longer exists.', 7000);
    expect(entries[0].status).toBe('conflict');
    expect(entries[0].attempts).toBe(0); // no retries were spent
    expect(entries[0].conflict).toMatchObject({ message: 'Product 7 no longer exists.', at: 7000 });
  });

  it('lets a person release a conflict back into the queue, with a clean slate', () => {
    let entries = parkConflict(enqueueSale([], entry('ref-1')), 'ref-1', 'x', 1);
    entries[0] = { ...entries[0], attempts: 2 };
    entries = clearConflict(entries, 'ref-1');
    expect(entries[0].status).toBe('queued');
    expect(entries[0].conflict).toBeNull();
    expect(entries[0].attempts).toBe(0);
    expect(nextQueued(entries).clientReference).toBe('ref-1');
  });

  it('leaves non-conflicting entries untouched when clearing one', () => {
    let entries = enqueueSale(enqueueSale([], entry('ref-1')), entry('ref-2'));
    entries = parkConflict(entries, 'ref-2', 'x', 1);
    entries = clearConflict(entries, 'ref-2');
    expect(entries.find((e) => e.clientReference === 'ref-1')).toMatchObject({ status: 'queued' });
    expect(entries.find((e) => e.clientReference === 'ref-2')).toMatchObject({ status: 'queued' });
  });
});

describe('storage', () => {
  it('round-trips a queue through the store', () => {
    const storage = makeStorage();
    const entries = enqueueSale([], entry('ref-1'));
    saveQueue(storage, entries);
    const { entries: loaded, corrupted } = loadQueue(storage);
    expect(corrupted).toBe(false);
    expect(loaded).toEqual(entries);
  });

  it('reports an empty store as empty, not corrupted', () => {
    const { entries, corrupted } = loadQueue(makeStorage());
    expect(entries).toEqual([]);
    expect(corrupted).toBe(false);
  });

  it('flags an unreadable store as corrupted and carries the raw text', () => {
    const storage = makeStorage();
    storage.setItem(QUEUE_KEY, '{not-json');
    const { entries, corrupted, raw } = loadQueue(storage);
    expect(entries).toEqual([]);
    expect(corrupted).toBe(true);
    expect(raw).toBe('{not-json');
  });

  it('flags a store that holds the wrong shape as corrupted', () => {
    const storage = makeStorage();
    storage.setItem(QUEUE_KEY, JSON.stringify({ entries: [] }));
    expect(loadQueue(storage).corrupted).toBe(true);
  });

  it('quarantines the raw text under its own key', () => {
    const storage = makeStorage();
    storage.setItem(QUEUE_KEY, '{not-json');
    quarantineCorruptStore(storage, '{not-json', 1234);
    expect(storage._dump()[`${QUEUE_KEY}.corrupt-1234`]).toBe('{not-json');
    // The original key is left for whoever reviews the device.
    expect(storage._dump()[QUEUE_KEY]).toBe('{not-json');
  });

  it('keeps a bounded history of recovered sales', () => {
    const storage = makeStorage();
    const records = Array.from({ length: HISTORY_LIMIT + 5 }, (_, i) => ({
      clientReference: `ref-${i}`,
      saleId: i,
      saleNumber: `ZN-${i}`,
      total: 1,
      at: i,
    }));
    let history = [];
    for (const record of records) {
      history = [...history, record];
      saveHistory(storage, history);
    }
    const loaded = loadHistory(storage);
    expect(loaded).toHaveLength(HISTORY_LIMIT);
    expect(loaded[loaded.length - 1].clientReference).toBe(`ref-${HISTORY_LIMIT + 4}`);
  });

  it('survives a mangled history store', () => {
    const storage = makeStorage();
    storage.setItem(HISTORY_KEY, 'oops');
    expect(loadHistory(storage)).toEqual([]);
  });
});

describe('selectors', () => {
  it('partitions the queue into waiting and conflicting', () => {
    let entries = enqueueSale(enqueueSale([], entry('ref-1')), entry('ref-2'));
    entries = parkConflict(entries, 'ref-2', 'x', 1);
    expect(queuedEntries(entries).map((e) => e.clientReference)).toEqual(['ref-1']);
    expect(conflictEntries(entries).map((e) => e.clientReference)).toEqual(['ref-2']);
  });
});
