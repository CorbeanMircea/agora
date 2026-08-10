CRONICĂ \## Party Platform & Comic AI Game **Game Design Document · v0.2
· Confidential**

           Platform Codename: AGORA
         First Game Codename: CRONICĂ

Romanian-first · 18+ · LAN/Discord · AI-powered

              Prepared by: Technical Lead

Status: Pre-production · Pending approval to begin M1

## Executive Summary

CRONICĂ is an AI-powered party game and the flagship title of AGORA ---
a reusable, extensible party game platform designed to become the
Romanian equivalent of Jackbox Games. It is not a Jackbox clone. It is a
new category of party game experience built around AI-generated content
that feels genuinely surprising, funny, and unrepeatable. Players submit
answers to absurd prompts on their phones. The AI pipeline --- guided by
a Creative Director --- generates an original comic story in one of
several cinematic genres. The comic is then revealed panel by panel with
narration, sound effects, and cinematic animation. Players vote. The
best comic wins. The cycle repeats. The platform (AGORA) handles all
shared infrastructure: lobbying, networking, player management, timers,
voting, and scoring. CRONICĂ is Game #1 built on top of it. Future games
can be added to the platform without re-engineering the foundation.

Attribute Value

Platform name AGORA

Game #1 name CRONICĂ

Target audience 18+, friends, LAN parties, Discord calls, streamers

Language Romanian first, English later

Deployment Local Windows PC (RTX 4070), phones via browser, no install

AI stack Ollama + Llama 3.1 8B, ComfyUI + FLUX.1 schnell, ElevenLabs TTS
(Piper offline fallback)

Tech stack Node.js 22 LTS, Fastify, Socket.IO, Svelte 5, Tauri 2, Python
3.12

Licencing model TBD --- architecture supports commercial from day one

Current status Pre-production, GDD approval pending

## Table of Contents

This document covers: Platform Vision · Game Design · Player Experience
· AI Systems · Creative Director · Technical Architecture · Risk
Analysis · Milestones

# 1 Platform Vision: AGORA

## 1.1 Why a Platform, Not a Single Game

The most expensive part of any party game is the shared infrastructure:
lobbying, QR code joining, phone clients, timers, round management,
voting, leaderboards, and asset delivery. Building this once and reusing
it across multiple games is the correct architectural decision. AGORA is
the engine. CRONICĂ is the first game. Future titles --- quiz games,
drawing games, debate games, improv games --- all inherit AGORA without
re-engineering networking or phone clients. DECISION AGORA must be
designed so that adding a new game requires only: a new game module +
new phone UI screens + new asset pipeline. Zero changes to core
infrastructure.

## 1.2 Platform Components

Component Responsibility Reused by all games?

Lobby Manager Room creation, QR code, player join/leave, host Yes
controls

Player Manager Nicknames, avatars, connection state, reconnection Yes

Round Engine Phase sequencing, timers, state machine Yes

Submission Collector Receives and stores player answers per phase Yes

Voting Engine Distributes options, collects votes, resolves ties Yes

Scoring Engine Points, streaks, bonuses, round/game totals Yes

Asset Delivery Serves generated images and audio to presenter Yes

AI Pipeline Story → images → audio orchestration Per game (pluggable)

Presenter Layer Cinematic reveal, animation, effects Per game

Phone Client Shell QR join, name entry, connection indicator Yes

Phone Game Screens Answer prompts, vote, react, wait screen Per game

## 1.3 Platform Extensibility Contract

Every game built on AGORA must implement exactly one interface: the Game
Module Interface. This is the contract between the platform and the
game.

interface AgoraGameModule { id: string // unique game identifier name:
string // display name minPlayers: number maxPlayers: number phases:
PhaseDefinition\[\] // ordered list of round phases promptPack:
PromptPack // questions/prompts for this game pipeline: AIPipeline //
pluggable AI pipeline (optional) presenterUI: PresenterModule // Tauri
UI for this game phoneUI: PhoneModule // Svelte screens for this game }

CRONICĂ implements this interface. A future quiz game implements it
differently. AGORA does not care what the game does --- only that it
honours the interface.

# 2 Game Design: CRONICĂ

## 2.1 Core Concept

Players answer absurd, funny, or deeply personal prompts. The AI reads
all answers and writes an original Romanian story in a randomly selected
cinematic genre. It turns that story into a comic with generated art,
narration, sound, and cinematic animation. The comic is revealed to
everyone simultaneously. Players vote on which element was funniest.
Points are awarded. Repeat. The reveal is the reward. The comic is the
reward. The narrator is the reward. Players should feel genuine surprise
at what the AI created from their inputs. DESIGN PRINCIPLE The AI must
feel like a writer who happened to overhear the players, not like a
machine that filled blanks in a template. Player answers are fuel, not
slots.

## 2.2 Core Gameplay Loop

┌─────────────────────────────────────────────────────────────┐ │
CRONICĂ GAME LOOP │ │ │ │ HOST opens game → QR code displayed on
TV/monitor │ │ │ │ │ PLAYERS scan QR → browser opens → enter nickname │
│ │ │ │ HOST starts round when ready (2-8 players) │ │ │ │ │
┌──────▼──────────────────────────────────────────────┐ │ │ │ ROUND LOOP
│ │ │ │ │ │ │ │ Phase 1: PROMPT PHASE (60-90s) │ │ │ │ Each player sees
2-3 prompts on their phone │ │ │ │ Players type answers (text, sometimes
emoji) │ │ │ │ Timer visible on all phones │ │ │ │ │ │ │ │ │ Phase 2:
GENERATION PHASE (60-90s) │ │ │ │ AI pipeline runs (story → images →
audio) │ │ │ │ Teaser/loading shown on presenter screen │ │ │ │ Genre
title revealed dramatically │ │ │ │ │ │ │ │ │ Phase 3: REVEAL PHASE
(90-120s) │ │ │ │ Comic plays panel by panel with narration │ │ │ │
Players react in real-time on phones │ │ │ │ │ │ │ │ │ Phase 4: VOTING
PHASE (30s) │ │ │ │ Players vote: funniest panel, best line, │ │ │ │
most accurate player portrayal │ │ │ │ │ │ │ │ │ Phase 5: SCORING PHASE
(15s) │ │ │ │ Points awarded, leaderboard updated │ │ │ │ Best moment
replayed │ │ │ └──────────────────────────────────────────────────────┘
│ │ │ │ │ After N rounds: GAME END → Final leaderboard → Share │
└─────────────────────────────────────────────────────────────┘

## 2.3 Player Count & Session Length

Players Recommended Rounds Estimated Session Notes

2--3 5--6 45--60 min Intimate; prompts adjusted for fewer inputs

4--6 4--5 60--75 min Sweet spot; richest story inputs

7--8 3--4 60--90 min Max chaos; funniest reveals

8+ Not recommended --- Story coherence degrades with too many inputs

# 3 Player Experience

## 3.1 Journey Map: From Zero to First Laugh

Moment What Happens Emotion Target Design Notes

Host opens app QR code + room code Curiosity, QR must be large,
scannable from appear on TV anticipation 3m away

Player scans QR Phone opens instantly, no Relief, delight Page must load
in \<2s on any install phone browser

Enter nickname Name appears on TV in real Social recognition TV shows
each new player joining time with a sound

Prompts appear Personal, specific, funny Mild panic, Players should feel
slightly exposed prompts excitement

Submit answers Confirmation + wait screen Suspense Show how many players
still typing

Generation starts Dramatic genre reveal on TV Excitement Genre title
should feel like a film title card

Comic begins First panel appears with Shock, laughter First panel must
land a joke or narration reveal

Recognition Player sees their answer in Pride, This is the core social
loop moment story embarrassment

Voting Quick tap vote on phone Agency, Should feel like applause, not
investment homework

Score reveal Points, animations, Competition, joy Loser needs to feel
OK; winner highlights needs to feel great

## 3.2 Why The Game Is Fun

The answer is always: recognition + surprise + social permission.
Recognition: players see their words woven into a story. The AI used
their answer. They matter. Their silly response shaped the comic.
Surprise: the AI takes unexpected directions. The genre the Creative
Director chose might be the last thing anyone expected. The narration
style transforms mundane answers into dramatic events.

Social permission: the game gives players permission to be absurd,
crude, or vulnerable within the safety of a game structure. The AI takes
the blame for the story. Players can claim authorship of the funny parts
and disavow the embarrassing ones.

## 3.3 The Recognition Moment

KEY INSIGHT The funniest moment in every round is when a player
recognises their own answer inside the AI story. Design the prompt
system and LLM instructions to guarantee this moment happens in every
single round. This means: every player answer must appear in the story
in a way that is recognisable but transformed. The LLM must be
instructed to incorporate every submitted answer, not just the funniest
ones. A boring answer made interesting by the AI context is funnier than
a funny answer that gets ignored.

# 4 Prompt System Design

## 4.1 Design Philosophy

Prompts must provide the LLM with interesting raw material, not
blank-filling data. The difference is between "Name a vegetable"
(produces: carrot → story says carrot) and "What would you bring to a
hostage negotiation?" (produces: a banana → story has to explain why
someone brought a banana to a hostage negotiation). The second type
gives the AI something to work with. The prompt forces a contextually
inappropriate answer. The context gap is where the comedy lives.

## 4.2 Prompt Categories

Category Example Prompt What It Produces for the LLM

Inappropriate expert Ce sfat ai da unui chirurg înainte de o Absurd
professional advice in serious context operație importantă?

Social confession Care e cel mai suspect lucru pe care l- Personal
revelation usable as character ai făcut de unul singur? motivation

Object as character Dacă telefonul tău ar putea vorbi, ce Non-human
character voice for the story ar reclama?

False expertise Explică în 10 cuvinte cum funcționează Overconfident
nonsense presented as fact economia mondială.

Relationship Scrie o acuzație neadevărată despre Inter-player conflict
material for the story accusation jucătorul din stânga ta.

Secret motivation De ce face cu adevărat \[player name\] Hidden
backstory for named character ce face?

Crisis response Ce faci primul când izbucnește un Reveals character
priorities under pressure incendiu acasă?

Romanian specific Care e scuza ta preferată când întârzii Culturally
specific, immediately funny to la o nuntă? Romanians

Absurd superlative Care este cel mai periculos lucru din Specific
mundane object in dangerous Lidl? framing

Time pressure Ai 5 secunde să convingi un vampir să Forces impulsive,
unconsidered answers te lase în pace. Ce spui?

## 4.3 Prompt Assignment Strategy

Not every player sees the same prompts. The system should: ● Assign 2--3
prompts per player per round ● Ensure no two players answer the exact
same prompt (avoids redundant LLM inputs) ● Include at least one prompt
that references another named player (generates inter-character
dynamics) ● Vary category balance across rounds (no two consecutive
rounds with same dominant category) ● Scale prompt difficulty/absurdity
with round number (round 1 safe, round 4 chaotic)

## 4.4 Safe Mode

For family gatherings or younger audiences, a Safe Mode flag filters
out: ● Prompts referencing alcohol, relationships, or embarrassment ●
LLM instructions for crude humour or adult themes ● Narrator
personalities with sarcasm or dark humour RISK Safe Mode content must be
explicitly tagged in the prompt database. Do not rely on LLM filtering
at runtime --- it is inconsistent. Filter at prompt selection time.

# 5 Scoring System

## 5.1 Design Goals

The scoring system must achieve three things simultaneously: reward
participation, reward quality, and prevent runaway leaders. A game where
one player dominates every round stops being fun. A game where everyone
gets equal points removes stakes.

## 5.2 Point Structure

Action Points Notes

Submitting any answer before timer 100 Participation baseline --- no one
scores zero for trying ends

Your answer appears in the story 200 Guaranteed if LLM is prompted
correctly (confirmed)

Voted "funniest panel" (from your 300 Votes come from other players
answer)

Voted "best line" (narration 300 Separate vote category referencing your
answer)

Voted "most accurate portrayal" of 250 For player-targeting prompts a
player

Voting for the eventual winning 100 Rewards taste, not just luck panel

First to submit in round 50 Small speed bonus

Streak: voted best 2 rounds in a row 150 bonus Comeback mechanic too ---
streaks reset

Host award (manual, once per 200 Host can award for something not
captured by voting game)

## 5.3 Anti-Runaway Mechanic

After round 2, the player in last place receives a "Scânteia" (spark)
modifier: their votes count as 1.5× for one round. This is not announced
to them --- only the host sees it on the host dashboard. It prevents
elimination- feeling without being obvious charity.

DESIGN NOTE The Scânteia must feel like earned luck, not pity. The
player should think they just had a great round. Never show the modifier
to all players --- only the host.

# 6 The Creative Director

## 6.1 Concept

The Creative Director (CD) is the brain of the AI pipeline. It is not a
genre picker. It is a system that generates a complete creative brief
before any story, image, or audio is produced. Every downstream AI
component --- the LLM, ComfyUI, and ElevenLabs TTS --- receives the CD
brief and uses it to shape their output. The result is that each round
feels like it was made by a different creative team with a different
vision, not like the same template running again.

## 6.2 Creative Brief Structure

CreativeBrief { // Narrative genre: string // e.g. "Telenovelă
Românească" subgenre: string // e.g. "Răzbunarea neașteptată"
storyStructure: StoryArc // act structure, beat map archetypes:
Archetype\[\] // roles player answers will fill twists: Twist\[\] // 1-2
mandatory story twists comedyLevel: 1-10 // 1=dry/dark, 10=pure
slapstick toneKeywords: string\[\] //
\["melodramatic","breathless","ironic"\]

      // Presentation
      format:              PresentationFormat      // comic | fakeNews | policeReport | documentary
      panelCount:          4 | 5 | 6 | 8
      panelLayout:         LayoutStrategy          // how panels are arranged

      // Visual
      visualStyle:         string           // e.g. "oversaturated Romanian soap opera"
      colourPalette:       string[]         // dominant hex colours for panels
      cameraLanguage:      CameraRule[]     // "panel 1 = wide establishing shot"
      lightingMood:        string           // "warm, harsh top light, dramatic shadows"

    // Audio
    narratorPersonality: NarratorPersona
    narratorVoiceKey:    string     // maps to ElevenLabs voice ID (or Piper model ID in

offline mode) musicDirection: string // "tense strings, sudden silence
on twist" soundEffects: SFXNote\[\] // per-panel sound effect notes

      // Pacing
      revealPacing:        "slow-burn" | "rapid-fire" | "deliberate" | "chaotic"
      punchlinePanel:      number        // which panel delivers the main joke

}

## 6.3 Genre Registry

Each genre is a complete creative template, not a label. The CD selects
one genre per round and populates the brief from that genre's defaults,
then randomises within the allowed variance for that genre.

Genre 1: Telenovelă Românească

Attribute Value

Story structure Secret revealed → denial → tearful confrontation →
unexpected twist → dramatic freeze-frame ending

Character archetypes Vinovatul (guilty one), Victima (victim), Martorul
tăcut (silent witness), Cel care știa tot (the one who knew everything)

Comedy level 6--8 --- melodrama played completely straight is the joke

Visual style Warm oversaturated colours, extreme close-ups on faces,
dramatic zoom panels, tears rendered visibly

Camera language Panel 1: wide establishing. Panel 2--3: alternating
close-ups. Panel 4: shocking revelation. Panel 5: reaction shots. Final:
freeze-frame

Narrator personality Breathless, rhetorical questions, speaks directly
to viewer, gasps mid-sentence

Music direction Dramatic violin, sudden silence before twist, crescendo
on final panel

Colour palette Gold, deep red, amber --- warm, passionate, slightly
overcooked

Genre 2: Film de Acțiune B Românesc

Attribute Value

Story structure Mission briefing → complication → betrayal → improvised
revenge → explosion ending

Character archetypes Eroul ghinionst (unlucky hero), Trădătorul elegant
(elegant traitor), Complicele naiv (naive sidekick), Șeful misterios
(mysterious boss)

Comedy level 7--9 --- sincerity of cheap action cinema applied to absurd
situations

Visual style High contrast, deep shadows, explosion backgrounds, lens
flare on every surface

Camera language Low angle hero shots, extreme close-up on eyes before
action, wide for explosions, slow-motion implied in final panel

Narrator personality Gravelly, terse, uses ellipses heavily, references
honour and vengeance often

Music direction Electric guitar riff, bass drop, dramatic pause before
final line

Colour palette Orange, deep blue, black --- classic action poster
palette

Genre 3: Basm Românesc Absurd

Attribute Value

Story structure Ordinary problem → magical interference → problem gets
worse → wise fool solves it accidentally

Character archetypes Prostul norocos (lucky fool), Înțeleptul inutil
(useless wise man), Forța cosmică (cosmic force that could not care
less), Animalul filozofic (philosophising animal)

Comedy level 8--10 --- pure absurdism, formal fairy-tale register
applied to ridiculous events

Visual style Folk art colour palette, flat perspective, decorative
borders inspired by Romanian painted eggs and embroidery

Camera language Symmetrical compositions, characters always face viewer,
no perspective --- flat like folk illustration

Narrator personality Formal fairy-tale register ("A fost odată ca
niciodată..."), completely deadpan about impossible events

Music direction Folk instruments (nai, cobza), whimsical, slightly
off-key, melancholy-funny

Colour palette Deep red, cobalt blue, gold, forest green --- Romanian
folk art palette

Genre 4: Scandal de Bloc

Attribute Value

Story structure Minor grievance → neighbour coalition formation →
emergency bloc meeting → absurd resolution that satisfies no one

Character archetypes Reclamantul profesionist (professional complainer),
Acuzatul indignat (indignant accused), Vecinii curioși (nosy
neighbours), Administratorul absent (absent building manager)

Comedy level 9 --- maximum petty conflict energy, everyone is completely
serious about something trivial

Visual style Cramped panel compositions, many faces crammed into frame,
thought bubbles showing private judgements contradicting dialogue

Camera language Overhead crowd shots, whispering two-shots, dramatic
door-opening panels, final panel shows everyone at their own door
pretending nothing happened

Narrator personality Gossipy, conspiratorial, makes knowing asides to
reader, takes sides then changes sides

Attribute Value

Music direction Tense silence, door slams, muffled arguing from adjacent
panels

Colour palette Institutional beige, harsh fluorescent blue, grey
concrete --- bloc building palette

Genre 5: Documentar Fals

Attribute Value

Story structure Authoritative thesis → contradictory evidence appears →
expert panel disagrees with increasing emotion → absurd authoritative
conclusion presented as established fact

Character archetypes Expertul îndoielnic (dubious expert), Subiectul
confuz (confused subject), Vocea Oficială (the official voice), Martorul
anonim (anonymous witness, face blurred)

Comedy level 5--7 --- dry, deadpan, the comedy is how seriously everyone
takes nonsense

Visual style Muted documentary palette, caption boxes with fake
credentials, blurred backgrounds, simulated archival footage aesthetic

Camera language Talking-head interview panels, b-roll cutaway panels,
caption-heavy layouts, one panel must be "security camera footage"

Narrator personality BBC documentary register, measured and
authoritative, never acknowledges the absurdity, treats everything as
established fact

Music direction Ambient drone, occasional tense musical sting, long
silences

Colour palette Desaturated grey-green, off-white, institutional blue ---
documentary television palette

Genre 6: Horror Mioritic

Attribute Value

Story structure Omen ignored → escalation of signs → confrontation with
inevitable force → fatalistic acceptance and poetic ending

Character archetypes Cel marcat (the marked one), Sfătuitorul ignorat
(the ignored advisor), Forța naturii (the natural force --- not
necessarily evil), Animalul care știe (the knowing animal)

Attribute Value

Comedy level 3--5 --- the comedy is the Romanian cultural attitude of
calm acceptance toward disaster, not the disaster itself

Visual style Desaturated, fog effects, silhouettes against sky,
woodcut-inspired line work, wolves optional but appreciated

Camera language Atmospheric wide shots, long silences implied by empty
panels, face never fully visible until final panel

Narrator personality Fatalistic, poetic, uses metaphor from nature,
completely calm about terrible things, occasionally philosophical

Music direction Solo doina, wind sounds, distant bells, silence at
moment of revelation

Colour palette Grey-blue, forest green, charcoal, single gold accent ---
Carpathian palette

Genre 7: Știri Rupte din Realitate

Attribute Value

Story structure Breaking news intro → contradictory reporter on the
ground → social media eruption → expert analysis that misses the point →
resolution that raises more questions

Character archetypes Prezentatorul de știri (news anchor), Reporterul
confuz (confused field reporter), Expertul de serviciu (on-call expert),
Cetățeanul revoltat (outraged citizen)

Comedy level 8--9 --- satirises Romanian news media specifically,
recognisable to all Romanian players

Visual style News broadcast aesthetic, lower-third graphic boxes,
split-screen panels, ticker tape text, aggressive red colour scheme

Camera language Talking-head panels with graphic overlays, chaotic
split-screen, one panel must be a phone-filmed vertical video

Narrator personality Breathless news anchor energy, treats everything as
the biggest story of the century, dramatic pause before every number

Music direction News jingle stab, urgent music bed, social media
notification sounds

Colour palette Aggressive red, white, black --- Romanian television news
palette

## 6.4 Presentation Formats

The Creative Director also selects a presentation format. Genre
determines the story. Format determines how the story is visually
presented. These are independent axes.

Format Description Compatible Genres

Western Comic Standard panel layout, speech bubbles, All genres action
lines

Fake News Broadcast TV news aesthetic, lower thirds, graphics Știri
Rupte, Documentar Fals

Police Report Bureaucratic document with hand-drawn Scandal de Bloc,
Acțiune B witness sketches

Documentary Film Mixed panel/caption layout, interview Documentar Fals,
Horror Mioritic stills, b-roll

Folk Tale Illustration Single-page illustrated spread, flat folk art
Basm Românesc style

Instagram Story Vertical panels, phone-native aesthetic, Știri Rupte,
Telenovelă Sequence emoji overlays

Interpol Dossier Case file aesthetic, redacted text, Acțiune B,
Documentar Fals surveillance photos

# 7 AI Pipeline Architecture

## 7.1 Provider Interface Design

Every AI component is accessed through a provider interface. The game
logic never calls Ollama, FLUX, ElevenLabs, or Piper directly. It calls
the interface. The interface has concrete implementations for each
provider, and the default can be swapped at any time. This means: if a
better LLM is released tomorrow, we write a new implementation of
StoryLLMProvider and swap it in. Zero changes to game logic.

// Provider Interfaces (Python abstract base classes)

class StoryLLMProvider(ABC): @abstractmethod def generate_story(self,
brief: CreativeBrief, answers: PlayerAnswers) -\> Story: ...

class ImageGeneratorProvider(ABC): @abstractmethod def
generate_panel(self, prompt: ImagePrompt, style: VisualStyle) -\>
PanelImage: ...

class TranslatorProvider(ABC): @abstractmethod def translate(self, text:
str, source: str, target: str) -\> str: ...

class TTSProvider(ABC): @abstractmethod def synthesise(self, text: str,
persona: NarratorPersona) -\> AudioFile: ...

// Concrete implementations class OllamaStoryLLM(StoryLLMProvider): ...
class OpenAIStoryLLM(StoryLLMProvider): ... class
FluxImageGenerator(ImageGeneratorProvider): ... class
OpenAIImageGenerator(ImageGeneratorProvider): ... class
ElevenLabsTTS(TTSProvider): ... class PiperTTS(TTSProvider): ...

## 7.2 Pipeline Execution Flow

PIPELINE ORCHESTRATOR

Input: PlayerAnswers, GameState │ ▼ \[1\] CREATIVE DIRECTOR → Selects
genre (weighted random, avoids recent) → Generates CreativeBrief (full
creative specification) → Assigns player answer → archetype mappings │ ▼
\[2\] STORY LLM (Ollama + Llama 3.1 8B) Input: CreativeBrief +
PlayerAnswers Output: Story struct { title: string (Romanian) panels:
PanelDescription\[\] (Romanian) narratorScript: string\[\] (Romanian,
per panel) imagePrompts: string\[\] (English --- translated internally)
}

      VRAM: ~4-6GB | Time: ~15-25s
           │
           ▼ [VRAM CLEARED]

\[3\] IMAGE GENERATOR (ComfyUI + FLUX.1 schnell) Input:
imagePrompts\[\] + VisualStyle + CharacterDescriptions Output:
panel_1.png ... panel_N.png VRAM: \~10-11GB \| Time: \~8-15s per panel
Total: \~50-90s for 6 panels │ ▼ \[VRAM CLEARED\] \[4\] TTS (ElevenLabs
default / Piper offline fallback) Input: narratorScript\[\] +
NarratorPersona Output: narration_1.wav ... narration_N.wav VRAM:
minimal (CPU) \| Time: \~1-3s per panel (ElevenLabs API) / \~3-5s (Piper
fallback) │ ▼ \[5\] ASSET PACKAGER Output: round_XXX/ { panels/,
narration/, story.json, brief.json, metadata.json } Signals Node.js
server: pipeline_complete

## 7.3 Character Consistency Strategy

Strict face-identity locking across AI panels is an unsolved problem in
open-source image generation. The approach here is visual consistency
through description constraints, not biometric identity.

Technique How It Works Effectiveness

Character Description Each character assigned at story-gen time: High
--- consistent silhouette and Sheet hair colour, clothing,
distinguishing feature. colour Same description in every panel prompt.

Colour-coded clothing Each player-character gets a unique dominant High
--- instinctive visual parsing clothing colour. Reader identifies
character by colour, not face.

Visual style lock Every panel gets the same LoRA/style tokens. Medium
--- depends on style Face variation is hidden by consistent art strength
style.

Panel composition rules CD specifies which character occupies which
Medium --- requires reliable panel region. Prevents accidental character
prompt following confusion.

Character count limit Maximum 3 characters per panel. More than High ---
hard constraint enforced in 3 and consistency collapses. orchestrator

## 7.4 Romanian → English Translation Layer

FLUX.1 and all major image generation models were trained predominantly
on English text. Romanian prompts produce degraded results. The pipeline
maintains a strict separation: ● Story, narrator scripts, panel
descriptions: Romanian throughout ● Image generation prompts: translated
to English before hitting ComfyUI ● Translation is performed by the LLM
itself in the story generation step --- not a separate translation call
● The LLM is instructed to output image prompts in English as part of
its structured JSON response IMPLEMENTATION NOTE Instruct the LLM to
output a JSON struct with Romanian fields and English imagePrompt fields
in a single call. Avoids a separate translation API call and keeps the
image prompt contextually grounded in the story the LLM just wrote.

# 8 Technical Architecture

## 8.1 System Overview

┌──────────────────────────────────────────────────────────────┐ │ HOST
PC (Windows 11, RTX 4070) │ │ │ │
┌─────────────────────────────────────────────────────┐ │ │ │ AGORA
PLATFORM SERVER (Node.js 22 LTS) │ │ │ │ Fastify + Socket.IO + SQLite │
│ │ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │ │ │ │ │ Lobby │
│ Round │ │ Voting │ │ Score │ │ │ │ │ │ Manager │ │ Engine │ │ Engine │
│Engine │ │ │ │ │ └──────────┘ └──────────┘ └──────────┘ └───────┘ │ │ │
│ ┌──────────────────────────────────────────────┐ │ │ │ │ │ CRONICĂ
GAME MODULE │ │ │ │ │ │ Phase defs │ Prompt packs │ Pipeline config │ │
│ │ │ └──────────────────────────────────────────────┘ │ │ │
└──────────────────────┬──────────────────────────────┘ │ │ │ HTTP /
filesystem │ │ ┌──────────────────────▼──────────────────────────────┐ │
│ │ AI PIPELINE ORCHESTRATOR (Python 3.12) │ │ │ │ Creative Director →
LLM → Image Gen → TTS │ │ │ │ Provider interfaces for each AI component
│ │ │ └──────────────────────┬──────────────────────────────┘ │ │ │
assets written to /output/ │ │
┌──────────────────────▼──────────────────────────────┐ │ │ │ PRESENTER
(Tauri 2 + WebView) │ │ │ │ Cinematic panel reveal + audio sync + vote
overlay │ │ │ └─────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────┘ │ LAN
WiFi ┌────────────────┼────────────────┐ ┌────▼────┐ ┌──────▼────┐
┌──────▼────┐ │ Phone 1 │ │ Phone 2 │ │ Phone N │ │Svelte 5 │ │ Svelte 5
│ │ Svelte 5 │ └─────────┘ └───────────┘ └───────────┘

## 8.2 Folder Structure

/agora ← monorepo root ├── /platform ← AGORA shared engine │ ├── /server
← Node.js 22 + Fastify + Socket.IO │ │ ├── /src │ │ │ ├── /core ← lobby,
rounds, voting, scoring │ │ │ ├── /socket ← all Socket.IO event handlers
│ │ │ ├── /db ← SQLite schema + query layer │ │ │ ├── /interfaces ←
GameModule, AIPipeline types │ │ │ └── /config ← platform constants │ │
├── package.json │ │ └── tsconfig.json │ └── /phone-shell ← Svelte 5
shared phone UI shell │ ├── /src │ │ ├── /routes ← join, wait, react
screens │ │ └── /components ← shared UI components │ └──
svelte.config.js │ ├── /games │ └── /cronica ← CRONICĂ game module │ ├──
/prompts ← prompt packs (JSON, tagged)

│ ├── /pipeline ← Python AI orchestrator │ │ ├── /providers ← LLM,
image, TTS, translator │ │ ├── /creative_director ← genre registry +
brief generator │ │ ├── /character ← character description system │ │
└── orchestrator.py ← pipeline entrypoint │ ├── /presenter ← Tauri 2
comic presenter │ │ ├── /src ← Rust backend │ │ └── /ui ← panel
animation HTML/CSS/JS │ └── /phone-ui ← Svelte 5 game screens │ └──
/src/routes ← answer, vote, react screens │ ├── /output ← generated
assets (gitignored) │ └── /round_001 │ ├── panel_1.png ... panel_6.png │
├── narration_1.wav ... narration_6.wav │ ├── brief.json │ └──
story.json │ ├── /docs ← ADRs, diagrams, this GDD ├── /scripts ←
setup.ps1, install-models.ps1 ├── README.md └── roadmap.md

## 8.3 Data Flow: One Complete Round

EVENT ACTOR DATA

host_start_round Node Server → emits prompts to each phone via Socket.IO
player_submit_answer Socket.IO → stored in SQLite round_answers table
all_players_submitted Round Engine → triggers pipeline via HTTP POST
/pipeline/run pipeline_run Python Orch. → reads answers, selects genre,
runs CD creative_brief_ready Creative Director → writes brief.json to
/output/round_XXX/ story_ready Ollama LLM → writes story.json with RO
text + EN prompts panels_ready ComfyUI/FLUX → writes panel_N.png files
narration_ready ElevenLabs/Piper → writes narration_N.wav files
pipeline_complete Python Orch. → POST /pipeline/complete to Node server
trigger_presenter Node Server → IPC message to Tauri window
reveal_starts Tauri Presenter → begins cinematic panel sequence
vote_phase_starts Node Server → emits vote options to all phones
player_vote Socket.IO → stored in SQLite votes table scoring_complete
Scoring Engine → emits leaderboard update to all phones round_end Round
Engine → state reset, await next round

# 9 Component & State Diagrams

## 9.1 Round State Machine

                     ┌─────────────┐
                     │   WAITING   │ ← initial state, players joining
                     └──────┬──────┘
                            │ host.startRound()
                     ┌──────▼──────┐
                     │ PROMPTING │ ← phones show prompts, timer running
                     └──────┬──────┘
                            │ all submitted OR timer expired
                     ┌──────▼──────┐
                     │ GENERATING │ ← AI pipeline running, presenter shows teaser
                     └──────┬──────┘
                            │ pipeline_complete
                     ┌──────▼──────┐
                     │ REVEALING │ ← comic playing panel by panel
                     └──────┬──────┘
                            │ reveal_complete
                     ┌──────▼──────┐
                     │   VOTING    │ ← phones show vote options, 30s timer
                     └──────┬──────┘
                            │ all voted OR timer expired
                     ┌──────▼──────┐
                     │   SCORING   │ ← leaderboard shown, points animated
                     └──────┬──────┘
                            │ more rounds?
               ┌────────────┴────────────┐
        ┌───────▼──────┐          ┌──────▼──────┐
        │ WAITING (→) │           │ GAME_OVER │
        └──────────────┘          └─────────────┘

## 9.2 Socket.IO Event Reference

Event Direction Payload Phase

player:join Client → Server { nickname, roomCode } WAITING

player:joined Server → All { players\[\] } WAITING

round:start Server → All { roundNumber, prompts\[\] } PROMPTING

player:submit Client → Server { answers\[\] } PROMPTING

round:generating Server → All { genreTitle, estimatedSeconds }
GENERATING

round:reveal_ready Server → { assetPath } GENERATING Presenter

round:reveal_panel Server → All { panelIndex } REVEALING

Event Direction Payload Phase

round:vote_start Server → All { voteOptions\[\] } VOTING

player:vote Client → Server { voteType, targetId } VOTING

round:scores Server → All { scores\[\], delta\[\] } SCORING

player:react Client → Server { emoji } REVEALING

player:disconnect Auto { playerId } Any

# 10 Technical Risks & Mitigations

Risk Severity Probability Mitigation

VRAM overflow: LLM + HIGH HIGH Sequential pipeline with explicit VRAM
clear image gen between steps. Monitor with nvidia-smi. Hard limit:
simultaneously exceed never run two AI processes simultaneously. 12GB

LLM produces Mad Lib HIGH MEDIUM Extensive prompt engineering. Eval
suite to test output despite story quality before ship. Genre brief
injection in instructions system prompt, not user prompt.

Character inconsistency MEDIUM HIGH Adopt colour-coded character design.
Accept breaks immersion variation as comic art style. Never promise face
identity.

Phone browser MEDIUM MEDIUM Target ES2020. Test on Android 10+, iOS 14+.
No incompatibility (older Web APIs beyond fetch and WebSocket. Android)

FLUX generates HIGH LOW Negative prompts always active. Content filter
inappropriate content wrapper on all image outputs. Safe Mode blocks
flagged prompts at source.

ElevenLabs API MEDIUM LOW Piper TTS is bundled as offline fallback.
Pipeline unavailable or rate- auto-detects API failure and switches.
Piper quality is limited during play robotic but functional. session

Generation takes \>3 HIGH MEDIUM Cinematic loading experience with
teaser reveals. min and kills energy Genre title reveal at start of
generation. Real-time phone reactions during wait.

LLM hallucinates player HIGH MEDIUM Structured JSON output enforced.
Post-generation names or ignores validation that all player names and at
least N answers answers appear in story.

Local network discovery MEDIUM MEDIUM Display IP address as manual
fallback alongside QR fails on some routers code. mDNS for
auto-discovery.

FLUX.1 schnell license HIGH LOW Provider interface means swap is one
class changes replacement. Monitor Black Forest Labs announcements.

# 11 Milestones & Complexity

## 11.1 Milestone Overview

Milestone Name Deliverable Complexity Est. Duration

M0 GDD Approval This document approved, Low 1--2 days architecture
finalised

M1 Platform Skeleton Node server + Socket.IO lobby + High 5--7 days
phone shell + round state machine

M2 Prompt & Answer Full PROMPTING phase: prompts Medium 3--4 days Loop
delivered, answers collected, timer works

M3 Creative Director Genre registry, brief generation, High 4--5 days
archetype assignment

M4 Story Generation Ollama + Llama 3.1 8B High 5--7 days integration,
structured story output, RO→EN translation

M5 Image Pipeline ComfyUI + FLUX.1 schnell, Very High 7--10 days
character descriptions, panel output

M6 TTS Pipeline ElevenLabs integration (default), Medium 3--4 days Piper
fallback, narrator persona mapping, audio output

M7 Presenter Tauri window, panel animation, High 6--8 days audio sync,
cinematic reveal

M8 Full Game Loop Voting, scoring, Scânteia High 5--6 days mechanic,
leaderboard, multi- round

M9 Polish & UX Romanian UI copy, loading Medium 4--5 days experience,
sound effects, reactions

M10 Playtest Build Complete game, installable, Medium 3--4 days tested
with real players

Milestone Name Deliverable Complexity Est. Duration

M11 Distribution Windows installer, model Medium 3--4 days download
script, README, public build

## 11.2 M1 Detailed Breakdown (First Milestone)

M1 is the most critical milestone because every subsequent milestone
builds on it. It must be engineered correctly. Speed is not the goal.

Task Description Done When

Monorepo setup Git repo, folder structure, tsconfig, shared npm run
build works from root types

Node server Fastify + Socket.IO, basic health endpoint, env Server
starts, /health returns 200 bootstrap config

Room management Create room, generate code, QR code Host creates room,
QR appears generation, room state

Player join flow Phone opens URL, enters name, appears on Player visible
on host within 2s of host screen scan

Connection resilience Reconnection logic, player state preserved on
Phone can reconnect without losing disconnect state

Round state machine State transitions, phase sequencing, event State
transitions logged correctly emissions

Phone shell (Svelte) Join screen, name entry, wait screen, Phone UI
renders on Android + iOS connection indicator

SQLite schema Rooms, players, rounds, answers, votes tables Schema
migration runs cleanly

Integration test Simulate 4 players joining, round starting, All 4
phones see correct state state advancing

# 12 Future Expansion

## 12.1 Future Games on AGORA Platform

Game Concept Mechanic AI Component Needed

Judecata Poporului Players debate absurd court cases, LLM judge persona
AI plays judge

Știri False Players write fake headlines, AI LLM + image gen generates
fake article + image

Karaoke de Poveste AI writes a song in a genre using LLM + music gen
(future) player inputs, players perform

Profeția Bătrânei Players describe events, AI writes a LLM only
prophecy, group interprets

Ghici Cine AI generates anonymous character LLM + voting descriptions,
players guess whose

Filmul Noaptea AI generates a B-movie script using LLM + TTS player
inputs, players perform scenes

## 12.2 Platform Expansion Features

● Streamer mode: OBS overlay output, Twitch chat integration, viewer
voting ● Spectator mode: additional browsers join as viewers without
playing ● Replay system: save and replay best rounds, shareable as video
● Prompt editor: host can create custom prompt packs ● Cloud mode:
optional cloud AI provider for faster generation ● Localisation:
English, French, Hungarian (Romanian minority language) support ● Mobile
app: optional native wrapper for improved phone experience ● Analytics
dashboard: track funniest prompts, most popular genres

## 12.3 AI Pipeline Evolution Path

Phase LLM Image Gen TTS Trigger

Launch (local) Llama 3.1 8B via Ollama FLUX.1 schnell via ElevenLabs Now
ComfyUI Romanian (default), Piper (offline fallback)

Quality Llama 3.3 70B (if VRAM FLUX.1 dev (non- ElevenLabs Better
upgrade allows) or cloud commercial) or SDXL (optional) hardware or
Lightning cloud mode

Commercial Claude claude-sonnet-4-6 Replicate / Fal.ai FLUX ElevenLabs
Commercial cloud or GPT-4o Romanian launch decision

Multimodal GPT-4o vision for prompt Video generation (Sora, Voice
cloning 2026+ reaction Wan)

# 13 Open Decisions Requiring Approval

The following decisions are documented here because they affect
architecture. They do not need to be resolved before M1, but they should
be resolved before the milestone they impact.

Decision Options Impact Needed Before

Monetisation model Free / paid / freemium AI model licence choices, M10
distribution strategy

Distribution channel itch.io / Steam / direct Installer format,
analytics, M11 installer / open source update mechanism

Cloud AI fallback Yes (OpenAI/Replicate) / Provider interface already M5
No (local only) supports it --- just needs keys

Multiplayer over LAN only / NAT traversal / Significant networking M8
internet hosted relay complexity if yes

Save/replay system Yes / No Output folder structure, M7 storage budget

Streamer mode M9 / post-launch Affects Tauri presenter output M9
priority format

Romanian TTS voice DECIDED: ElevenLabs as ElevenLabs API key required
RESOLVED default, Piper as offline for default mode. Piper fallback
bundled for offline LAN play.

# 14 Glossary

Term Definition

AGORA The reusable party game platform. All games run on AGORA.

CRONICĂ The first game built on AGORA. An AI comic generator party game.

Creative Director (CD) The system component that generates the complete
creative brief for each round.

Creative Brief The complete creative specification produced by the CD:
genre, visual style, narrator persona, panel count, etc.

Provider Interface An abstract interface for an AI component (LLM, image
gen, TTS, translator). Implementations are swappable.

Game Module Interface The contract a game must implement to run on the
AGORA platform.

Scânteia The anti-runaway scoring mechanic. Last-place player gets
hidden vote multiplier.

Pipeline The sequential AI generation process: Creative Director → Story
LLM → Image Gen → TTS.

Presenter The Tauri 2 desktop window responsible for the cinematic comic
reveal.

Phone Shell The shared Svelte 5 base UI that all AGORA games use for
joining and navigation.

Recognition Moment The moment when a player sees their answer
incorporated into the AI story. The core social loop.

Panel One frame of the comic. A round produces 4--8 panels depending on
the Creative Director's decision.

Archetype The narrative role assigned to a player's answers within the
genre structure.

# 15 Approval & Next Steps

This document is ready for review. Before Milestone 1 begins, the
following must be confirmed:

1.  Architecture approval: AGORA platform design, monorepo structure,
    and component boundaries
2.  Tech stack confirmation: Node.js 22 + Fastify + Socket.IO, Svelte 5,
    Tauri 2, Python orchestrator
3.  AI stack confirmation: Ollama + Llama 3.1 8B, ComfyUI + FLUX.1
    schnell, ElevenLabs TTS (Piper offline fallback)
4.  Creative Director design: genre registry (7 genres), presentation
    formats, brief structure
5.  Prompt system design: category types, assignment strategy, Safe Mode
    requirement
6.  Scoring system: point structure, Scânteia mechanic approved
7.  Provider interface pattern: all AI components behind abstract
    interfaces

READY TO BUILD Once this GDD is approved, development begins at M1:
Platform Skeleton. Estimated first playable prototype: M5 completion
(approximately 4--5 weeks of focused development).

                         CRONICĂ · AGORA Platform · Game Design Document v0.2 · Confidential
