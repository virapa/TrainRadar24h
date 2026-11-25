export type Route = { kind: 'map' } | { kind: 'train'; id: string } | { kind: 'station'; id: string }

export function parsePath(path: string): Route {
  const m = /^\/([ts])\/(.+)$/.exec(path)
  if (!m) return { kind: 'map' }
  const id = decodeURIComponent(m[2])
  return m[1] === 't' ? { kind: 'train', id } : { kind: 'station', id }
}

export function buildPath(route: Route): string {
  if (route.kind === 'map') return '/'
  const id = encodeURIComponent(route.id).replace(/%3A/g, ':')
  return `/${route.kind === 'train' ? 't' : 's'}/${id}`
}
