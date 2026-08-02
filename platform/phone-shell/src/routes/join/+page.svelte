<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { base } from '$app/paths';
    import { browser } from '$app/environment';
    import { getSocket } from '$lib/socket.js';
    import { gameState } from '$lib/gameState.svelte.js';

    let roomCodeInput = $state('');
    let nicknameInput = $state('');
    let submitting = $state(false);
    let attemptingRejoin = $state(false);

    onMount(() => {
        if (!browser) return;

        const socket = getSocket();

        const hasSession = gameState.restorePlayer();
        if (hasSession && gameState.playerId && gameState.roomCode) {
            attemptingRejoin = true;
            socket.emit(
                'player:rejoin',
                { playerId: gameState.playerId, roomCode: gameState.roomCode },
                (ack: { ok: boolean; nickname?: string; error?: string }) => {
                    attemptingRejoin = false;
                    if (ack.ok) {
                        gameState.setPhase('waiting');
                        goto(`${base}/wait`);
                    }
                    // If rejoin fails, show fresh join form (state already restored)
                },
            );
        }
    });

    function handleRoomCodeInput(e: Event) {
        const target = e.currentTarget as HTMLInputElement;
        roomCodeInput = target.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 4);
    }

    async function handleJoin() {
        if (submitting) return;
        gameState.clearError();

        const code = roomCodeInput.trim().toUpperCase();
        const nick = nicknameInput.trim();

        if (code.length !== 4) {
            gameState.setError('Codul camerei trebuie să aibă exact 4 caractere.');
            return;
        }
        if (nick.length < 1 || nick.length > 24) {
            gameState.setError('Porecla trebuie să aibă între 1 și 24 de caractere.');
            return;
        }

        submitting = true;

        const socket = getSocket();
        socket.emit(
            'player:join',
            { roomCode: code, nickname: nick },
            (ack: { ok: boolean; playerId?: string; error?: string }) => {
                submitting = false;
                if (ack.ok && ack.playerId) {
                    gameState.initPlayer(ack.playerId, nick, code);
                    gameState.setPhase('waiting');
                    goto(`${base}/wait`);
                } else {
                    gameState.setError(ack.error ?? 'A apărut o eroare. Încearcă din nou.');
                }
            },
        );
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === 'Enter') handleJoin();
    }
</script>

<main>
    {#if attemptingRejoin}
        <div class="loading">
            <p>Se reconectează…</p>
        </div>
    {:else}
        <div class="card">
            <h1 class="title">AGORA</h1>
            <p class="subtitle">Introdu codul camerei și porecla ta</p>

            {#if gameState.errorMessage}
                <div class="error" role="alert">{gameState.errorMessage}</div>
            {/if}

            <div class="field">
                <label for="room-code">Cod cameră</label>
                <input
                    id="room-code"
                    type="text"
                    inputmode="text"
                    autocomplete="off"
                    autocapitalize="characters"
                    spellcheck="false"
                    maxlength="4"
                    placeholder="ex. BDFK"
                    value={roomCodeInput}
                    oninput={handleRoomCodeInput}
                    onkeydown={handleKeydown}
                    disabled={submitting}
                />
            </div>

            <div class="field">
                <label for="nickname">Poreclă</label>
                <input
                    id="nickname"
                    type="text"
                    inputmode="text"
                    autocomplete="off"
                    autocapitalize="words"
                    maxlength="24"
                    placeholder="ex. Ionuț"
                    bind:value={nicknameInput}
                    onkeydown={handleKeydown}
                    disabled={submitting}
                />
            </div>

            <button
                class="btn-primary"
                onclick={handleJoin}
                disabled={submitting || !gameState.connected || roomCodeInput.length !== 4 || nicknameInput.trim().length === 0}
            >
                {submitting ? 'Se conectează…' : 'Intră în cameră'}
            </button>

            {#if !gameState.connected}
                <p class="hint">Se conectează la server…</p>
            {/if}
        </div>
    {/if}
</main>

<style>
    main {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1.5rem;
    }

    .loading {
        color: #888;
        font-size: 1rem;
    }

    .card {
        width: 100%;
        max-width: 22rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .title {
        font-size: 2.5rem;
        font-weight: 900;
        text-align: center;
        letter-spacing: 0.15em;
        color: #e2b714;
    }

    .subtitle {
        text-align: center;
        color: #888;
        font-size: 0.9rem;
    }

    .error {
        background: #7f1d1d;
        color: #fca5a5;
        padding: 0.75rem 1rem;
        border-radius: 0.5rem;
        font-size: 0.875rem;
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
    }

    label {
        font-size: 0.8rem;
        color: #aaa;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    input {
        background: #16213e;
        border: 1px solid #2d3748;
        border-radius: 0.5rem;
        color: #e0e0e0;
        font-size: 1.1rem;
        padding: 0.75rem 1rem;
        width: 100%;
        outline: none;
        transition: border-color 0.2s;
    }

    input:focus {
        border-color: #e2b714;
    }

    input:disabled {
        opacity: 0.5;
    }

    .btn-primary {
        background: #e2b714;
        border: none;
        border-radius: 0.5rem;
        color: #1a1a2e;
        cursor: pointer;
        font-size: 1rem;
        font-weight: 700;
        padding: 0.875rem 1rem;
        width: 100%;
        transition: opacity 0.2s;
        margin-top: 0.5rem;
    }

    .btn-primary:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .hint {
        text-align: center;
        color: #666;
        font-size: 0.8rem;
    }
</style>