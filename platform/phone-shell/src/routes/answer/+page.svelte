<script lang="ts">
    /**
     * M2.4 — Answer Screen
     *
     * Displays the player's assigned prompts and collects typed answers.
     * Emits `player:submit` when the player submits all answers.
     *
     * Submission is optimistic: the client navigates to /wait immediately.
     * M2.5 implements the server-side handler that persists and validates.
     */
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { base } from '$app/paths';
    import { browser } from '$app/environment';
    import { getSocket } from '$lib/socket.js';
    import { gameState } from '$lib/gameState.svelte.js';

    const MAX_ANSWER_LENGTH = 40;

    let submitting = $state(false);
    let submitted = $state(false);

    // ── Session guard ─────────────────────────────────────────────────────
    onMount(() => {
        if (!browser) return;
        if (!gameState.playerId) {
            const restored = gameState.restorePlayer();
            if (!restored) {
                goto(`${base}/join`);
                return;
            }
        }
        // If the round already advanced past PROMPTING, go to the correct screen.
        if (gameState.phase === 'generating') { goto(`${base}/wait`); return; }
        if (gameState.phase === 'revealing')  { goto(`${base}/react`); return; }
        if (gameState.phase === 'waiting' || gameState.phase === 'idle') {
            goto(`${base}/wait`);
        }
    });

    // ── Derived state ─────────────────────────────────────────────────────

    /** True when every prompt has a non-empty (non-whitespace) answer. */
    const allAnswered = $derived(
        gameState.prompts.length > 0 &&
        gameState.prompts.every(
            (p) => (gameState.answers[p.promptId] ?? '').trim().length > 0,
        )
    );

    /** Formatted countdown, e.g. "1:23" */
    const countdownDisplay = $derived((): string | null => {
        const r = gameState.phaseRemaining;
        if (r === null || r <= 0) return null;
        const m = Math.floor(r / 60);
        const s = r % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    });

    /** True when 30 seconds or fewer remain — timer turns urgent red. */
    const timerUrgent = $derived(
        gameState.phaseRemaining !== null && gameState.phaseRemaining <= 30
    );

    // ── Handlers ──────────────────────────────────────────────────────────

    function handleInput(promptId: string, event: Event) {
        const target = event.currentTarget as HTMLTextAreaElement;
        const value = target.value.slice(0, MAX_ANSWER_LENGTH);
        target.value = value;
        gameState.updateAnswer(promptId, value);
    }

    function handleSubmit() {
        if (submitting || submitted || !allAnswered) return;
        submitting = true;

        const answers = gameState.prompts.map((p) => ({
            promptId: p.promptId,
            text: (gameState.answers[p.promptId] ?? '').trim(),
        }));

        const socket = getSocket();
        socket.emit(
            'player:submit',
            { roomCode: gameState.roomCode, answers },
            (ack?: { ok: boolean; error?: string }) => {
                submitting = false;
                if (!ack || ack.ok) {
                    submitted = true;
                    goto(`${base}/wait`);
                } else {
                    gameState.setError(ack.error ?? 'Eroare la trimitere. Încearcă din nou.');
                }
            },
        );

        // Safety fallback: if no ack arrives within 3s, navigate anyway
        setTimeout(() => {
            if (!submitted) {
                submitted = true;
                goto(`${base}/wait`);
            }
        }, 3000);
    }
</script>

<main>
    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <header class="top-bar">
        <span class="round-label">Runda {gameState.currentRound || '—'}</span>

        {#if countdownDisplay()}
            <span class="timer" class:urgent={timerUrgent}>
                ⏱ {countdownDisplay()}
            </span>
        {/if}
    </header>

    <!-- ── Loading state (prompts not yet delivered) ──────────────────── -->
    {#if gameState.prompts.length === 0}
        <div class="loading-state">
            <p class="loading-text">Se pregătesc întrebările…</p>
        </div>

    {:else}
        <!-- ── Prompt list ─────────────────────────────────────────────── -->
        <div class="prompts-list">
            {#each gameState.prompts as prompt, i (prompt.promptId)}
                {@const answer = gameState.answers[prompt.promptId] ?? ''}
                {@const remaining = MAX_ANSWER_LENGTH - answer.length}
                {@const hasContent = answer.trim().length > 0}

                <section class="prompt-card" class:has-answer={hasContent}>
                    <p class="prompt-number">Întrebarea {i + 1}</p>
                    <p class="prompt-text">{prompt.text}</p>

                    <div class="input-wrapper">
                        <textarea
                            class="answer-input"
                            placeholder="Răspunsul tău…"
                            maxlength={MAX_ANSWER_LENGTH}
                            rows={2}
                            value={answer}
                            oninput={(e) => handleInput(prompt.promptId, e)}
                            disabled={submitting || submitted}
                            aria-label={`Răspuns la întrebarea ${i + 1}`}
                        ></textarea>
                        <span class="char-counter" class:near-limit={remaining <= 20}>
                            {remaining}
                        </span>
                    </div>
                </section>
            {/each}
        </div>

        <!-- ── Error message ───────────────────────────────────────────── -->
        {#if gameState.errorMessage}
            <div class="error-banner" role="alert">{gameState.errorMessage}</div>
        {/if}

        <!-- ── Submit button ───────────────────────────────────────────── -->
        <div class="submit-area">
            <button
                class="btn-submit"
                onclick={handleSubmit}
                disabled={!allAnswered || submitting || submitted}
            >
                {#if submitted}
                    ✓ Trimis!
                {:else if submitting}
                    Se trimite…
                {:else}
                    Trimite răspunsurile
                {/if}
            </button>

            {#if !allAnswered && gameState.prompts.length > 0}
                <p class="submit-hint">
                    Răspunde la toate întrebările pentru a trimite.
                </p>
            {/if}
        </div>
    {/if}
</main>

<style>
    main {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 0 0 1.5rem;
        overflow-y: auto;
    }

    .top-bar {
        position: sticky;
        top: 0;
        z-index: 10;
        background: #1a1a2e;
        border-bottom: 1px solid #2d3748;
        padding: 0.6rem 1.25rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
    }

    .round-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #555;
    }

    .timer {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e2b714;
        font-variant-numeric: tabular-nums;
        transition: color 0.3s ease;
    }

    .timer.urgent {
        color: #ef4444;
        animation: pulse 1s ease-in-out infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.6; }
    }

    .loading-state {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem;
    }

    .loading-text {
        color: #555;
        font-size: 0.95rem;
        animation: pulse 2s ease-in-out infinite;
    }

    .prompts-list {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 1rem;
        padding: 1.25rem 1.25rem 0;
    }

    .prompt-card {
        background: #16213e;
        border: 1px solid #2d3748;
        border-radius: 0.75rem;
        padding: 1rem;
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
        transition: border-color 0.2s ease;
    }

    .prompt-card.has-answer {
        border-color: #3d5a80;
    }

    .prompt-number {
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #555;
        margin: 0;
    }

    .prompt-text {
        font-size: 0.95rem;
        color: #e0e0e0;
        line-height: 1.5;
        margin: 0;
    }

    .input-wrapper {
        position: relative;
    }

    .answer-input {
        width: 100%;
        background: #0d1526;
        border: 1px solid #2d3748;
        border-radius: 0.5rem;
        color: #e0e0e0;
        font-size: 0.95rem;
        font-family: inherit;
        line-height: 1.5;
        padding: 0.65rem 0.75rem 1.5rem;
        resize: none;
        outline: none;
        transition: border-color 0.2s ease;
    }

    .answer-input:focus {
        border-color: #e2b714;
    }

    .answer-input:disabled {
        opacity: 0.5;
    }

    .char-counter {
        position: absolute;
        bottom: 0.4rem;
        right: 0.6rem;
        font-size: 0.65rem;
        color: #444;
        pointer-events: none;
        transition: color 0.2s ease;
    }

    .char-counter.near-limit {
        color: #ef4444;
    }

    .error-banner {
        margin: 0.75rem 1.25rem 0;
        background: #7f1d1d;
        color: #fca5a5;
        padding: 0.65rem 0.9rem;
        border-radius: 0.5rem;
        font-size: 0.85rem;
    }

    .submit-area {
        padding: 1rem 1.25rem 0;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .btn-submit {
        width: 100%;
        padding: 1rem;
        font-size: 1rem;
        font-weight: 700;
        border: none;
        border-radius: 0.625rem;
        background: #e2b714;
        color: #1a1a2e;
        cursor: pointer;
        transition: opacity 0.2s ease, transform 0.1s ease;
    }

    .btn-submit:disabled {
        opacity: 0.35;
        cursor: not-allowed;
    }

    .btn-submit:not(:disabled):active {
        transform: scale(0.97);
    }

    .submit-hint {
        text-align: center;
        color: #555;
        font-size: 0.78rem;
    }
</style>