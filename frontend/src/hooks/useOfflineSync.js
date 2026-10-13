import { useCallback, useEffect, useRef, useState } from 'react';

import api, { apiError } from '../services/api';
import {
  conflictEntries,
  clearConflict,
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
} from '../lib/offlineQueue';

/**
 * Offline sale sync.
 *
 * The till rings cash sales while the connection is down; this hook owns the
 * queue that carries them back to the server when it returns. The queue's
 * rules live in `lib/offlineQueue.js` (pure, unit-tested); this hook owns
 * the browser: the online/offline events, the network calls and the state
 * the UI renders.
 *
 * The safety argument, in one paragraph: every queued entry carries the
 * basket's `client_reference`, and the server treats that as an idempotency
 * key — repeating it returns the first sale. So the two scary cases both
 * collapse into the same safe behaviour. (1) The sale never reached the
 * server: the replay books it. (2) The sale DID reach the server and only
 * the response was lost: the replay returns the existing sale, and no second
 * stock movement exists. Either way the cashier sees exactly one sale for
 * the money that was taken.
 *
 * M-Pesa is deliberately not queued: an STK push is live money on a phone
 * screen, and replaying it later would be a different charge at a different
 * moment. The till says so and offers cash instead.
 *
 * Mounted by the app shell (so a queue syncs even when the cashier is on
 * another page) and by the POS (for the banner); a module-level lock keeps
 * the two from double-POSTing the same entry.
 */

// One flush at a time across the whole app: the queue is shared storage, and
// two components watching `online` in the same tick would otherwise race it.
let activeFlush = null;

// The queue lives in localStorage and every mounted instance (the app shell
// and the till) holds its own React copy. Storage is the single source of
// truth, so any write notifies the other instances to re-read — otherwise a
// flush won by one instance would leave the other's banner stale.
const QUEUE_CHANGED_EVENT = 'zenpos:offline-queue';

const notifyQueueChanged = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(QUEUE_CHANGED_EVENT));
  }
};

/**
 * No HTTP response at all — offline, timed out, or the answer was lost.
 * Anything with a response is a server decision (possibly "no"), which is a
 * different animal: it parks, it does not retry.
 */
const isNetworkFailure = (error) => Boolean(error) && !error.response;

const readToken = (storage) => {
  try {
    return storage ? storage.getItem('token') : null;
  } catch {
    return null;
  }
};

const useOfflineSync = () => {
  const storageRef = useRef(
    typeof window !== 'undefined' ? window.localStorage : null,
  );
  const storage = storageRef.current;

  const [online, setOnline] = useState(
    () => (typeof navigator === 'undefined' ? true : navigator.onLine),
  );
  const [queue, setQueue] = useState(() => (storage ? loadQueue(storage).entries : []));
  const [history, setHistory] = useState(() => (storage ? loadHistory(storage) : []));
  const [corruptWarning, setCorruptWarning] = useState(false);

  const refresh = useCallback(() => {
    if (!storage) return;
    const { entries, corrupted, raw } = loadQueue(storage);
    if (corrupted) {
      // The money is not lost: the raw store text is set aside under its own
      // key, and the warning tells the till to call a human.
      quarantineCorruptStore(storage, raw);
    }
    setQueue(entries);
    setHistory(loadHistory(storage));
    setCorruptWarning(corrupted);
  }, [storage]);

  /**
   * Walk the queue, FIFO, one POST at a time, until it is empty, the
   * network drops, or a sale needs a human. Re-reads storage before every
   * step, so a second tab of the same till cannot interleave a decision.
   */
  const flush = useCallback(async () => {
    if (!storage || activeFlush) return activeFlush;
    activeFlush = (async () => {
      for (;;) {
        if (!navigator.onLine || !readToken(storage)) {
          refresh();
          return;
        }
        const { entries: loaded } = loadQueue(storage);
        const entry = nextQueued(loaded);
        if (!entry) {
          setQueue(loaded);
          return;
        }
        saveQueue(storage, markInFlight(loaded, entry.clientReference));
        try {
          const { data } = await api.post('/sales/', entry.payload);
          const { entries: after, record } = markSynced(loaded, entry.clientReference, {
            saleId: data?.id ?? null,
            saleNumber: data?.sale_number || '',
            at: Date.now(),
          });
          saveQueue(storage, after);
          saveHistory(storage, [...loadHistory(storage), record]);
          notifyQueueChanged();
          refresh();
        } catch (error) {
          const { entries: current } = loadQueue(storage);
          if (isNetworkFailure(error)) {
            // We just proved the connection is gone again: stop and wait for
            // the `online` event. The attempt count rides along, so the cap
            // in `recordNetworkFailure` is eventually enforced.
            saveQueue(storage, recordNetworkFailure(current, entry.clientReference, Date.now()));
            notifyQueueChanged();
            refresh();
            return;
          }
          // A server answer: the sale is parked for a person, with the
          // server's own words on why.
          saveQueue(
            storage,
            parkConflict(
              current,
              entry.clientReference,
              apiError(error, 'The queued sale was rejected by the server.'),
              Date.now(),
            ),
          );
          notifyQueueChanged();
          refresh();
          return;
        }
      }
    })();
    try {
      return await activeFlush;
    } finally {
      activeFlush = null;
    }
  }, [storage, refresh]);

  const enqueue = useCallback(
    (entry) => {
      if (!storage) return;
      const { entries, corrupted, raw } = loadQueue(storage);
      if (corrupted) quarantineCorruptStore(storage, raw);
      saveQueue(storage, enqueueSale(entries, entry));
      notifyQueueChanged();
      refresh();
      if (navigator.onLine) flush(); // a blip may have passed already
    },
    [storage, refresh, flush],
  );

  const retryConflict = useCallback(
    (clientReference) => {
      if (!storage) return;
      const { entries } = loadQueue(storage);
      saveQueue(storage, clearConflict(entries, clientReference));
      notifyQueueChanged();
      refresh();
      if (navigator.onLine) flush();
    },
    [storage, refresh, flush],
  );

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onOnline = () => {
      setOnline(true);
      flush();
    };
    const onOffline = () => setOnline(false);
    const onAuth = () => flush(); // a re-login gives the queue a fresh token
    const onQueueChanged = () => refresh(); // another instance wrote the store
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    window.addEventListener('zenpos:auth', onAuth);
    window.addEventListener(QUEUE_CHANGED_EVENT, onQueueChanged);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      window.removeEventListener('zenpos:auth', onAuth);
      window.removeEventListener(QUEUE_CHANGED_EVENT, onQueueChanged);
    };
  }, [flush, refresh]);

  // The browser opens with a queue (closed during the outage, or the network
  // is back): no `online` event fires on startup, so sync once on mount.
  const didInitialFlush = useRef(false);
  useEffect(() => {
    if (didInitialFlush.current) return;
    didInitialFlush.current = true;
    if (navigator.onLine) flush();
  }, [flush]);

  return {
    online,
    queue,
    queued: queuedEntries(queue),
    conflicts: conflictEntries(queue),
    history,
    corruptWarning,
    enqueue,
    retryConflict,
    flush,
  };
};

export default useOfflineSync;
