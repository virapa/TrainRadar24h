import { deleteSubscription, getVapidKey, saveSubscription } from '../api/client'

export type PushResult = 'ok' | 'denied' | 'unsupported' | 'unconfigured' | 'error'

export function urlBase64ToUint8Array(base64url: string): Uint8Array {
  const padded = base64url + '='.repeat((4 - (base64url.length % 4)) % 4)
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

/** Los avisos necesitan service worker, Push API y contexto seguro (HTTPS o localhost). */
export function pushSupported(): boolean {
  return window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

export async function pushEnabled(): Promise<boolean> {
  if (!pushSupported() || Notification.permission !== 'granted') return false
  const reg = await navigator.serviceWorker.getRegistration()
  return Boolean(reg && (await reg.pushManager.getSubscription()))
}

export async function enablePush(): Promise<PushResult> {
  if (!pushSupported()) return 'unsupported'
  try {
    const { key } = await getVapidKey()
    if (!key) return 'unconfigured'
    if ((await Notification.requestPermission()) !== 'granted') return 'denied'
    const reg = await navigator.serviceWorker.ready
    const sub =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key).buffer as ArrayBuffer,
      }))
    const json = sub.toJSON()
    if (!json.endpoint || !json.keys) return 'error'
    await saveSubscription({ endpoint: json.endpoint, keys: json.keys })
    return 'ok'
  } catch {
    return 'error'
  }
}

export async function disablePush(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  await sub?.unsubscribe()
  await deleteSubscription().catch(() => undefined)
}
