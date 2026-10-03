import { useEffect, useRef } from 'react';
import api from '../services/api';
import { usePOSStore } from '../store/posStore';
import toast from 'react-hot-toast';

export const useBarcodeScanner = () => {
  const addToCart = usePOSStore((state) => state.addToCart);
  const buffer = useRef('');
  const lastKeyTime = useRef(0);

  useEffect(() => {
    const handleKeyDown = async (e) => {
      const currentTime = new Date().getTime();
      
      // If delay between keys is < 50ms, it's likely a scanner
      if (currentTime - lastKeyTime.current > 50) {
        buffer.current = '';
      }

      if (e.key === 'Enter') {
        if (buffer.current.length > 3) {
          try {
            const res = await api.get(`/v1/inventory/products/${buffer.current}`);
            addToCart(res.data);
            toast.success(`Added ${res.data.name}`);
            buffer.current = '';
          } catch (err) {
            toast.error('Product not found');
            buffer.current = '';
          }
        }
      } else if (e.key.length === 1) {
        buffer.current += e.key;
      }

      lastKeyTime.current = currentTime;
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [addToCart]);
};
