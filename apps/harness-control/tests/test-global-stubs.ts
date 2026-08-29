const originalDescriptors = new Map<PropertyKey, PropertyDescriptor | undefined>()

export function stubGlobal(key: PropertyKey, value: unknown): void {
  if (!originalDescriptors.has(key)) {
    originalDescriptors.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
  }
  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value
  })
}

export function restoreGlobalStubs(): void {
  for (const [key, descriptor] of originalDescriptors) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else Reflect.deleteProperty(globalThis, key)
  }
  originalDescriptors.clear()
}
