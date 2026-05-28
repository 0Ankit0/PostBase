import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: ['babel-plugin-react-compiler'],
      },
    }),
  ],
  resolve: {
    alias: [
      {
        find: '@',
        replacement: fileURLToPath(new URL('./src', import.meta.url)),
      },
      {
        find: 'next/link',
        replacement: fileURLToPath(new URL('./src/compat/next/link.tsx', import.meta.url)),
      },
      {
        find: 'next/navigation',
        replacement: fileURLToPath(new URL('./src/compat/next/navigation.ts', import.meta.url)),
      },
      {
        find: 'next/font/google',
        replacement: fileURLToPath(new URL('./src/compat/next/font-google.ts', import.meta.url)),
      },
      {
        find: /^next$/,
        replacement: fileURLToPath(new URL('./src/compat/next/index.ts', import.meta.url)),
      },
    ],
  },
  define: {
    'process.env': 'import.meta.env',
  },
  envPrefix: ['VITE_', 'NEXT_PUBLIC_'],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
  preview: {
    host: '0.0.0.0',
    port: 3000,
  },
});