import { create } from 'zustand';

/**
 * The till's cart.
 *
 * Totals here are a display convenience only: the server recomputes every
 * line from the catalogue and the sale total from those lines, and rejects a
 * client total that disagrees. Nothing in this store is trusted by the API.
 */
export const usePOSStore = create((set, get) => ({
  cart: [],

  addToCart: (product, quantity = 1) => {
    const { cart } = get();
    const existing = cart.find((item) => item.id === product.id);
    if (existing) {
      set({
        cart: cart.map((item) =>
          item.id === product.id
            ? { ...item, quantity: item.quantity + quantity }
            : item,
        ),
      });
    } else {
      set({ cart: [...cart, { ...product, quantity }] });
    }
  },

  setQuantity: (id, quantity) => {
    const next = Math.max(1, Math.floor(Number(quantity) || 1));
    set({
      cart: get().cart.map((item) =>
        item.id === id ? { ...item, quantity: next } : item,
      ),
    });
  },

  updateQuantity: (id, delta) => {
    const { cart } = get();
    set({
      cart: cart.map((item) => {
        if (item.id !== id) return item;
        const next = Math.max(1, item.quantity + delta);
        return { ...item, quantity: next };
      }),
    });
  },

  removeFromCart: (id) => {
    set({ cart: get().cart.filter((item) => item.id !== id) });
  },

  clearCart: () => set({ cart: [] }),

  getQuantityFor: (id) => get().cart.find((item) => item.id === id)?.quantity || 0,

  getLineTotal: (item) => Number(item.price || 0) * item.quantity,

  getTotal: () =>
    get().cart.reduce((sum, item) => sum + Number(item.price || 0) * item.quantity, 0),

  getCount: () => get().cart.reduce((sum, item) => sum + item.quantity, 0),
}));
