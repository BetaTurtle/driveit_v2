import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
    build: {
        outDir: '../docs',
        emptyOutDir: true,
        rollupOptions: {
            input: {
                landing: resolve(__dirname, 'landing.html'),
                redir: resolve(__dirname, 'redir.html'),
            },
        },
    },
});
