<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { base } from '$app/paths';
    import { browser } from '$app/environment';
    import { getSocket } from '$lib/socket.js';
    import { gameState } from '$lib/gameState.svelte.js';

    let { children } = $props();

    onMount(() => {
        if (!browser) return;

        const socket = getSocket();

        socket.on('connect', () => gameState.setConnected(true));
        socket.on('disconnect', () => gameState.setConnected(false));

        socket.on('player:joined', (data: { players: { id: string; nickname: string }[] }) => {
            gameState.setPlayers(data.players);
        });

        socket.on('round:prompting', (data: { roundNumber: number; state: string; deadline?: number }) => {
            gameState.setPhase('prompting');
            gameState.setDeadline(data.deadline ?? null);
            // Navigate to the answer screen; if prompts haven't arrived yet the
            // screen will show a "loading prompts…" state until round:prompts fires.
            goto(`${base}/answer`);
        });

        socket.on('round:prompts', (data: { roundNumber: number; prompts: { promptId: string; text: string }[] }) => {
            gameState.setPrompts(data.roundNumber, data.prompts);
            // Ensure we're on the answer screen (handles the case where
            // round:prompts arrives before or after round:prompting navigation).
            if (gameState.phase === 'prompting') {
                goto(`${base}/answer`);
            }
        });

        socket.on('round:generating', () => {
            gameState.setPhase('generating');
            gameState.setDeadline(null);
            goto(`${base}/wait`);
        });

        socket.on('round:revealing', () => {
            gameState.setPhase('revealing');
            gameState.setDeadline(null);
            goto(`${base}/react`);
        });

        socket.on('round:voting', (data: { deadline?: number }) => {
            gameState.setPhase('voting');
            gameState.setDeadline(data.deadline ?? null);
        });

        socket.on('round:scoring', () => {
            gameState.setPhase('scoring');
            gameState.setDeadline(null);
            gameState.clearRound();
        });

        socket.on('round:waiting', () => {
            gameState.setPhase('waiting');
            gameState.setDeadline(null);
            goto(`${base}/wait`);
        });

        socket.on('timer:tick', (data: { phase: string; remaining: number; deadline: number }) => {
            gameState.updateRemaining(data.remaining);
        });

        return () => {
            socket.off('connect');
            socket.off('disconnect');
            socket.off('player:joined');
            socket.off('round:prompting');
            socket.off('round:prompts');
            socket.off('round:generating');
            socket.off('round:revealing');
            socket.off('round:voting');
            socket.off('round:scoring');
            socket.off('round:waiting');
            socket.off('timer:tick');
        };
    });
</script>

<div class="shell">
    {#if browser}
        <div class="connection-indicator" class:connected={gameState.connected} aria-label={gameState.connected ? 'Connected' : 'Disconnected'}>
            <span class="dot"></span>
        </div>
    {/if}

    {@render children()}
</div>

<style>
    :global(*, *::before, *::after) {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }

    :global(html, body) {
        height: 100%;
        background-color: #1a1a2e;
        color: #e0e0e0;
        font-family: system-ui, -apple-system, sans-serif;
        -webkit-tap-highlight-color: transparent;
        overscroll-behavior: none;
    }

    .shell {
        min-height: 100dvh;
        display: flex;
        flex-direction: column;
        position: relative;
    }

    .connection-indicator {
        position: fixed;
        top: 0.5rem;
        right: 0.5rem;
        z-index: 1000;
    }

    .dot {
        display: block;
        width: 0.5rem;
        height: 0.5rem;
        border-radius: 50%;
        background-color: #ef4444;
        transition: background-color 0.3s ease;
    }

    .connection-indicator.connected .dot {
        background-color: #22c55e;
    }
</style>