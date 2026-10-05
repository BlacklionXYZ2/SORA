const DATABASE_NAME = "sora-paired-device-v1";
const STORE_NAME = "credentials";

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME, { keyPath: "origin" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Paired-device storage failed."));
  });
}

function transact(mode, action) {
  return openDatabase().then((database) => new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, mode);
    const store = transaction.objectStore(STORE_NAME);
    const request = action(store);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error || new Error("Paired-device storage failed."));
    transaction.oncomplete = () => database.close();
    transaction.onabort = () => database.close();
  }));
}

export function loadPairedDevice(origin = globalThis.location.origin) {
  return transact("readonly", (store) => store.get(origin));
}

export function savePairedDevice(device, origin = globalThis.location.origin) {
  const record = {
    origin,
    deviceId: String(device.device_id),
    deviceCredential: String(device.device_credential),
    scopes: Array.isArray(device.scopes) ? [...device.scopes] : [],
  };
  return transact("readwrite", (store) => store.put(record));
}

export function clearPairedDevice(origin = globalThis.location.origin) {
  return transact("readwrite", (store) => store.delete(origin));
}
