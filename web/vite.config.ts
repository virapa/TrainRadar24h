import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

const WORKER_PATH = '/maplibre-gl-worker.js'

/**
 * Sirve el worker de MapLibre tal cual, sin transformarlo. MapLibre 6 lo busca junto a su propio
 * módulo, pero el empaquetador los separa; y si Vite lo transforma en desarrollo le inyecta código
 * de página que no funciona dentro de un worker. La app le indica esta ruta con setWorkerUrl().
 */
function maplibreWorker(): Plugin {
  const file = fileURLToPath(new URL('./node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs', import.meta.url))
  return {
    name: 'maplibre-worker',
    configureServer(server) {
      server.middlewares.use(WORKER_PATH, (_req, res) => {
        res.setHeader('Content-Type', 'text/javascript')
        res.end(readFileSync(file))
      })
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: WORKER_PATH.slice(1), source: readFileSync(file) })
    },
  }
}

// En desarrollo, /api se reenvía a la API que corre en Docker.
export default defineConfig({
  plugins: [react(), maplibreWorker()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8090' },
  },
  test: { environment: 'jsdom' },
})
