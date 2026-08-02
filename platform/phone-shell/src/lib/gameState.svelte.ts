/**
 * Shared game state store — Svelte 5 runes.
 *
 * Uses a class instance so state can be exported and mutated from modules.
 * Svelte 5 prohibits `export let x = $state()` when x is reassigned outside
 * the declaring module; a class instance sidesteps this constraint.
 */

export interface Player {
    id: string;
    nickname: string;
}

export type GamePhase =
    | 'idle'
    | 'joining'
    | 'waiting'
    | 'prompting'
    | 'generating'
    | 'revealing'
    | 'voting'
    | 'scoring'
    | 'game_over';

class GameState {
    playerId = $state<string | null>(null);
    nickname = $state<string>('');
    roomCode = $state<string>('');
    players = $state<Player[]>([]);
    phase = $state<GamePhase>('idle');
    errorMessage = $state<string | null>(null);
    connected = $state<boolean>(false);
    phaseDeadline = $state<number | null>(null);
    phaseRemaining = $state<number | null>(null);

    setConnected(value: boolean): void {
        this.connected = value;
    }

    setError(message: string | null): void {
        this.errorMessage = message;
    }

    clearError(): void {
        this.errorMessage = null;
    }

    setPlayers(list: Player[]): void {
        this.players = list;
    }

    setPhase(p: GamePhase): void {
        this.phase = p;
    }

    setDeadline(deadline: number | null): void {
        this.phaseDeadline = deadline;
        this.phaseRemaining = deadline !== null
            ? Math.max(0, deadline - Math.floor(Date.now() / 1000))
            : null;
    }

    updateRemaining(remaining: number): void {
        this.phaseRemaining = remaining;
    }

    /**
     * Initialises player identity and persists to sessionStorage.
     */
    initPlayer(id: string, nick: string, code: string): void {
        this.playerId = id;
        this.nickname = nick;
        this.roomCode = code;
        if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('agora_playerId', id);
            sessionStorage.setItem('agora_nickname', nick);
            sessionStorage.setItem('agora_roomCode', code);
        }
    }

    /**
     * Restores player identity from sessionStorage on page load.
     * Returns true if identity was found and restored.
     */
    restorePlayer(): boolean {
        if (typeof sessionStorage === 'undefined') return false;
        const id = sessionStorage.getItem('agora_playerId');
        const nick = sessionStorage.getItem('agora_nickname');
        const code = sessionStorage.getItem('agora_roomCode');
        if (id && nick && code) {
            this.playerId = id;
            this.nickname = nick;
            this.roomCode = code;
            return true;
        }
        return false;
    }

    /**
     * Clears all state and sessionStorage.
     */
    reset(): void {
        this.playerId = null;
        this.nickname = '';
        this.roomCode = '';
        this.players = [];
        this.phase = 'idle';
        this.errorMessage = null;
        this.phaseDeadline = null;
        this.phaseRemaining = null;
        if (typeof sessionStorage !== 'undefined') {
            sessionStorage.removeItem('agora_playerId');
            sessionStorage.removeItem('agora_nickname');
            sessionStorage.removeItem('agora_roomCode');
        }
    }
}

export const gameState = new GameState();