import { useEffect } from 'react';

/**
 * Offline sale capture is not implemented.
 *
 * It remains a genuine gap rather than a hidden one: a queued sale would have
 * to be replayed with its own idempotency key and a fixed price snapshot, and
 * the previous version of this hook posted to an Express endpoint that no
 * longer exists. Until that lands, the POS requires a connection and says so.
 */
const useOfflineSync = (token) => {
  useEffect(() => {
    if (!token) return undefined;
    return undefined;
  }, [token]);

  return null;
};

export default useOfflineSync;
