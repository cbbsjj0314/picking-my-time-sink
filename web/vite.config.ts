import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

const configDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(configDir, '..')

function parseAllowedHosts(value: string | undefined): string[] {
  if (!value) {
    return []
  }

  return value
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean)
}

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, repoRoot, '')
  const webEnv = loadEnv(mode, configDir, '')
  const allowedHosts = parseAllowedHosts(
    webEnv.DEV_ALLOWED_HOSTS ?? rootEnv.DEV_ALLOWED_HOSTS,
  )

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      allowedHosts,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
