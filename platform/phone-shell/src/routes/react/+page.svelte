<script lang="ts">
    import { browser } from '$app/environment';
    import { getSocket } from '$lib/socket.js';
    import { gameState } from '$lib/gameState.svelte.js';

    const EMOJIS = ['😂', '🔥', '💀', '👏', '😱', '🤣', '❤️', '👀'];

    let lastSent = $state<string | null>(null);
    let cooldown = $state(false);

    function sendReaction(emoji: string) {
        if (!browser || cooldown) return;

        const socket = getSocket();
        socket.emit('player:react', { roomCode: gameState.roomCode, emoji });

        lastSent = emoji;
        cooldown = true;

        setTimeout(() => { cooldown = false; }, 500);
    }
</script>

<main>
    <div class="header">
        <h1>Reacționează!</h1>
        <p class="subtitle">Apasă un emoji pentru a reacționa</p>
    </div>

    <div class="emoji-grid">
        {#each EMOJIS as emoji}
            <button
                class="emoji-btn"
                class:sent={lastSent === emoji}
                onclick={() => sendReaction(emoji)}
                disabled={cooldown}
                aria-label={emoji}
            >
                {emoji}
            </button>
        {/each}
    </div>

    {#if lastSent}
        <p class="sent-indicator">Ai trimis {lastSent}</p>
    {/if}

    {#if gameState.phase !== 'revealing'}
        <div class="phase-overlay">
            <p>
                {#if gameState.phase === 'voting'}
                    Timp de votat!
                {:else if gameState.phase === 'scoring'}
                    Scoruri…
                {:else}
                    Așteptăm…
                {/if}
            </p>
        </div>
    {/if}
</main>

<style>
    main {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 1.5rem;
        gap: 2rem;
        position: relative;
    }

    .header { text-align: center; }

    h1 {
        font-size: 1.75rem;
        font-weight: 900;
        color: #e2b714;
    }

    .subtitle {
        color: #888;
        font-size: 0.9rem;
        margin-top: 0.25rem;
    }

    .emoji-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.75rem;
        width: 100%;
        max-width: 22rem;
    }

    .emoji-btn {
        background: #16213e;
        border: 2px solid #2d3748;
        border-radius: 0.75rem;
        cursor: pointer;
        font-size: 2rem;
        line-height: 1;
        padding: 0.75rem;
        transition: transform 0.1s ease, border-color 0.15s ease;
        aspect-ratio: 1;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .emoji-btn:active { transform: scale(0.9); }
    .emoji-btn.sent { border-color: #e2b714; }
    .emoji-btn:disabled { opacity: 0.6; cursor: not-allowed; }

    .sent-indicator {
        color: #888;
        font-size: 0.85rem;
        animation: fadeIn 0.2s ease;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .phase-overlay {
        position: absolute;
        inset: 0;
        background: rgba(26, 26, 46, 0.92);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .phase-overlay p {
        font-size: 1.5rem;
        font-weight: 700;
        color: #e2b714;
    }
</style>