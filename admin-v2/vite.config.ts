import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// =====================================================================
// admin-v2 Vite config (S2-DEV-013 / ADR-0042)
// ---------------------------------------------------------------------
// 关键关切（胡桃 ADR-0042 review §5.1）:
// 1. dev proxy 路径必须与 nginx prod 反代一致 → /api/v1 直转 backend:8000
// 2. base path 设 /admin-v2/ 与 nginx location 一致（共存 v1 在 /admin/）
// 3. 按需引入 antd 避免全量 bundle（CSS-in-JS 5.x tree-shaking）
// =====================================================================

export default defineConfig({
  base: '/admin-v2/',  // nginx location 一致
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    // dev proxy 必须与 nginx prod 反代路径一致（acceptance #8 ）
    // nginx 配置：location /api/v1/ -> backend:8000
    // dev 配置 ：proxy /api/v1 -> http://localhost:8000
    // path 一致性 CI gate 在 scripts/check-api-path-consistency.mjs
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    // 按需 chunk 拆分降 bundle 大小（dist gzip < 2MB budget gate）
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'antd-vendor': ['antd', '@ant-design/icons'],
          'data-vendor': ['@tanstack/react-query', 'axios', 'zustand'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
