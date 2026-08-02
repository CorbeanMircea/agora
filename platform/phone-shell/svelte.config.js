import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
    kit: {
        adapter: adapter({
            // Output to dist/ — Fastify will serve this directory at /phone
            pages: 'dist',
            assets: 'dist',
            fallback: 'index.html',
            precompress: false,
            strict: false,
        }),
        // The phone shell is served at /phone by the Fastify server
        paths: {
            base: '/phone',
        },
    },
};

export default config;