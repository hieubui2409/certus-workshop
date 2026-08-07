import { existsSync } from 'node:fs';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// Đa trang có điều kiện: app chính luôn có; trang giảng viên (learning.html) chỉ
// thêm vào build khi file còn tồn tại. Bản build repo sinh viên loại learning.html
// đi, nên vòng này bỏ qua nó và build KHÔNG vỡ vì trỏ tới file vắng mặt.
const learningHtml = fileURLToPath(new URL('./learning.html', import.meta.url));
const input: Record<string, string> = {
  main: fileURLToPath(new URL('./index.html', import.meta.url)),
};
if (existsSync(learningHtml)) {
  input.learning = learningHtml;
}

// Backend FastAPI chạy ở 8000; khi VITE_USE_MOCK=0 thì proxy này là đường ra thật.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: { input },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
