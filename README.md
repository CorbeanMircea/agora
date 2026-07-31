# AGORA

**Platform codename:** AGORA
**Game #1 codename:** CRONICA
**Document version:** GDD v0.2.1

## What Is This?

AGORA is a local-multiplayer party game platform for Windows. Players join on their phones via QR code. The host's PC runs the game and presents AI-generated content on a large screen.

CRONICA is the first game built on AGORA. Players answer absurd Romanian prompts; the platform's AI pipeline turns their answers into a genre-specific comic strip with narration.

## Stack

| Layer | Technology |
|---|---|
| Platform server | Node.js 22 LTS + Fastify + Socket.IO + SQLite (better-sqlite3) |
| Phone client | Svelte 5 + SvelteKit + adapter-static |
| Presenter | Tauri 2 + Rust + WebView |
| AI orchestrator | Python 3.12 |
| LLM | Ollama + Llama 3.1 8B |
| Image generation | ComfyUI + FLUX.1 schnell |
| TTS | ElevenLabs (Piper offline fallback) |

## Hardware Requirements

- Windows 11
- NVIDIA RTX 4070 (12 GB VRAM minimum)
- 32 GB RAM recommended
- LAN WiFi for phone connections

## Quick Start

> Full setup scripts are implemented in M11. This section will be completed then.

## Repository Structure

```
/agora
  /platform
    /server          Node.js 22 + Fastify + Socket.IO
    /phone-shell     Svelte 5 shared phone UI shell
  /games
    /cronica         CRONICA game module
      /prompts       prompt packs (JSON)
      /pipeline      Python AI orchestrator
      /presenter     Tauri 2 comic presenter
      /phone-ui      Svelte 5 game screens
  /output            generated assets (gitignored)
  /docs              ADRs, architecture diagrams, GDD
  /scripts           setup.ps1, install-models.ps1
  README.md
  roadmap.md
```

## Codenames

- **AGORA** the platform (lobby engine, round state machine, AI pipeline interface)
- **CRONICA** the first game module running on AGORA

## Development

See roadmap.md for milestone status.
See TASKS.md for the full task list (source of truth for current task).