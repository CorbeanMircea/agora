/**
 * Singleton Socket.IO client for the phone shell.
 *
 * The server URL is derived at runtime from window.location.origin so the
 * phone automatically connects to whichever Fastify instance served the page
 * — works on LAN without any build-time configuration.
 */
import { io, type Socket } from 'socket.io-client';
import { browser } from '$app/environment';

let _socket: Socket | null = null;

/**
 * Returns the singleton Socket.IO client, creating it on first call.
 * Safe to call multiple times — always returns the same instance.
 *
 * Must only be called in browser context.
 */
export function getSocket(): Socket {
    if (!browser) {
        throw new Error('getSocket() must only be called in a browser context');
    }

    if (_socket !== null) return _socket;

    // Connect to the Fastify server that served this page.
    const serverUrl = window.location.origin;

    _socket = io(serverUrl, {
        transports: ['websocket'],
        autoConnect: true,
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: Infinity,
    });

    return _socket;
}

/**
 * Disconnects and destroys the singleton socket.
 * Call during cleanup if needed.
 */
export function destroySocket(): void {
    if (_socket !== null) {
        _socket.disconnect();
        _socket = null;
    }
}