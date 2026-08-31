import '@testing-library/jest-dom/vitest';
import { beforeEach } from 'vitest';

// Node's experimental webstorage global shadows jsdom's localStorage under
// vitest and its methods are non-functional without --localstorage-file.
// Install a real in-memory Storage so the app's persistence code behaves in
// tests exactly as it does in a browser.
class MemoryStorage {
  #map = new Map();

  getItem(key) {
    return this.#map.has(key) ? this.#map.get(key) : null;
  }

  setItem(key, value) {
    this.#map.set(String(key), String(value));
  }

  removeItem(key) {
    this.#map.delete(key);
  }

  clear() {
    this.#map.clear();
  }

  get length() {
    return this.#map.size;
  }

  key(i) {
    return [...this.#map.keys()][i] ?? null;
  }
}

if (typeof window.localStorage?.clear !== 'function') {
  Object.defineProperty(window, 'localStorage', { value: new MemoryStorage(), configurable: true });
}

// Tabs and investigations persist to window.localStorage; without this, one
// test's saved state would leak into the next render.
beforeEach(() => {
  window.localStorage.clear();
});
