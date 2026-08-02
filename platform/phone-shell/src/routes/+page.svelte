<script lang="ts">
    import { goto } from '$app/navigation';
    import { base } from '$app/paths';
    import { browser } from '$app/environment';
    import { onMount } from 'svelte';
    import { gameState } from '$lib/gameState.svelte.js';

    onMount(() => {
        if (!browser) return;
        const hasSession = gameState.restorePlayer();
        if (hasSession && gameState.playerId) {
            goto(`${base}/wait`);
        } else {
            goto(`${base}/join`);
        }
    });
</script>

<div style="display:flex;align-items:center;justify-content:center;height:100dvh;">
    <p style="color:#888;font-size:0.9rem;">Se încarcă…</p>
</div>