# AGORA Development Tasks

> Source of truth: CRONICĂ GDD v0.2
> Platform codename: **AGORA**
> Game #1 codename: **CRONICĂ**
> Stack: Node.js 22 LTS · Fastify · Socket.IO · Svelte 5 · Tauri 2 · Python 3.12 · Ollama · ComfyUI · ElevenLabs (Piper fallback)

---

## M0 — Planning (Completed)

- [x] M0.1 Game Design Document
  **Objective:** Produce and approve the full GDD covering platform vision, game design, AI pipeline, architecture, and milestones.
  **Dependencies:** None.
  **Completion criteria:** GDD v0.2 approved by project owner. All 7 items in the approval checklist confirmed.

---

## M1 — Platform Skeleton

> Goal: A working lobby. Host creates a room. Players join on their phones via QR code. The round state machine advances through all phases. No AI. No game content. Pure infrastructure.

- [x] M1.1 Repository Initialisation
  **Objective:** Create the monorepo root with Git, root-level tooling config, and the exact folder structure defined in the GDD.
  **Dependencies:** M0.1.
  **Completion criteria:** Git repo initialised; folder structure matches GDD Section 8.2 exactly; `.gitignore` excludes `node_modules`, `output/`, `.env` files; `README.md` contains project name, codenames, and stack; `roadmap.md` lists all milestones M1–M11.

- [x] M1.2 Platform Server Bootstrap
  **Objective:** Stand up a Fastify server on Node.js 22 LTS with Socket.IO attached and a health endpoint.
  **Dependencies:** M1.1.
  **Completion criteria:** `GET /health` returns `{ status: "ok" }` with HTTP 200; Socket.IO handshake succeeds from a browser; server reads host and port from `.env`; TypeScript compiles without errors; `npm run dev` starts with hot reload.

- [x] M1.3 SQLite Database Layer
  **Objective:** Create the SQLite schema for all platform tables and a typed query wrapper.
  **Dependencies:** M1.2.
  **Completion criteria:** Tables exist: `rooms`, `players`, `rounds`, `round_answers`, `votes`; schema matches data needs described in GDD Section 8.3; migrations run cleanly on a fresh database; all queries are typed; no raw SQL strings outside the db module.

- [x] M1.4 Room Management
  **Objective:** Implement room creation, 4-character room code generation, and QR code serving.
  **Dependencies:** M1.3.
  **Completion criteria:** `POST /rooms` creates a room and returns a room code; room code is unique and human-readable (4 uppercase letters); `GET /rooms/:code/qr` returns a QR code image pointing to the phone join URL; room state is persisted in SQLite; duplicate room codes are handled.

- [x] M1.5 Player Join Flow — Server Side
  **Objective:** Implement the Socket.IO events that allow a player to join a room by code, register a nickname, and appear in the room's player list.
  **Dependencies:** M1.4.
  **Completion criteria:** `player:join` event accepts `{ roomCode, nickname }`; validates room exists and is in WAITING state; stores player in SQLite; emits `player:joined` to all room members with updated player list; rejects duplicate nicknames in the same room; handles join attempt for non-existent room gracefully.

- [x] M1.6 Connection Resilience
  **Objective:** Implement player reconnection so a phone that drops and rejoins does not lose its place in the game.
  **Dependencies:** M1.5.
  **Completion criteria:** Player is assigned a persistent `playerId` (stored in phone's `sessionStorage`); on reconnect, `player:rejoin` event restores the player's room and state; disconnected player is marked inactive but not deleted; host is notified of disconnection and reconnection; game does not crash if a player disconnects mid-round.

- [x] M1.7 Round State Machine
  **Objective:** Implement the server-side state machine that sequences all round phases as defined in GDD Section 9.1.
  **Dependencies:** M1.5.
  **Completion criteria:** States implemented: `WAITING → PROMPTING → GENERATING → REVEALING → VOTING → SCORING → WAITING`; each transition emits the correct Socket.IO event per GDD Section 9.2; invalid transitions are rejected; current state is persisted in SQLite; host can trigger `round:start` from WAITING state only.

- [x] M1.8 Phase Timers
  **Objective:** Implement server-side countdown timers for each timed phase, with synchronised tick events sent to all clients.
  **Dependencies:** M1.7.
  **Completion criteria:** PROMPTING phase has a configurable timer (default 90s); VOTING phase has a configurable timer (default 30s); `timer:tick` event emitted every second to all room members; timer expires and advances state automatically if not all players have submitted; timer can be configured per phase in the game module config; timers survive server restart via persisted deadline timestamps.

- [x] M1.9 Phone Shell — Svelte 5 Project Setup
  **Objective:** Initialise the Svelte 5 / SvelteKit project for the phone client shell with routing, Socket.IO client, and shared state store.
  **Dependencies:** M1.2.
  **Completion criteria:** SvelteKit project created under `platform/phone-shell`; Svelte 5 with runes; Socket.IO client connected to the platform server; shared game state store using Svelte 5 runes; routes exist for `/join`, `/wait`, `/react`; project builds to static output (`adapter-static`); build output is served by the Fastify server at `/phone`.

- [x] M1.10 Phone Shell — Join Screen
  **Objective:** Build the player-facing join screen: room code entry, nickname input, and join confirmation.
  **Dependencies:** M1.9, M1.5.
  **Completion criteria:** Player can enter a 4-character room code and a nickname; form validates both fields before submission; on success, player is taken to the wait screen; on failure (bad code, duplicate name), a clear error is shown; screen works on mobile browsers (Android 10+, iOS 14+); no install required; loads in under 2 seconds on LAN.

- [x] M1.11 Phone Shell — Wait Screen
  **Objective:** Build the waiting room screen that shows connected players and a "waiting for host" message.
  **Dependencies:** M1.10.
  **Completion criteria:** Displays live list of all players currently in the room; updates in real time as new players join; shows player's own nickname highlighted; displays room code for others to join; transitions automatically when host starts the round; connection status indicator visible at all times.

- [x] M1.12 Host Dashboard — Minimal Web UI
  **Objective:** Build a minimal host control page served at `/host` that shows the room QR code, connected players, and a start round button.
  **Dependencies:** M1.11, M1.7.
  **Completion criteria:** Displays QR code and room code large enough to scan from 3m; shows live player list with connection status; "Start Round" button is enabled only when 2+ players are connected; button advances state machine to PROMPTING; host page is separate from the phone shell and intended for the large screen; no framework required — plain HTML/JS is acceptable.

- [x] M1.13 Game Module Interface
  **Objective:** Define the TypeScript `AgoraGameModule` interface that all games must implement to run on the AGORA platform.
  **Dependencies:** M1.7.
  **Completion criteria:** Interface defined in `platform/server/src/interfaces/`; includes all fields from GDD Section 1.3: `id`, `name`, `minPlayers`, `maxPlayers`, `phases`, `promptPack`, `pipeline`, `presenterUI`, `phoneUI`; supporting types defined: `PhaseDefinition`, `PromptPack`, `AIPipeline`, `PresenterModule`, `PhoneModule`; interface is exported and importable by game modules; no concrete implementation in the platform layer.

- [x] M1.14 Integration Test — Full Lobby Simulation
  **Objective:** Write an automated integration test that simulates 4 players joining a room, the host starting a round, and the state machine advancing through all phases.
  **Dependencies:** M1.13, M1.8, M1.11.
  **Completion criteria:** Test uses Socket.IO test clients (no browser); 4 clients join the same room with unique nicknames; host triggers round start; state machine advances through WAITING → PROMPTING → GENERATING → REVEALING → VOTING → SCORING; all clients receive the correct events at each transition; test passes with `npm test`; test runs in under 10 seconds.

---

## M2 — Prompt & Answer Loop

> Goal: The PROMPTING phase works end to end. Players receive prompts on their phones, type answers, and submit before the timer expires. The server collects and validates all answers.

- [x] M2.1 Prompt Pack Format
  **Objective:** Define the JSON schema for ingredient question packs and create the first CRONICĂ pack with 70 questions across 7 semantic categories (CONCRET, ABSTRACT, ACTIUNE, LOC, NUMAR, PROPRIU, ATRIBUT).
  **Dependencies:** M1.13.
  **Completion criteria:** JSON schema defined; each question has: `id`, `text` (Romanian), `category` (semantic domain), `safeMode` boolean, `minPlayers`; 70 questions covering all 7 categories with minimum 10 per category; pack validates against schema; questions collect raw ingredients with no narrative hints.

- [x] M2.2 Prompt Assignment Engine
  **Objective:** Implement the server-side logic that selects and assigns prompts to players at the start of each round.
  **Dependencies:** M2.1, M1.7.
  **Completion criteria:** Each player receives 2–3 prompts; no two players receive the exact same prompt in the same round; at least one prompt per round references another named player; prompt categories are varied across rounds (no two consecutive rounds dominated by same category); Safe Mode filters out adult prompts when enabled; assignment is stored in SQLite per round.

- [x] M2.3 Prompt Delivery — Server to Phone
  **Objective:** Implement the Socket.IO event that delivers each player's assigned prompts to their phone at the start of the PROMPTING phase.
  **Dependencies:** M2.2, M1.8.
  **Completion criteria:** `round:start` event delivers `{ roundNumber, prompts[] }` to each player with their specific prompts only; prompts include `id` and `text`; event fires immediately when state transitions to PROMPTING; player cannot receive another player's prompts; timer starts server-side at the same moment.

- [x] M2.4 Phone — Answer Screen
  **Objective:** Build the Svelte 5 phone screen that displays prompts and collects typed answers from the player.
  **Dependencies:** M2.3, M1.9.
  **Completion criteria:** Displays each prompt clearly with its text; one text input per prompt; character limit enforced per answer (max 120 characters); live character counter shown; submit button disabled until all prompts have a non-empty answer; countdown timer visible and synced to server; screen transitions to wait screen on submit; works on mobile keyboard without layout breaking.

- [x] M2.5 Answer Submission — Server Side
  **Objective:** Implement the `player:submit` Socket.IO event handler that validates, stores, and acknowledges player answer submissions.
  **Dependencies:** M2.4, M1.3.
  **Completion criteria:** `player:submit` accepts `{ answers: [{ promptId, text }] }`; validates all assigned prompt IDs are answered; stores answers in `round_answers` table; emits acknowledgement to submitting player; emits `round:player_submitted` to host (not to other players); triggers state advance to GENERATING when all players have submitted; late submissions after timer expiry are rejected.

- [x] M2.6 Partial Submission Handling
  **Objective:** Handle the case where the timer expires before all players have submitted, collecting whatever answers exist and advancing the round.
  **Dependencies:** M2.5.
  **Completion criteria:** When PROMPTING timer expires, server collects all answers received so far; players who did not submit receive empty answers (recorded as such in SQLite); round advances to GENERATING regardless; host sees which players submitted and which did not; a player with zero answers still participates in the round (LLM will receive fewer inputs).

---

## M3 — Creative Director

> Goal: The Creative Director system is implemented. Given a set of player answers, it produces a complete, structured CreativeBrief that every downstream AI component will consume.

- [x] M3.1 CreativeBrief Data Model
  **Objective:** Define all Python dataclasses and TypeScript types for the `CreativeBrief` and all supporting structures from GDD Section 6.2.
  **Dependencies:** M1.13.
  **Completion criteria:** Python dataclasses defined for: `CreativeBrief`, `StoryArc`, `Archetype`, `Twist`, `CameraRule`, `NarratorPersona`, `SFXNote`, `LayoutStrategy`; all enums defined: `PresentationFormat`, `RevealPacing`; TypeScript equivalents defined in platform interfaces; Python dataclasses serialise to/from JSON cleanly; no fields from GDD Section 6.2 are missing.

- [x] M3.2 Genre Registry
  **Objective:** Implement all 7 genre definitions from GDD Section 6.3 as structured data in the genre registry.
  **Dependencies:** M3.1.
  **Completion criteria:** All 7 genres implemented: Telenovelă Românească, Film de Acțiune B, Basm Românesc Absurd, Scandal de Bloc, Documentar Fals, Horror Mioritic, Știri Rupte din Realitate; each genre encodes all attributes from the GDD: story structure, archetypes, comedy level range, visual style, camera language, narrator personality, music direction, colour palette; genres are stored as structured data, not strings; registry is easily extensible for future genres.

- [x] M3.3 Presentation Format Registry
  **Objective:** Implement all 7 presentation formats from GDD Section 6.4 as structured data with their compatible genres.
  **Dependencies:** M3.2.
  **Completion criteria:** All 7 formats implemented: Western Comic, Fake News Broadcast, Police Report, Documentary Film, Folk Tale Illustration, Instagram Story Sequence, Interpol Dossier; each format defines its panel layout strategy; genre–format compatibility matrix enforced (e.g. Folk Tale only with Basm); format data is used downstream by both the LLM prompt builder and the ComfyUI style injector.

- [x] M3.4 Genre Selection Logic
  **Objective:** Implement the weighted random genre selection algorithm that avoids recently played genres.
  **Dependencies:** M3.2, M1.3.
  **Completion criteria:** Genre is selected with weighted randomness; genres played in the last 2 rounds have reduced weight; all 7 genres will appear within any 7-round session; selection is seeded per round (reproducible for debugging); selected genre is persisted in SQLite with the round record; host can see selected genre in debug mode.

- [x] M3.5 Archetype Assignment
  **Objective:** Implement the logic that maps each player's submitted ingredient answers to a narrative archetype within the selected genre, and assigns a structural role to each ingredient.
  **Dependencies:** M3.4, M2.5.
  **Completion criteria:** Each player is assigned exactly one archetype from the selected genre's archetype list; each ingredient answer is assigned an `IngredientRole` (CHARACTER | LOCATION | OBJECT | CONCEPT | NAME | QUANTITY | ACTION | ATMOSPHERE) by the Creative Director — ingredients adapt to the story, not vice versa; no two players share the same archetype; assignments are included in the `CreativeBrief`; the same ingredient can fulfill different roles across different playthroughs.

- [x] M3.6 Creative Brief Generator
  **Objective:** Implement the `CreativeDirector` class that combines genre, format, archetypes, and player data into a complete, validated `CreativeBrief`.
  **Dependencies:** M3.3, M3.5.
  **Completion criteria:** `CreativeDirector.generate(playerAnswers, roundHistory)` returns a fully populated `CreativeBrief`; all required fields are populated; panel count is determined by the selected genre (4–8); punchline panel is assigned; comedy level is randomised within the genre's allowed range; brief serialises to `brief.json` in the output directory; brief can be logged in human-readable form for debugging.

- [x] M3.7 Creative Director Unit Tests
  **Objective:** Write unit tests for the Creative Director covering genre selection distribution, archetype assignment, and brief completeness.
  **Dependencies:** M3.6.
  **Completion criteria:** Test: genre distribution over 100 calls produces all 7 genres with no genre dominating (>30%); test: archetype assignment produces no duplicates; test: brief generator always produces a fully populated brief with no null required fields; test: genre avoidance works across simulated round history; all tests pass with `pytest`.

---

## M4 — Story Generation

> Goal: The LLM integration is complete. Given a CreativeBrief and player answers, Ollama + Llama 3.1 8B produces a structured Romanian story with English image prompts.

- [x] M4.1 AI Pipeline Orchestrator Shell
  **Objective:** Create the Python pipeline orchestrator entry point that accepts input from the Node.js server via HTTP and coordinates all pipeline steps sequentially.
  **Dependencies:** M3.6.
  **Completion criteria:** `orchestrator.py` exposes `POST /pipeline/run` accepting `{ roundId, playerAnswers, outputDir }`; pipeline steps execute sequentially; VRAM is explicitly cleared between LLM and image generation steps; `POST /pipeline/complete` is called on the Node.js server when all assets are ready; pipeline errors are caught, logged, and reported back to the server without crashing; orchestrator runs as a separate process from the Node.js server.

- [x] M4.2 StoryLLMProvider Interface
  **Objective:** Define the abstract `StoryLLMProvider` Python interface that all LLM implementations must satisfy.
  **Dependencies:** M4.1.
  **Completion criteria:** Abstract base class defined with method: `generate_story(brief: CreativeBrief, answers: PlayerAnswers) -> Story`; `Story` dataclass defined with fields: `title`, `panels: PanelDescription[]`, `narratorScript: str[]`, `imagePrompts: str[]` (English); interface is importable from the providers module; no Ollama-specific code in the interface definition.

- [x] M4.3 Story Dataclass & Output Schema
  **Objective:** Define the complete `Story` output schema including all fields the LLM must populate, and the JSON structure written to `story.json`.
  **Dependencies:** M4.2.
  **Completion criteria:** `Story` dataclass includes: `title` (RO), `panels[]` each with `panelIndex`, `descriptionRO`, `dialogueRO`, `imagePromptEN`, `narratorLineRO`, `charactersinPanel[]`; schema validates that all player names appear somewhere in the story; schema validates that image prompts are in English; `story.json` schema documented; validation raises descriptive errors on missing fields.

- [x] M4.4 Ollama LLM Implementation
  **Objective:** Implement `OllamaStoryLLM`, the concrete `StoryLLMProvider` that calls Ollama with Llama 3.1 8B to generate a structured story.
  **Dependencies:** M4.2, M4.3.
  **Completion criteria:** Calls Ollama REST API at `localhost:11434`; uses Llama 3.1 8B model; sends system prompt encoding the CreativeBrief and anti-template instructions; requests structured JSON output conforming to the Story schema; retries once on malformed JSON before raising; logs token usage; VRAM usage stays under 6GB during LLM step; generation completes in under 30 seconds.

- [x] M4.5 Story System Prompt Engineering
  **Objective:** Write and validate the LLM system prompt that produces original stories using player ingredients as narrative fuel, with each ingredient assigned a structural role by the Creative Director.
  **Dependencies:** M4.4.
  **Completion criteria:** System prompt receives each ingredient paired with its assigned role (e.g. "crocodil = numele organizației secrete"); prompt instructs LLM to integrate ingredients organically — never decoratively; story must be impossible to reverse-engineer from ingredients alone; prompt encodes the full CreativeBrief (genre, archetypes, structure, tone); tested across all 7 genres; produces structurally different stories from identical ingredient sets across multiple runs.

- [x] M4.6 Post-Generation Validation
  **Objective:** Implement a validation layer that checks the generated story satisfies minimum quality requirements before passing it downstream.
  **Dependencies:** M4.5.
  **Completion criteria:** Validates: all player names appear in the story; all image prompts are non-empty English strings; panel count matches the brief's specified panel count; narrator script has one line per panel; no panel description is shorter than 20 words; on validation failure, one retry is attempted with the error included in the prompt; after two failures, a fallback minimal story is generated rather than crashing the round.

- [X] M4.7 Story Generation Integration Test
  **Objective:** Write an integration test that calls the full story generation pipeline with a sample CreativeBrief and real player answers and validates the output.
  **Dependencies:** M4.6.
  **Completion criteria:** Test calls `OllamaStoryLLM.generate_story()` with a fixture CreativeBrief and 4-player answer set; validates all Story schema fields are populated; validates player names appear in output; validates image prompts are English; test runs against a live Ollama instance; documented setup instructions explain how to install Ollama and pull Llama 3.1 8B; test passes consistently across 3 runs.

---

## M5 — Image Pipeline

> Goal: ComfyUI + FLUX.1 schnell is integrated. Given a Story's image prompts and the CreativeBrief's visual style, 4–8 comic panels are generated and saved as PNG files.

- [ ] M5.1 ImageGeneratorProvider Interface
  **Objective:** Define the abstract `ImageGeneratorProvider` Python interface that all image generation implementations must satisfy.
  **Dependencies:** M4.1.
  **Completion criteria:** Abstract base class with method: `generate_panel(prompt: ImagePrompt, style: VisualStyle, characterDescriptions: CharacterSheet[]) -> PanelImage`; `ImagePrompt` dataclass defined; `VisualStyle` dataclass defined (maps from CreativeBrief visual fields); `PanelImage` dataclass wraps the output file path and metadata; no ComfyUI-specific code in the interface.

- [ ] M5.2 Character Description System
  **Objective:** Implement the character description generator that creates consistent visual descriptions for each player-character at the start of image generation.
  **Dependencies:** M5.1, M3.5.
  **Completion criteria:** Each player-character gets a `CharacterSheet`: name, hair colour/style, clothing dominant colour (unique per character), one distinguishing feature; colour assignments are unique within a round (no two characters share a dominant clothing colour); character sheets are derived from player names and archetype (not randomly); sheets are written to `brief.json` alongside the CreativeBrief; same character sheet is injected into every panel prompt featuring that character.

- [ ] M5.3 ComfyUI Workflow Integration
  **Objective:** Implement `FluxImageGenerator`, the concrete `ImageGeneratorProvider` that submits generation jobs to ComfyUI's API using FLUX.1 schnell.
  **Dependencies:** M5.1, M5.2.
  **Completion criteria:** Calls ComfyUI REST API at `localhost:8188`; uses FLUX.1 schnell model; workflow accepts positive prompt, negative prompt, style tokens, resolution (1024×1024 default); polls for job completion; saves output PNG to the round output directory; VRAM usage stays under 12GB; generation completes in under 20 seconds per panel on RTX 4070; VRAM is cleared after all panels are generated.

- [ ] M5.4 Style Token Injection
  **Objective:** Implement the system that translates each genre's visual style and camera language rules into ComfyUI prompt tokens for each panel.
  **Dependencies:** M5.3, M3.2.
  **Completion criteria:** Each genre's visual style maps to a set of positive style tokens (e.g. "oversaturated, warm tones, telenovela aesthetic, dramatic close-up"); each genre has a negative token list (e.g. horror genre excludes "bright, cheerful"); camera language per panel is translated to composition tokens (e.g. "panel 1: wide establishing shot, low angle" → `wide shot, low angle, establishing`); tokens are constructed deterministically from the CreativeBrief; no hard-coded prompt strings outside the style injection module.

- [ ] M5.5 Panel Composition Orchestrator
  **Objective:** Implement the loop that generates all panels sequentially, injecting per-panel camera rules, character descriptions, and dialogue cues.
  **Dependencies:** M5.4.
  **Completion criteria:** Generates panels in order (panel 1 first, panel N last); each panel prompt combines: base style tokens + camera rule for that panel + character descriptions for characters in that panel + scene description from Story; dialogue/speech bubble text is passed as a caption note (not embedded in the image); panels are saved as `panel_1.png` … `panel_N.png`; total generation time for 6 panels logged; partial failure (one panel fails) retries that panel once before writing a placeholder.

- [ ] M5.6 Image Pipeline Integration Test
  **Objective:** Write an integration test that runs the full image pipeline from a Story fixture through to PNG files on disk.
  **Dependencies:** M5.5.
  **Completion criteria:** Test uses a fixture Story and CreativeBrief; calls `FluxImageGenerator` for all panels; validates output files exist and are valid PNGs; validates file sizes are non-trivial (>50KB each); validates panel count matches brief; test is documented with ComfyUI and FLUX.1 schnell setup instructions; test passes on RTX 4070 in under 3 minutes total.

---

## M6 — TTS Pipeline

> Goal: ElevenLabs TTS (with Piper fallback) is integrated. Each panel's narrator line is synthesised into a WAV file matching the narrator persona from the CreativeBrief.

- [ ] M6.1 TTSProvider Interface
  **Objective:** Define the abstract `TTSProvider` Python interface that both ElevenLabs and Piper must implement.
  **Dependencies:** M4.1.
  **Completion criteria:** Abstract base class with method: `synthesise(text: str, persona: NarratorPersona) -> AudioFile`; `NarratorPersona` dataclass includes: `voiceId` (maps to ElevenLabs voice ID or Piper model), `speed`, `stability`, `style` (maps to ElevenLabs style exaggeration); `AudioFile` wraps output WAV path and duration in seconds; no provider-specific code in the interface.

- [ ] M6.2 ElevenLabs TTS Implementation
  **Objective:** Implement `ElevenLabsTTS`, the default `TTSProvider`, using the ElevenLabs API with a Romanian voice.
  **Dependencies:** M6.1.
  **Completion criteria:** Calls ElevenLabs REST API; API key loaded from `.env`; uses a Romanian-capable voice (voice ID configurable); narrator persona maps to ElevenLabs `stability`, `similarity_boost`, and `style` parameters; output saved as `narration_N.wav`; handles API errors gracefully; automatically falls back to `PiperTTS` if API key is missing or API returns an error; logs which provider was used.

- [ ] M6.3 Piper TTS Fallback Implementation
  **Objective:** Implement `PiperTTS`, the offline fallback `TTSProvider`, using the best available Romanian Piper voice model.
  **Dependencies:** M6.1.
  **Completion criteria:** Calls Piper binary via subprocess; uses the best available Romanian voice model (evaluated and documented in setup instructions); produces WAV output at 22050 Hz; persona mapping is best-effort (speed only — Piper does not support style parameters); model file is bundled with the project or downloaded by setup script; works with no internet connection; output format is identical to ElevenLabs output (WAV, same sample rate).

- [ ] M6.4 Narrator Persona Mapping
  **Objective:** Implement the mapping from each genre's narrator personality definition (GDD Section 6.3) to concrete ElevenLabs and Piper voice parameters.
  **Dependencies:** M6.2, M6.3.
  **Completion criteria:** All 7 genres have a defined narrator persona; each persona specifies: `voiceId`, `stability` (0–1), `similarityBoost` (0–1), `styleExaggeration` (0–1), `speakingRate`; persona parameters produce audibly different narration across genres (e.g. telenovelă narrator sounds different from horror narrator); persona map is stored as data, not hard-coded in the TTS implementation; documented with example output descriptions.

- [ ] M6.5 TTS Pipeline Integration Test
  **Objective:** Write an integration test that synthesises all narrator lines from a Story fixture and validates the audio output files.
  **Dependencies:** M6.4.
  **Completion criteria:** Test synthesises narration for a 6-panel story using ElevenLabs (requires API key in environment); validates WAV files exist for all 6 panels; validates each WAV duration is between 2s and 15s; test also runs in offline mode using Piper fallback; both modes produce valid WAV files; setup instructions document ElevenLabs API key requirement.

---

## M7 — Presenter

> Goal: The Tauri 2 presenter window displays the comic. Panels appear one by one with cinematic animation, narration audio plays in sync, and the experience feels like a short film.

- [ ] M7.1 Tauri 2 Project Setup
  **Objective:** Initialise the Tauri 2 project for the CRONICĂ presenter with a Rust backend and an HTML/CSS/JS frontend.
  **Dependencies:** M1.1.
  **Completion criteria:** Tauri 2 project created under `games/cronica/presenter`; builds and opens a native window on Windows; window is full-screen or maximised by default; frontend served from local files (not a dev server); Rust backend can receive IPC messages from the Node.js server; build script documented in `scripts/`; `cargo build` and `npm run tauri build` succeed without errors.

- [ ] M7.2 Asset Loading System
  **Objective:** Implement the Tauri Rust backend command that loads round assets (panel PNGs and narration WAVs) from the output directory and exposes them to the frontend.
  **Dependencies:** M7.1, M5.5, M6.5.
  **Completion criteria:** Tauri command `load_round_assets(roundId)` reads the output directory and returns a manifest of panel images and narration audio files; manifest includes file paths, panel count, and brief metadata; frontend can fetch panel images and audio via Tauri's asset protocol; invalid or incomplete asset directories return a structured error; command is called automatically when the Node.js server signals `pipeline_complete`.

- [ ] M7.3 Panel Reveal Animation
  **Objective:** Build the panel-by-panel cinematic reveal animation in the presenter frontend.
  **Dependencies:** M7.2.
  **Completion criteria:** Panels appear one at a time with a cinematic entrance animation (not a simple fade — at minimum a Ken Burns or slide-in effect appropriate to the genre); transition between panels is smooth (no flash or blank frame); panel display time is driven by narration audio duration (panel stays visible while its narration plays); panel layout adapts to panel count (4-panel vs 6-panel layouts differ); animations use CSS transitions/keyframes only — no JavaScript animation libraries.

- [ ] M7.4 Narration Audio Sync
  **Objective:** Implement audio playback that plays each panel's narration WAV in sync with its panel reveal.
  **Dependencies:** M7.3.
  **Completion criteria:** Each panel's narration WAV begins playing as soon as that panel is revealed; next panel does not advance until current narration has finished; audio plays without gaps between panels (pre-load next audio file); volume is controlled by host keyboard shortcut; playback survives a panel with a missing WAV file (silent fallback); total reveal sequence plays from start to finish automatically without host interaction.

- [ ] M7.5 Genre Visual Theming
  **Objective:** Implement per-genre visual theming in the presenter so the UI colour scheme, font style, and panel borders reflect the active genre.
  **Dependencies:** M7.3, M3.2.
  **Completion criteria:** Presenter reads the genre from `brief.json`; each of the 7 genres applies a distinct CSS theme: background colour, panel border style, title card typography, transition style; themes are driven by CSS custom properties loaded at runtime; no genre is visually identical to another; theme is applied before the first panel is shown.

- [ ] M7.6 Title Card & Genre Reveal
  **Objective:** Implement the cinematic title card sequence that reveals the story title and genre before the first panel appears.
  **Dependencies:** M7.5.
  **Completion criteria:** Before panel 1, a full-screen title card shows: genre name, story title (from `story.json`), a brief atmospheric pause; title card duration is 3–5 seconds; title card uses the genre's visual theme; transition from title card to panel 1 is animated; title card appearance is different for each genre (e.g. telenovelă uses different typography than documentar fals).

- [ ] M7.7 Reaction Overlay
  **Objective:** Implement the real-time emoji reaction overlay that displays reactions from players' phones during the reveal.
  **Dependencies:** M7.6, M1.5.
  **Completion criteria:** Players can send emoji reactions from their phone during the REVEALING phase; reactions appear as floating emoji on the presenter screen in the sending player's nickname colour; reactions animate upward and fade out over 2 seconds; maximum 5 simultaneous visible reactions to avoid covering panels; reactions are received via Socket.IO `player:react` event; phone shows a reaction button row during the reveal phase.

- [ ] M7.8 Presenter Integration Test
  **Objective:** Manually verify the complete presenter flow using a set of fixture assets (sample panels and audio) representing a full round.
  **Dependencies:** M7.7.
  **Completion criteria:** Fixture asset set created (6 placeholder panels + 6 narration WAVs); presenter loads fixture assets correctly; title card appears then transitions to panel 1; all 6 panels reveal in sequence with audio sync; emoji reactions from a test phone appear on screen; full reveal sequence completes without errors; tested on Windows with Tauri window maximised.

---

## M8 — Full Game Loop

> Goal: A complete game can be played from lobby to final leaderboard. Voting, scoring, the Scânteia mechanic, and multi-round flow all work.

- [ ] M8.1 Voting Engine — Server Side
  **Objective:** Implement the server-side voting engine that distributes vote options, collects votes, and resolves ties.
  **Dependencies:** M1.7, M2.5.
  **Completion criteria:** Three vote categories implemented per GDD Section 5.2: "funniest panel", "best narrator line", "most accurate portrayal"; vote options distributed to all players at start of VOTING phase; each player may cast one vote per category; duplicate votes from same player are rejected; ties are resolved by random selection; vote results persisted in SQLite; `round:vote_results` emitted to all clients at end of VOTING phase.

- [ ] M8.2 Phone — Vote Screen
  **Objective:** Build the Svelte 5 phone screen that presents vote options and collects the player's vote during the VOTING phase.
  **Dependencies:** M8.1, M1.9.
  **Completion criteria:** Displays all three vote categories with tappable options; options for "funniest panel" show panel thumbnail images; player can change vote before submitting; submit button sends `player:vote` event; after submitting, transitions to a waiting screen showing vote count progress; vote screen is visually distinct from the answer screen; works on mobile touch without misfire.

- [ ] M8.3 Scoring Engine
  **Objective:** Implement the scoring engine with the full point structure from GDD Section 5.2.
  **Dependencies:** M8.1.
  **Completion criteria:** All point values implemented per GDD Section 5.2: participation (100), answer in story (200), voted funniest panel (300), voted best line (300), voted best portrayal (250), voted for winner (100), first to submit (50), streak bonus (150); scores persisted in SQLite per round and cumulative; score deltas calculated per round; scoring engine is a pure function (same inputs → same outputs) for testability.

- [ ] M8.4 Scânteia Mechanic
  **Objective:** Implement the anti-runaway Scânteia scoring multiplier for the last-place player, visible only to the host.
  **Dependencies:** M8.3.
  **Completion criteria:** After round 2, last-place player's votes count as 1.5× for scoring purposes; multiplier is applied silently (player is not informed); host dashboard shows which player has the active Scânteia; multiplier resets each round (last-place player may change); if last-place player wins a round, no multiplier next round; mechanic is documented in host-facing UI only.

- [ ] M8.5 Leaderboard & Score Screen
  **Objective:** Build the post-round score screen on the presenter and the phone score notification.
  **Dependencies:** M8.3, M7.6.
  **Completion criteria:** Presenter shows animated leaderboard after voting closes; score deltas animate up next to each player name; first place is visually distinguished; leaderboard is readable from 3m; phones show each player their own score change and current rank; "best moment" (highest-voted panel) is replayed for 3 seconds before leaderboard appears; leaderboard displays for 10 seconds before host can advance.

- [ ] M8.6 Multi-Round Flow
  **Objective:** Implement the full multi-round loop so the game advances from round end back to a new PROMPTING phase without requiring a page reload on any device.
  **Dependencies:** M8.5, M1.7.
  **Completion criteria:** After leaderboard, host sees a "Start Next Round" button; state machine resets to WAITING then immediately advances to PROMPTING on host action; all phones receive new prompts without reloading; round number increments correctly; prompt assignment avoids repeating prompts used in previous rounds of the same session; SQLite preserves all previous round data while new round begins.

- [ ] M8.7 Game End & Final Leaderboard
  **Objective:** Implement the game end flow triggered after the configured number of rounds, with a final leaderboard and winner announcement.
  **Dependencies:** M8.6.
  **Completion criteria:** Host configures number of rounds before game start (default 4); after final round scoring, state transitions to `GAME_OVER`; presenter shows final leaderboard with winner crown animation; winner's best panel from the game is displayed full-screen; phones show final rankings; host can start a new game (full reset) or end the session; all session data remains in SQLite for potential replay.

- [ ] M8.8 Full Loop Playtest Build
  **Objective:** Run a manual end-to-end playtest of the complete game loop with 3–4 real phones and verify every phase works correctly.
  **Dependencies:** M8.7.
  **Completion criteria:** 4 phones join via QR code; 3 rounds played to completion; all prompts delivered; all answers collected; AI pipeline runs and produces comic (fixture may be used if AI not yet stable); voting works on all phones; scoring correct; Scânteia applied silently; game ends with final leaderboard; no crashes or unrecoverable errors during the session; issues found are logged as new tasks.

---

## M9 — Polish & UX

> Goal: The game feels finished. Romanian copy everywhere. Genre-specific loading experience. Sound effects. Streamer-friendly output. Safe mode works.

- [ ] M9.1 Romanian UI Copy Pass
  **Objective:** Replace all placeholder English text in every UI screen (phone shell, host dashboard, presenter) with final Romanian copy.
  **Dependencies:** M8.8.
  **Completion criteria:** All button labels, prompts, status messages, error messages, and UI strings are in Romanian; no English strings visible to players during normal gameplay; error messages are in Romanian and actionable; a string constants file exists per UI component (no hard-coded UI strings in component logic); Romanian diacritics render correctly on all target browsers.

- [ ] M9.2 Generation Loading Experience
  **Objective:** Build the cinematic loading experience shown during the GENERATING phase that keeps players engaged while the AI pipeline runs.
  **Dependencies:** M7.6, M3.6.
  **Completion criteria:** As soon as GENERATING phase starts, presenter shows the genre title card with dramatic reveal animation; after 5 seconds, a teaser text appears (e.g. a fragment of the story title or genre atmosphere line); progress indicator shows pipeline steps completing (story written → panels generating → audio ready); total loading screen feels intentional and atmospheric, not like a spinner; phones show a "preparing your story…" screen with the genre name during this phase.

- [ ] M9.3 Sound Effects
  **Objective:** Add non-narration sound effects to the presenter: genre sting on title card, panel transition sounds, voting open/close sounds, score animation sounds.
  **Dependencies:** M7.6, M8.5.
  **Completion criteria:** Genre title card plays a short atmospheric sound sting matching the genre (e.g. violin sting for telenovelă, electric guitar for acțiune); panel transitions have a subtle page-turn or cinematic whoosh sound; voting opens with a sound; leaderboard score animation has a sound; all sounds are royalty-free or generated; volume is controllable by host; sounds do not overlap with narration audio.

- [ ] M9.4 Safe Mode Implementation
  **Objective:** Implement the Safe Mode flag that filters prompts and modifies LLM instructions to produce family-appropriate content.
  **Dependencies:** M2.2, M4.5.
  **Completion criteria:** Host can toggle Safe Mode before starting a game; Safe Mode filters all prompts with `safeMode: false` from assignment; LLM system prompt includes a safe mode instruction removing crude humour, adult themes, and dark comedy; narrator persona mapping excludes sarcastic or dark personalities; Safe Mode state is persisted in the room config in SQLite; all 7 genres have a safe mode variant of their narrator personality.

- [ ] M9.5 Host Dashboard — Full Controls
  **Objective:** Build the complete host dashboard with all controls needed to run a game: player management, round config, Safe Mode, debug panel.
  **Dependencies:** M8.7, M9.4.
  **Completion criteria:** Host dashboard shows: QR code, live player list with connection status and Scânteia indicator, round config (number of rounds, timer durations, Safe Mode), game start/next round/end buttons, pipeline status during generation, debug log of last pipeline run; all controls work without a page reload; host dashboard is served at `/host` and is password-protected (configurable password in `.env`).

- [ ] M9.6 Streamer Mode
  **Objective:** Implement a streamer-friendly output mode that adds an OBS-compatible overlay output and removes player real names from the on-screen display if requested.
  **Dependencies:** M9.5.
  **Completion criteria:** Streamer mode toggled from host dashboard; in streamer mode, the presenter window outputs a clean composite suitable for OBS window capture; an additional `/overlay` endpoint serves a transparent HTML overlay with current game state for OBS browser source; player names can be replaced with aliases in streamer mode; no Twitch/YouTube API integration required at this stage.

---

## M10 — Playtesting

> Goal: The game has been tested with real players in real conditions. Bugs are found and fixed. The experience is genuinely funny.

- [ ] M10.1 Internal Playtest Session #1
  **Objective:** Run a controlled playtest with 4–6 players, a full 4-round game, and structured feedback collection.
  **Dependencies:** M9.6.
  **Completion criteria:** Session recorded (screen capture of presenter); each player completes a short feedback form (5 questions: funniest moment, most confusing moment, would you play again, what felt broken, free comment); all feedback documented; top 5 issues identified and logged as new tasks; AI story quality rated by players on a 1–5 scale (target: ≥3.5 average).

- [ ] M10.2 Bug Fix Sprint #1
  **Objective:** Address all critical and high-priority bugs identified in playtest session #1.
  **Dependencies:** M10.1.
  **Completion criteria:** All bugs rated "game-breaking" or "prevents round completion" are fixed; each fix has a regression test where applicable; no new bugs introduced (verified by re-running M8.8 playtest build checklist); fixed bugs documented in git commit messages.

- [ ] M10.3 Internal Playtest Session #2
  **Objective:** Run a second playtest incorporating fixes from M10.2 and testing edge cases: player disconnect mid-round, Safe Mode, 2-player game, 8-player game.
  **Dependencies:** M10.2.
  **Completion criteria:** Session covers edge cases: one player disconnects during PROMPTING and reconnects; Safe Mode produces no adult content; 2-player game completes without errors; 8-player game does not degrade story quality significantly; new bugs logged; AI story quality re-rated (target: ≥4.0 average).

- [ ] M10.4 Bug Fix Sprint #2
  **Objective:** Address all issues identified in playtest session #2.
  **Dependencies:** M10.3.
  **Completion criteria:** All critical bugs fixed; edge case behaviours are consistent and graceful; performance on RTX 4070 meets GDD targets (panel generation ≤20s each); ElevenLabs fallback to Piper tested and confirmed working.

---

## M11 — Distribution

> Goal: Anyone with a Windows PC and an RTX 4070 can install and run the game by following the README.

- [ ] M11.1 Setup Scripts
  **Objective:** Write PowerShell setup scripts that install all dependencies, download AI models, and configure the environment for a fresh Windows machine.
  **Dependencies:** M10.4.
  **Completion criteria:** `scripts/setup.ps1` installs: Node.js 22, Python 3.12, Ollama, ComfyUI, Piper; `scripts/install-models.ps1` pulls Llama 3.1 8B via Ollama and downloads FLUX.1 schnell weights; scripts are idempotent (safe to run twice); scripts display clear progress and estimated time; scripts validate GPU presence and VRAM (warn if < 12GB); `.env.example` file documents all required environment variables including ElevenLabs API key.

- [ ] M11.2 Windows Installer
  **Objective:** Package the complete application (Node.js server, Python pipeline, Tauri presenter, phone client) into a single Windows installer.
  **Dependencies:** M11.1.
  **Completion criteria:** Installer built with NSIS or Tauri's built-in installer; single `.exe` installs all components to `Program Files\AGORA`; installer does not bundle AI model weights (too large — setup script handles this separately); uninstaller cleanly removes all components; installed application starts via a single desktop shortcut that launches all processes; tested on a clean Windows 11 VM.

- [ ] M11.3 README & Documentation
  **Objective:** Write the final README.md and all supporting documentation needed for someone to install, configure, and host a game session.
  **Dependencies:** M11.2.
  **Completion criteria:** README covers: system requirements, installation steps, first-run guide, how to host a game, how to configure Safe Mode and streamer mode, ElevenLabs API key setup, troubleshooting common issues; `docs/` folder contains: architecture overview, ADR for each major technical decision, AI model setup guide; all documentation is in Romanian and English; README reviewed for accuracy against the actual installation process.

- [ ] M11.4 Final Milestone Commit
  **Objective:** Tag the v1.0.0 release, produce the final build artefacts, and update the roadmap.
  **Dependencies:** M11.3.
  **Completion criteria:** Git tag `v1.0.0` created; `roadmap.md` updated with all milestones marked complete; `TASKS.md` updated with all tasks checked; release notes written describing what the game is, what it includes, and known limitations; installer `.exe` and setup scripts archived; repository is in a state where a new contributor can clone it, run setup, and play a game.

---

## Current Status

**Current Milestone:** M5 — Image Pipeline
**Current Task:** M5.1 ImageGeneratorProvider Interface
**Next Task:** M5.2 Character Description System
**Overall Progress:** 34 / 48 tasks complete
---

## Development Rules

- Always implement **only the first unchecked task**.
- Never begin the next task without explicit approval.
- After finishing a task:
  - Mark it `[x]` in this file.
  - Update the **Current Status** block.
  - Recommend a git commit message.
  - **Stop immediately.**
- If a task reveals a technical problem requiring an architecture change, **stop and explain** before changing anything.
- Do not create files or folders not specified in the GDD folder structure without approval.
- Every task must leave the codebase in a **working, runnable state** — no half-finished broken builds.
