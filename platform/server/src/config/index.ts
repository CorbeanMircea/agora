/**
 * Platform configuration — loaded once at startup from environment variables.
 * All server code imports from here; nothing reads process.env directly.
 */
export const config = {
    host: process.env['HOST'] ?? '0.0.0.0',
    port: parseInt(process.env['PORT'] ?? '3000', 10),
    corsOrigin: process.env['CORS_ORIGIN'] ?? '*',
    nodeEnv: process.env['NODE_ENV'] ?? 'development',
} as const;