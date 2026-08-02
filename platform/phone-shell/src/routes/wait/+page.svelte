<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { base } from '$app/paths';
    import { browser } from '$app/environment';
    import { gameState } from '$lib/gameState.svelte.js';

    // ── Session guard ──────────────────────────────────────────────────────
    // If the player has no identity (e.g. navigated here directly), send
    // them to the join screen.
    onMount(() => {
        if (!browser) return;
        if (!gameState.playerId) {
            const restored = gameState.restorePlayer();
            if (!restored) {
                goto(`${base}/join`);
            }
        }
    });

    // ── Derived display state ──────────────────────────────────────────────

    /** Human-readable phase label shown in the status bar. */
    const phaseLabel = $derived((): string => {
        switch (gameState.phase) {
            case 'waiting':    return 'Așteptăm să înceapă gazda…';
            case 'prompting':  return 'Runda a început! Pregătește-te…';
            case 'generating': return 'Povestea se generează…';
            case 'revealing':  return 'Urmărește ecranul principal!';
            case 'voting':     return 'Timp de votat!';
            case 'scoring':    return 'Se calculează scorurile…';
            case 'game_over':  return 'Joc terminat!';
            default:           return 'Se conectează…';
        }
    });

    /** True when the game is actively in a round (not in lobby). */
    const inRound = $derived(
        gameState.phase !== 'waiting' && gameState.phase !== 'idle'
    );

    /** Formatted countdown string, e.g. "1:23" */
    const countdownDisplay = $derived((): string | null => {
        const r = gameState.phaseRemaining;
        if (r === null || r <= 0) return null;
        const m = Math.floor(r / 60);
        const s = r % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    });

    /** Whether to pulse the status message (lobby idle state). */
    const shouldPulse = $derived(gameState.phase === 'waiting');
</script>

<main>
    <!-- ── Room code header ──────────────────────────────────────────────── -->
    <header class="room-header">
        <span class="label">Cod cameră</span>
        <span class="code">{gameState.roomCode || '----'}</span>
    </header>

    <!-- ── Phase status bar ─────────────────────────────────────────────── -->
    <div class="status-bar" class:pulse={shouldPulse} class:active={inRound}>
        <p class="status-text">{phaseLabel()}</p>

        {#if countdownDisplay()}
            <p class="countdown">{countdownDisplay()}</p>
        {/if}
    </div>

    <!-- ── Prompting-phase placeholder ──────────────────────────────────── -->
    <!-- The answer screen (M2.4) does not exist yet. During PROMPTING we    -->
    <!-- show an inline "get ready" card so the player isn't left confused.  -->
    {#if gameState.phase === 'prompting'}
        <div class="phase-card prompting-card">
            <span class="phase-icon">✏️</span>
            <p class="phase-title">Pregătește-te să răspunzi!</p>
            <p class="phase-hint">Ecranul de răspuns vine în curând…</p>
        </div>
    {/if}

    <!-- ── Generating phase card ─────────────────────────────────────────── -->
    {#if gameState.phase === 'generating'}
        <div class="phase-card generating-card">
            <span class="phase-icon">🎬</span>
            <p class="phase-title">AI-ul scrie povestea…</p>
            <p class="phase-hint">Urmărește ecranul principal pentru reveal!</p>
        </div>
    {/if}

    <!-- ── Player list ───────────────────────────────────────────────────── -->
    <section class="player-section">
        <h2 class="section-label">
            Jucători
            <span class="player-count">({gameState.players.length})</span>
        </h2>

        {#if gameState.players.length === 0}
            <p class="empty-hint">Nimeni nu s-a alăturat încă…</p>
        {:else}
            <ul class="player-list">
                {#each gameState.players as player (player.id)}
                    {@const isSelf = player.nickname === gameState.nickname}
                    <li class="player-item" class:self={isSelf}>
                        <span class="player-name">{player.nickname}</span>
                        {#if isSelf}
                            <span class="badge self-badge">Tu</span>
                        {/if}
                    </li>
                {/each}
            </ul>
        {/if}
    </section>

    <!-- ── Minimum player hint ───────────────────────────────────────────── -->
    {#if gameState.phase === 'waiting' && gameState.players.length < 2}
        <p class="min-players-hint">
            Mai este nevoie de cel puțin {2 - gameState.players.length} jucător{gameState.players.length === 1 ? '' : 'i'} pentru a începe.
        </p>
    {/if}
</main>

<style>
    main {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 1.25rem 1.5rem;
        gap: 1.25rem;
        overflow-y: auto;
    }

    /* ── Room header ──────────────────────────────────────────────────── */
    .room-header {
        text-align: center;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        padding-top: 0.5rem;
    }

    .label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #555;
    }

    .code {
        font-size: 2.25rem;
        font-weight: 900;
        letter-spacing: 0.3em;
        color: #e2b714;
        line-height: 1;
    }

    /* ── Status bar ───────────────────────────────────────────────────── */
    .status-bar {
        background: #16213e;
        border: 1px solid #2d3748;
        border-radius: 0.75rem;
        padding: 0.875rem 1rem;
        text-align: center;
        transition: border-color 0.3s ease;
    }

    .status-bar.active {
        border-color: #e2b714;
    }

    .status-text {
        color: #aaa;
        font-size: 0.9rem;
        margin: 0;
    }

    .countdown {
        margin: 0.35rem 0 0;
        font-size: 1.5rem;
        font-weight: 700;
        color: #e2b714;
        font-variant-numeric: tabular-nums;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.5; }
    }

    .pulse .status-text {
        animation: pulse 2.5s ease-in-out infinite;
    }

    /* ── Phase cards ──────────────────────────────────────────────────── */
    .phase-card {
        background: #16213e;
        border-radius: 0.75rem;
        padding: 1.25rem 1rem;
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.4rem;
        animation: slideIn 0.25s ease;
    }

    @keyframes slideIn {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    .prompting-card { border: 1px solid #e2b714; }
    .generating-card { border: 1px solid #6366f1; }

    .phase-icon { font-size: 2rem; line-height: 1; }

    .phase-title {
        font-size: 1rem;
        font-weight: 700;
        color: #e0e0e0;
        margin: 0;
    }

    .phase-hint {
        font-size: 0.8rem;
        color: #888;
        margin: 0;
    }

    /* ── Player list ──────────────────────────────────────────────────── */
    .player-section {
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
        flex: 1;
    }

    .section-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #555;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .player-count {
        color: #444;
    }

    .empty-hint {
        color: #444;
        font-size: 0.85rem;
        font-style: italic;
        padding: 0.5rem 0;
    }

    .player-list {
        list-style: none;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
    }

    .player-item {
        background: #16213e;
        border: 1px solid #2d3748;
        border-radius: 0.5rem;
        padding: 0.7rem 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        animation: slideIn 0.2s ease;
        transition: border-color 0.2s ease;
    }

    .player-item.self {
        border-color: #e2b714;
    }

    .player-name {
        font-size: 0.95rem;
        color: #e0e0e0;
    }

    .player-item.self .player-name {
        color: #e2b714;
        font-weight: 600;
    }

    /* ── Badges ───────────────────────────────────────────────────────── */
    .badge {
        font-size: 0.6rem;
        font-weight: 700;
        padding: 0.15rem 0.45rem;
        border-radius: 0.25rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        flex-shrink: 0;
    }

    .self-badge {
        background: #e2b714;
        color: #1a1a2e;
    }

    /* ── Minimum players hint ─────────────────────────────────────────── */
    .min-players-hint {
        text-align: center;
        color: #555;
        font-size: 0.78rem;
        padding-bottom: 0.5rem;
    }
</style>