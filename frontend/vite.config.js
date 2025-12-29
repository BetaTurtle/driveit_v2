import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
    base: '/driveit_v2/',
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
