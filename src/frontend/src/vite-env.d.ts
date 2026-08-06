/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Công tắc backend giả — SDD 08 §7. Mặc định BẬT. */
  readonly VITE_USE_MOCK?: string;
  /** Gốc của REST + SSE khi VITE_USE_MOCK=0. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
