<script lang="ts">
    import { gameState } from '$lib/gameState.svelte.js';

    const phaseMessages: Record<string, string> = {
        waiting: 'Așteptăm să înceapă gazda…',
        generating: 'Povestea se generează…',
        scoring: 'Se calculează scorurile…',
        game_over: 'Joc terminat!',
    };

    let statusMessage = $derived(phaseMessages[gameState.phase] ?? 'Așteptăm…');
</script>

<main>
    <div class="room-header">
        <span class="label">Cod cameră</span>
        <span class="code">{gameState.roomCode}</span>
    </div>

    <div class="status">
        <p>{statusMessage}</p>
    </div>

    <div class="player-list">
        <h2>Jucători ({gameState.players.length})</h2>
        <ul>
            {#each gameState.players as player (player.id)}
                <li class:self={player.nickname === gameState.nickname}>
                    {player.nickname}
                    {#if player.nickname === gameState.nickname}
                        <span class="you-badge">Tu</span>
                    {/if}
                </li>
            {/each}
        </ul>
    </div>
</main>

<style>
    main {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 1.5rem;
        gap: 1.5rem;
    }

    .room-header {
        text-align: center;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }

    .label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #666;
    }

    .code {
        font-size: 2rem;
        font-weight: 900;
        letter-spacing: 0.25em;
        color: #e2b714;
    }

    .status {
        text-align: center;
        color: #888;
        font-size: 0.9rem;
        animation: pulse 2s ease-in-out infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }

    .player-list h2 {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #666;
        margin-bottom: 0.75rem;
    }

    ul {
        list-style: none;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    li {
        background: #16213e;
        border-radius: 0.5rem;
        padding: 0.75rem 1rem;
        font-size: 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border: 1px solid transparent;
    }

    li.self {
        border-color: #e2b714;
        color: #e2b714;
    }

    .you-badge {
        background: #e2b714;
        color: #1a1a2e;
        font-size: 0.65rem;
        font-weight: 700;
        padding: 0.15rem 0.4rem;
        border-radius: 0.25rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
</style>