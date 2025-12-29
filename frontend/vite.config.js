import { defineConfig } from 'vite';
import { resolve } from 'path';
import fs from 'fs';

// Simple plugin to bump version in landing.html before build
const versionBumper = () => {
    return {
        name: 'version-bumper',
        buildStart() {
            const filePath = resolve(__dirname, 'landing.html');
            if (fs.existsSync(filePath)) {
                let content = fs.readFileSync(filePath, 'utf-8');
                const pattern = /(>v)(\d+)\.(\d+)\.(\d+)(.*<)/;
                const match = content.match(pattern);

                if (match) {
                    const major = match[2];
                    const minor = match[3];
                    const patch = parseInt(match[4]) + 1;
                    const suffix = match[5];
                    const newVersion = `${match[1]}${major}.${minor}.${patch}${suffix}`;

                    content = content.replace(pattern, newVersion);
                    fs.writeFileSync(filePath, content);
                    console.log(`\n🚀 Auto-bumped version to v${major}.${minor}.${patch}\n`);
                }
            }
        }
    };
};

export default defineConfig({
    base: '/driveit_v2/',
    plugins: [versionBumper()],
    build: {
        outDir: '../docs',
        emptyOutDir: true,
        rollupOptions: {
            input: {
                landing: resolve(__dirname, 'landing.html'),
                redir: resolve(__dirname, 'redir.html'),
                test: resolve(__dirname, 'test.html'),
            },
        },
    },
});
