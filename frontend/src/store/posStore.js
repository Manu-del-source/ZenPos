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

  getLineAmounts: (item) => {
    const gross = Math.round((Number(item.price || 0) * Number(item.quantity || 0) + Number.EPSILON) * 100) / 100;
    const rate = Number(item.tax_rate_rate || 0);
    if (!rate || item.tax_rate_is_inclusive == null) {
      return { subtotal: gross, tax: 0, total: gross };
    }
    if (item.tax_rate_is_inclusive) {
      const tax = Math.round((gross * rate / (100 + rate) + Number.EPSILON) * 100) / 100;
      return { subtotal: Math.round((gross - tax + Number.EPSILON) * 100) / 100, tax, total: gross };
    }
    const tax = Math.round((gross * rate / 100 + Number.EPSILON) * 100) / 100;
    return { subtotal: gross, tax, total: Math.round((gross + tax + Number.EPSILON) * 100) / 100 };
  },

  getSubtotal: () =>
    Math.round((get().cart.reduce((sum, item) => sum + get().getLineAmounts(item).subtotal, 0) + Number.EPSILON) * 100) / 100,

  getTaxTotal: () =>
    Math.round((get().cart.reduce((sum, item) => sum + get().getLineAmounts(item).tax, 0) + Number.EPSILON) * 100) / 100,

  getLineTotal: (item) => get().getLineAmounts(item).total,

  getTotal: () =>
    Math.round((get().cart.reduce((sum, item) => sum + get().getLineAmounts(item).total, 0) + Number.EPSILON) * 100) / 100,

  getCount: () => get().cart.reduce((sum, item) => sum + item.quantity, 0),
}));
