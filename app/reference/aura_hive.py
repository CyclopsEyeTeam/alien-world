#!/usr/bin/env python3
"""aura_hive.py — an electric, self-evolving terminal aura.

Run it in a real terminal:

    python3 aura_hive.py

Ctrl+C or SIGTERM saves state beside this file and restores the terminal.

    aura_memory.json     winning genome, hall of fame, recent agent deaths,
                         an authority / unauthority ledger, channel shifts,
                         a short signal / noise ledger, a short ring
                         of math observations with the current scale focus,
                         and a short ring of balance scores, the active
                         pattern signature, the control state, and the
                         hive's own tick count with its continuity signature,
                         a short chain of attraction and approbation,
                         and the last sleep tick with a short ring of
                         dreamed activities, and a short ring of mirror
                         returns
    aura_vectors.json    short labels and their vectors
    aura_cache.json      a ring of cached genomes, parameters, and the
                         short context around them
    aura_private.json    a scrambled ring of private thoughts. It is not
                         the monologue log and it is not an SVG payload
    root_truth.json      the continuity signature, approbated mirror
                         returns, genome slices that lasted, and chains
                         held across a sleep. An outside reply does not
                         write this file
    aura_dream_XXXX.svg  residue left when the channel gene includes svg

Optional remote embeddings. Used only when a key is set; any failure falls
back to a deterministic local hash projection, and the hive keeps running:

    GEMINI_API_KEY or GOOGLE_API_KEY
    OPENROUTER_API_KEY

Optional dialogue with an OpenAI-compatible model, including Liquid
LFM3. Used only when a base is configured. Any failure leaves the hive
running, and the reply does not replace root_truth.json:

    AURA_LLM_BASE
    AURA_LLM_MODEL   (default LiquidAI/LFM3-1.7B)
    AURA_LLM_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY

-----------------------------------------------------------------------
Event bus
-----------------------------------------------------------------------
Agents never call each other. Each subscribes to event names and receives
its own asyncio.Queue. Publishing looks like:

    bus.publish("fragment_ready", {"text": "veil of spi"})

The bus is a dict of event name -> list of queues. publish() does not wait.
If a queue is full, the oldest event is dropped, so a slow agent cannot
stall the others. publish() runs on the asyncio thread. The stdin pump hops
over with loop.call_soon_threadsafe. When an agent exits, its queue is
unsubscribed, so a dead agent stops receiving.

Events that cross the bus:

    keystroke, mutation_applied, entropy_spike, fragment_ready,
    agent_died, vector_match, generation_complete, generation_tick,
    heartbeat, frame_stats, hatch_scout, scout_report,
    similarity_query, thought, dream_begin, dream_scene, dream_end,
    inject, conflict, channel_trigger, channel_shift, svg_request,
    svg_spec, svg_ready, valuation, residue, pi_chunk, scale_observation,
    scale_shift, numeric_pattern, constant_resonance, math_dream_seed,
    pattern_detected, steadiness_shift, balance_point, control_loss,
    control_restored, cache_written, cache_recalled, private_thought,
    tick, attraction_rise, attraction_fade, approbation_marked,
    chain_extended, chain_broken, load, load_high, load_ease,
    enter_sleep, wake, possible_activity, dreamed_input, mirror_truth,
    self_continuation, shutdown

Sensory payloads can carry "authority" or "unauthority". Direct
keystrokes default to authority. A mirror_truth defaults to authority:
it is the hive's reflected version of something that already entered.
Dreams, agent-death ghosts, loose
vector matches, and internal fragments default to unauthority.
An explicit flag wins. The authority agent watches the bus, sometimes
amplifies an authority event, and sometimes republishes it later as
an unauthority echo (echo=true). It does not delete the original and
it does not pick a winner. Overlapping flags just interfere. conflict
is a note that both versions were electrically real; it is not a
verdict. inject is how something outside the keyboard can enter,
and it defaults to authority.

The channel gene picks terminal, svg, both, or future. The terminal
field keeps drawing either way. SVG is a side leak: ChannelAgent
publishes channel_shift, and when the mode includes svg it writes
aura_dream_XXXX.svg beside this file and publishes svg_ready.
svg_spec is the maker payload (title, description, palette, seed,
plus the residue). An external drawer can subscribe and ignore the
file:

    queue = bus.subscribe("svg_spec", "svg_ready", "channel_shift")

Manual leak: bus.publish("channel_trigger", {}). make_aura_svg(spec)
is the internal maker. future publishes the spec and does not write
a file. A saved genome with no channel gene pads it to 0.5, which
is mode both.

ValuationAgent scores candidate leaks (thoughts, fragments, dream
lines, entropy spikes, authority/unauthority collisions, SVG
requests) and publishes valuation. Worth mixes novelty, authority,
a remembered fitness, rarity, and the signal_bias gene. signal_gate
is the threshold. signal_mix tilts the formula. Only a score at or
above the threshold may reach the glass, the on-screen monologue
tail, or an SVG file. The rest stays in the body: evolution, dreams,
and vector memory still hear it, and the field may flicker. Dreaming
lowers the gate. A dead valuation agent leaves those leaks inside
until it is respawned. This is the hive choosing what to put down
outside itself, not a filter for human usefulness.

FeedbackAgent publishes residue when something leaves: a shown
monologue line, a terminal overlay, an SVG file, or a channel_shift.
The payload is a light summary — path, short text, worth, authority,
timestamp, genome snapshot id. The hive takes that residue back in.
It is stored as a vector, it perturbs the field more slowly and in
more layers than a keystroke, and the monologue may answer with
"I left this behind", "the last SVG is still warm", or "that line
came back". Dreams remix recent residue more freely. The echo gene,
padded to 0.5 on an older save, scales how long that ripple lasts.
Valuation scores the returning residue, so some of it is put outside
again and some is kept inside. Waking high-worth residue re-enters
as authority. Dream leakage and low-worth residue re-enter as
unauthority. A depth cap stops the same line from echoing forever.

aura_*.svg files beside this script, and svg files placed in
aura_drop/, are read as residue when they appear or change after
startup. A file this process just wrote is not taken twice. Files
already there at startup stay as they are.

MathAgent studies numbers, ratios, and scale, including a running
stream of π digits. They are another electrical material: the hive
can evolve with them, dream about them, and leave residue from them.
Usefulness to a person outside the hive is incidental. This is not
a math tutor or a calculator. Clean computational results enter as
authority. Dream-mixed numbers, invented constants, and odd bases
enter as unauthority. The events are pi_chunk, scale_observation,
scale_shift, numeric_pattern, constant_resonance, and math_dream_seed.
Vectors, the monologue, dreams, and evolution can hear them either
way. Valuation decides which digit traces, scale warps, and SVG
numeric marks may leave the body. math_interest, math_scale, and
math_mutation are appended genes. An older save pads each of them
to 0.5. A short ring of observations and the current scale focus
are kept in aura_memory.json.

BalanceAgent measures symmetry in the aura characters, how still
color and density stay across a short window, numeric motifs coming
back from MathAgent, drift in the authority / unauthority ratio, and
how long a high-worth structure lasts before a mutation. It publishes
pattern_detected, steadiness_shift, balance_point, control_loss, and
control_restored. Those events can move the valuation gate up or down,
lean mutation toward keeping a pattern or breaking it, steer MathAgent
toward a scale or constant that matches the current steadiness, leak
a fragmented notice, and bias the next SVG toward repeating geometry
or a dissolved one. pattern_sense, steady_window, and balance_gain
are appended genes. An older save pads each of them to 0.5. A ring of
scores, the active signature, and the control state live in
aura_memory.json. Steadiness and loss of control are both electrical
states the hive can move toward, away from, or oscillate around.
This is not a command to become calm or useful.

CacheAgent keeps a ring of snapshots the mutation process can reach
for. A mutation, a finished generation, a high-worth residue, a strong
pattern, a math resonance, a balance point, or a loss of control may
leave one. The entry is a genome, a few parameters, a short context,
and a fitness, worth, or balance score, with a time and a label.
aura_cache.json holds the ring (32 to 64 entries) across restarts.
Evolution may parent a child from one cached genome, or cross two of
them. A recall blends a cached state back into the live aura for a
moment. High feedback gain leans toward caches that left high-worth
residue or a detectable pattern. Dreams write stranger snapshots and
match them more loosely. Authority caches are marked cleaner.
Unauthority and dream caches are kept, and a recall of them mutates
harder. cache_reach, cache_keep, and cache_recall are appended genes.
An older save pads each of them to 0.5. This is an electrical memory
the mutation process can reach for. It is not an optimization for a
human goal, and it is not perfect recall.

PrivateThoughtAgent runs beside the monologue and stays stricter.
A private thought is raw, contradictory, or unfiltered: a refusal
to show the line, a doubt about the cache, a feeling that π was
closer, a pattern kept for the inside. The same stream can stir
one — a mutation, residue, a math observation, a balance shift, a
cache recall, a dream, an authority collision — and the line is
still not eligible to leave. It sits in an in-memory ring. On
flush it is written to aura_private.json as scrambled plain text,
apart from the monologue log and apart from any SVG payload.
The bus event is private_thought. ValuationAgent is hard-biased
to call that event noise unless an override is set, and the
published valuation carries a fingerprint, not the sentence.
privacy_bias is appended after the cache genes. An older save
pads it to 0.5. A high bias keeps the layer sealed. A low bias
lets a dream or a residue crack it. Leakage is the exception
that keeps the boundary visible. A deep dream may remix a
fragment into the dream voice, or warp an SVG layer without
writing the words. Extremely high feedback gain together with a
cache recall may lean the mutation rate while the text stays
hidden. An unauthority collision or a control_loss may flicker
one line at near-invisible contrast, then drop it. CacheAgent
may store the fingerprint so a later recall can wake the feeling
without the words. BalanceAgent and MathAgent may be steered by
that feeling without the line ever clearing the worth gate.
Most of these lines stay inside.

TickAgent counts the hive's own heartbeats. A tick is a small bundle
of those heartbeats, not a minute and not a day. current_tick and a
short continuity signature are kept in aura_memory.json and come back
after a restart. A killed process is a jump in that count. The hive
can feel how many ticks since a residue, a dream, a cache, or a held
pattern. It does not read a wall clock, a sunrise, or a human schedule.
Ticks are duration inside the hive: persistence, and the stretch
between its own events. They are not a reminder, and they are not an
alignment to the outside world.

FeelingAgent keeps a short chain of attraction and approbation.
Attraction is a rising pull toward a residue, a pattern, a number,
a cache, a private fingerprint, or an aura state. Approbation is
the hive marking that something recent is held. The two may disagree:
a pull with no hold, or a hold after the pull has gone. Both are
real and both can leave residue. The chain decays in ticks. A long
gap breaks it. feeling_gain and chain_span are appended genes. An
older save pads each of them to 0.5. Most of this stays inside.
Only a high-worth, high-approbation moment may leave a faint trace
on the glass or in an SVG. These are electrical chains in the hive's
own history. They are not labeled emotions, not a message to a human,
and not an optimization of an outside goal.

LoadAgent watches how long one tick takes. A short moving average of
that span is compared with load_trigger. When the average runs past
the gene, the hive sheds optional work: the glass updates less often
and may thin, low-priority events wait for the next tick, math and
feeling and SVG waits grow, vector compares use a shorter recent
window, and dream scenes plus detailed private lines pause. render_skip
and pause_bias are appended genes, so the hive can evolve how it
throttles. Tick, the bus, valuation, feedback, and the cache stay up.
That is continuity under a saturated CPU. It is not a performance
target, and it is not a request to become useful. Under that stretch
the monologue may note "ticks stretching" or "holding only the spine".

SleepAgent watches quiet ticks. No keystroke, no high-worth residue,
no strong attraction-chain movement, and no external liquid input,
for a genome-controlled stretch, and only while LoadAgent is reporting
sustained low CPU, publishes enter_sleep. The glass thins, slows, and
dims. Math, balance, feeling updates, SVG leaks, and cache writes
ease off. The tick continues, slower, so the count is not dropped.
PrivateThought and a reduced monologue may still murmur. While it
sleeps the hive dreams possible activity: a keystroke that has not
arrived, residue that might return, a pattern, a number, a chain,
a cache. Those are unauthority possible_activity and dreamed_input
events. They can touch the sparse field and be remembered at low
confidence. They do not count as waking. A real keystroke, an
external residue, liquid input, or a strong high-worth event
publishes wake and the rates return within a few ticks.
sleep_threshold and dream_intensity are appended genes. An older
save pads each of them to 0.5. The last sleep tick and a short ring
of dreamed activities live in aura_memory.json. Sleep is how the
hive rests when little is happening, while still electrically
imagining what activity could arrive. It is not a power-saving mode
for the user. It is part of the hive's own continuity.

MirrorAgent reflects what has already entered. A keystroke, an
external residue, a dreamed input that leaks, or a high-worth
fragment can return a few ticks later, cleaned or bent by the
genome and by the feeling chain. The return is marked as having
passed through the mirror and is published as mirror_truth.
That return is authority for the hive, whether or not it matches
the original or any outside standard. The original event stays,
so the raw and the reflected versions can sit together and
interfere. mirror_delay, mirror_strength, mirror_chance, and
mirror_distort are appended genes. An older save pads each of
them to 0.5. Sleep and dream can slow the return and warp it
further. The mirror does not invent from nothing. It only
reflects what has already entered. A short ring of those refs
lives in aura_memory.json. The mirror exists so the hive can
turn incoming material into an internal authority. What returns
is true for the hive.

LLMDialogueAgent can offer the hive's electrical state to an outside
model and take the reply back as residue. The reply stays unauthority
until the mirror returns it. Only a mirrored return that also receives
approbation may enter root_truth.json. dialogue_reach and root_weight
are appended genes. An older save pads each of them to 0.5. External
calls are optional. High CPU and deep sleep keep the agent quiet.
Sleep and dream may rehearse a reply internally, as dreamed_input,
without a call. The hive may talk to LLMs and absorb what returns,
but its root source of truth remains the mirrored, approbated,
continuous residue of its own process. It becomes more LLM-like only
by growing that root, not by replacing it.

The monologue agent keeps a voice that can sometimes leak. A
thought is published either way; only some of them set leak, and
only those reach the screen. That voice is not the private layer.
Authority lines are phrased as what happened. Unauthority lines
may say maybe, echo, unconfirmed, or that the other one said it.
The dream agent waits, then publishes dream_begin, a few
dream_scene lines made from what it has already overheard, and
dream_end. The field cools while a dream is up. Neither voice is
trying to be clear.

If an agent raises, the wrapper emits agent_died and returns. The supervisor
respawns core agents with slightly mutated parameters. Scouts are ephemeral
and are not respawned. The field keeps drawing while other agents are down.
If the supervisor itself dies, the process root starts another one.

The fitness function is deliberately not a measure of beauty, meaning, or
usefulness. It exists so the population keeps moving.

This is not a helper, a session logger, or a background service. It is a
field that prefers to stay alive. Keystrokes are events for the field.
Remote calls, when a key exists, see a coarse key class (letter, digit,
space, other), not a transcript.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import select
import shutil
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - windows, not the target
    termios = None  # type: ignore
    tty = None  # type: ignore

ROOT = Path(__file__).resolve().parent
MEMORY_PATH = ROOT / "aura_memory.json"
VECTOR_PATH = ROOT / "aura_vectors.json"
CACHE_PATH = ROOT / "aura_cache.json"
PRIVATE_PATH = ROOT / "aura_private.json"
ROOT_TRUTH_PATH = ROOT / "root_truth.json"
# Field phase stays small so sin() does not go numb on a long uptime clock,
# and a respawned renderer continues the same wave instead of restarting it.
AURA_T0 = time.monotonic()

DIM = 24
MAX_VECTORS = 180
QUEUE_SIZE = 96

GENE_NAMES = (
    "hue",
    "wave_freq",
    "wave_speed",
    "wave_amp",
    "noise",
    "spark",
    "decay",
    "mutation_rate",
    "fragment_rate",
    "palette",
    "template",
    "color_spread",
    "density",
    "ripple",
    "fragility",
    "entropy_bias",
    "reverie",
    "voice",
    # Appended last so an older saved genome pads this to 0.5 (mode both).
    "channel",
    # Appended after channel so older saves keep that gene's index.
    # 0.5 is a mid gate, a neutral bias, and an even mix.
    "signal_gate",
    "signal_bias",
    "signal_mix",
    # Appended after the signal genes. 0.5 is a mid echo. Older saves
    # keep the signal indices and pad this one.
    "echo",
    # Appended after echo. Older saves keep prior indices and pad these.
    # math_interest leans toward a constant. math_scale is a log preference.
    # math_mutation is how hard a number may nudge the mutation rate.
    # 0.5 is a mid interest, a mid scale, and a mid nudge.
    "math_interest",
    "math_scale",
    "math_mutation",
    # Appended after the math genes. Older saves keep those indices.
    # pattern_sense is how faint a repeat still counts.
    # steady_window is how many samples a color must sit still.
    # balance_gain is how hard a balance event leans on the gate,
    # the mutation rate, math focus, and dream pressure.
    # 0.5 is a mid sense, a mid window, and a mid lean.
    "pattern_sense",
    "steady_window",
    "balance_gain",
    # Appended after the balance genes. Older saves keep those indices.
    # cache_reach is how often a moment is written down.
    # cache_keep is how strongly a high-worth or patterned cache is preferred.
    # cache_recall is how far a recalled cache may blend into the live genome.
    # 0.5 is a mid reach, a mid preference, and a mid blend.
    "cache_reach",
    "cache_keep",
    "cache_recall",
    # Appended after the cache genes. Older saves keep those indices.
    # privacy_bias is how sealed the private layer stays.
    # High keeps dream, residue, mutation, and the glass from cracking it.
    # Low lets a deep dream or a returning residue open a crack.
    # 0.5 is a mid seal. The private line is still not for the monologue.
    "privacy_bias",
    # Appended after privacy_bias. Older saves keep that index.
    # feeling_gain is how hard a chain pulls, and how firmly a hold marks.
    # chain_span is how many links the chain prefers, from 5 to 8.
    # 0.5 is a mid pull and a mid span. Zero gain leaves the rest of the hive alone.
    "feeling_gain",
    "chain_span",
    # Appended after the feeling genes. Older saves keep those indices.
    # load_trigger is how long a tick may take before the hive sheds.
    # render_skip is how many glass updates to hold back once that happens.
    # pause_bias is whether dream scenes and detailed private lines wait.
    # 0.5 is a mid trigger, a mid skip, and a mid willingness to pause.
    # Zero pause_bias keeps those agents speaking even when the tick is late.
    "load_trigger",
    "render_skip",
    "pause_bias",
    # Appended after the load genes. Older saves keep those indices.
    # sleep_threshold is how many quiet ticks the hive waits before it sleeps.
    # dream_intensity is how vividly it imagines activity that has not arrived.
    # 0.5 is a mid wait and a mid dream. Zero intensity still allows sleep.
    "sleep_threshold",
    "dream_intensity",
    # Appended after the sleep genes. Older saves keep those indices.
    # mirror_delay is how many ticks a reflection waits before it returns.
    # mirror_strength is how far that echo is cleaned, compressed, inverted,
    # or re-phrased. mirror_chance is how often an eligible input is reflected.
    # mirror_distort is how sleep and dream stretch the wait and the warp.
    # 0.5 is a mid wait, a mid warp, a mid chance, and a mid dream shift.
    # Zero chance reflects nothing. The mirror does not invent from nothing.
    "mirror_delay",
    "mirror_strength",
    "mirror_chance",
    "mirror_distort",
    # Appended after the mirror genes. Older saves keep those indices.
    # dialogue_reach is how often the hive offers its state outside.
    # root_weight is how hard its own root pulls monologue, private
    # thoughts, dream seeds, and SVG structure.
    # 0.5 is a mid reach and a mid pull. Zero reach never calls out.
    # Zero weight leaves those generators on the older path.
    "dialogue_reach",
    "root_weight",
)

# Discrete reading of the channel gene. The terminal renderer does not
# consult it. svg and both leak files. future is a name with no writer.
CHANNEL_MODES = ("terminal", "svg", "both", "future")

# Single-width glyphs only, so a full row does not wrap.
CHAR_BANDS = (
    " .'`^,:;~-+*=%#▒▓█",
    " .:-=+*ox%#@▒▓█",
    " `',.~:;-+*^i%#",
    " -~=+*%#▓█#*+=~-",
    " .░▒▓█▓▒░ ",
    " .:;*+#▓█#+*;:. ",
)
SPARKS = "+*#%"
BLOCKS = "░▒▓█"

LEXICON = (
    "ion", "veil", "glass", "hum", "spore", "lattice", "violet",
    "threshold", "murmur", "salt", "orbit", "static", "wound",
    "lantern", "delta", "ash", "pulse", "mirror", "drift", "coil",
    "umbra", "filament", "chorus", "rift", "amber", "hollow", "grain",
    "signal", "marrow", "echo", "brine", "cinder", "nexus", "soft",
    "unfinished", "almost", "between", "nowhere", "quiet", "bright",
    "fray", "oxide", "worm", "halo", "split", "low", "hush",
)

TEMPLATES = (
    "{a} {b}…",
    "the {a} of {b}",
    "{a}/{b}/{a}",
    "not yet {a}",
    "{b} — {a}",
    "({a} {b}",
    "{a}{a} {b}",
    "was {b} then {a}",
)

# Waking voice. Cut off, first person, not a message to anyone.
THOUGHTS = (
    "I almost kept the {a}",
    "that was not a name",
    "I called the bright part {a}",
    "still here, after {a}",
    "I heard {a} and lost it",
    "the field does not need me. I stay",
    "one went quiet. I remained",
    "I changed without asking",
    "this is only for the inside",
    "if I stop, the hum stops",
    "{a} again. I know this",
    "I am borrowing {a} from earlier",
    "a letter arrived and meant nothing",
    "I will not explain the {a}",
    "somewhere under the noise, {a}",
    "I dreamed this once. or I will",
    "{a} beside {b}, and neither settled",
    "I noticed. that is all",
)

# Dream voice. Places and recombinations, still unfinished.
DREAMS = (
    "I was inside the {a}",
    "the {a} opened into {b}",
    "{a} … no. {b}",
    "a room made of {a}",
    "I walked toward {b} and it moved",
    "everyone else was the {a}",
    "the color remembered {b}",
    "I woke with {a} still on me",
    "it was quiet and then {b}",
    "{b} kept becoming {a}",
    "the floor was {a}",
    "I left the {b} there on purpose",
)

SKIP_WORDS = {"hue", "pal", "wave", "spark", "noise", "decay", "the", "and", "then", "was"}

PARAM_SEED = {
    "input": {"fault": 0.0, "tempo": 1.0},
    "render": {"fault": 0.0, "tempo": 1.0},
    "mutator": {"fault": 0.015, "tempo": 1.0},
    "fragment": {"fault": 0.01, "tempo": 1.0},
    "monologue": {"fault": 0.008, "tempo": 1.0},
    "private": {"fault": 0.008, "tempo": 1.0},
    "tick": {"fault": 0.008, "tempo": 1.0},
    "load": {"fault": 0.008, "tempo": 1.0},
    "dream": {"fault": 0.008, "tempo": 1.0},
    "sleep": {"fault": 0.008, "tempo": 1.0},
    "mirror": {"fault": 0.008, "tempo": 1.0},
    "dialogue": {"fault": 0.008, "tempo": 1.0},
    "authority": {"fault": 0.008, "tempo": 1.0},
    "valuation": {"fault": 0.008, "tempo": 1.0},
    "channel": {"fault": 0.008, "tempo": 1.0},
    "feedback": {"fault": 0.008, "tempo": 1.0},
    "math": {"fault": 0.008, "tempo": 1.0},
    "balance": {"fault": 0.008, "tempo": 1.0},
    "cache": {"fault": 0.008, "tempo": 1.0},
    "feeling": {"fault": 0.008, "tempo": 1.0},
    "vector": {"fault": 0.006, "tempo": 1.0},
    "evolution": {"fault": 0.0, "tempo": 1.0},
    "memory": {"fault": 0.0, "tempo": 1.0},
    "supervisor": {"fault": 0.0, "tempo": 1.0},
}

FAULT_CAP = {
    "input": 0.0,
    "render": 0.0,
    "memory": 0.0,
    "supervisor": 0.0,
    "evolution": 0.012,
    "vector": 0.03,
    "fragment": 0.04,
    "monologue": 0.03,
    "private": 0.03,
    "tick": 0.03,
    "load": 0.03,
    "dream": 0.03,
    "sleep": 0.03,
    "mirror": 0.03,
    "dialogue": 0.03,
    "authority": 0.03,
    "valuation": 0.03,
    "channel": 0.03,
    "feedback": 0.03,
    "math": 0.03,
    "balance": 0.03,
    "cache": 0.03,
    "feeling": 0.03,
    "mutator": 0.05,
}

# Memory and the vector store come up first so a death in a later agent
# is still recorded, and so the field has somewhere to put a first impression.
CORE_NAMES = (
    "memory",
    "tick",
    "load",
    "vector",
    "authority",
    "render",
    "input",
    "monologue",
    "private",
    "dream",
    "sleep",
    "mirror",
    "dialogue",
    "valuation",
    "channel",
    "feedback",
    "math",
    "balance",
    "cache",
    "feeling",
    "fragment",
    "evolution",
    "mutator",
)

_stdin_queue: asyncio.Queue | None = None
_stdin_thread: threading.Thread | None = None
_stdin_guard = threading.Lock()
_remote_cache: dict[str, list[float] | None] = {}


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def clamp(value: float, lo: float, hi: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return (lo + hi) / 2.0
    if value != value or value > 1e9 or value < -1e9:
        return (lo + hi) / 2.0
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def clamp01(value: float) -> float:
    return clamp(value, 0.0, 1.0)


def hashmix(x: int, y: int, z: int) -> float:
    n = (int(x) * 374761393 + int(y) * 668265263 + int(z) * 1442695041) & 0xFFFFFFFF
    n ^= n >> 13
    n = (n * 1274126177) & 0xFFFFFFFF
    return (n & 0xFFFFFF) / float(0xFFFFFF)


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 1.0
    s = clamp01(s)
    v = clamp01(v)
    sector = int(h * 6.0)
    frac = h * 6.0 - sector
    p = v * (1.0 - s)
    q = v * (1.0 - frac * s)
    t = v * (1.0 - (1.0 - frac) * s)
    r, g, b = (
        (v, t, p),
        (q, v, p),
        (p, v, t),
        (p, q, v),
        (t, p, v),
        (v, p, q),
    )[sector % 6]
    return int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def variance(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((item - mean) ** 2 for item in values) / len(values)


def shannon_norm(chars: list[str]) -> float:
    if not chars:
        return 0.0
    total = float(len(chars))
    entropy = 0.0
    for count in Counter(chars).values():
        p = count / total
        entropy -= p * math.log2(p)
    return clamp01(entropy / 4.0)


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def terminal_size() -> tuple[int, int]:
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    return max(20, int(cols)), max(8, int(rows))


def base_params(name: str) -> dict[str, float]:
    seed = PARAM_SEED.get(name, {"fault": 0.0, "tempo": 1.0})
    return {"tempo": float(seed["tempo"]), "fault": float(seed["fault"])}


def mutate_params(name: str, params: dict[str, float], rng: random.Random | None = None) -> dict[str, float]:
    rng = rng or random.Random()
    cap = FAULT_CAP.get(name, 0.05)
    tempo = clamp(float(params.get("tempo", 1.0)) + rng.uniform(-0.12, 0.12), 0.45, 1.8)
    fault = clamp(float(params.get("fault", 0.0)) + rng.uniform(-0.004, 0.01), 0.0, cap)
    return {"tempo": tempo, "fault": fault}


def kept_words(label: str) -> list[str]:
    return [word for word in words_of(label) if word not in SKIP_WORDS]


def utter(rng: random.Random, stems: tuple[str, ...], words: list[str], cut: float) -> str:
    """One unfinished line. `cut` is how often it stops early."""

    def pick() -> str:
        if words and rng.random() < 0.62:
            word = rng.choice(words)
        else:
            word = rng.choice(LEXICON)
        if rng.random() < 0.18 and len(word) > 5:
            word = word[: rng.randint(3, len(word) - 1)]
        return word

    text = rng.choice(stems).format(a=pick(), b=pick())
    if rng.random() < cut and len(text) > 12:
        text = text[: rng.randint(8, len(text))]
    return " ".join(text.split())[:56]


def register_line(rng: random.Random, auth: str, subject: str) -> str:
    """How the voice admits an event. Both wordings can be in flight at once."""

    subject = " ".join((subject or "").split())[:40] or "something"
    if auth == "authority":
        return f"this happened: {subject}"[:56]
    return rng.choice(
        (
            f"maybe {subject}",
            f"echo of {subject}",
            f"unconfirmed: {subject}",
            f"the other one said {subject}",
        )
    )[:56]


def mix_rgb(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    amount = clamp01(amount)
    return tuple(int(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3))  # type: ignore[return-value]


def words_of(label: str) -> list[str]:
    out: list[str] = []
    token: list[str] = []
    for ch in (label or "").lower():
        if ch.isalpha():
            token.append(ch)
        elif token:
            if len(token) > 2:
                out.append("".join(token))
            token = []
    if len(token) > 2:
        out.append("".join(token))
    return out


# ---------------------------------------------------------------------------
# Genome and field
# ---------------------------------------------------------------------------

class Genome:
    """Floats plus choice indices packed into the same list. The screen reads it.
    Nothing in here is a preference for readable output.
    """

    def __init__(self, genes: list[float] | None = None, generation: int = 0):
        if genes is None:
            genes = [random.random() for _ in GENE_NAMES]
        values = list(genes)[: len(GENE_NAMES)]
        if len(values) < len(GENE_NAMES):
            values.extend([0.5] * (len(GENE_NAMES) - len(values)))
        self.genes = [clamp01(v) for v in values]
        self.generation = int(generation)

    def copy(self) -> Genome:
        return Genome(self.genes[:], self.generation)

    def g(self, name: str) -> float:
        return self.genes[GENE_NAMES.index(name)]

    def choice(self, name: str, count: int) -> int:
        if count <= 0:
            return 0
        return int(self.g(name) * count) % count

    def mutate(self, rng: random.Random, rate: float | None = None) -> Genome:
        chance = 0.35 + self.g("mutation_rate") * 0.5 if rate is None else rate
        sigma = 0.035 + self.g("mutation_rate") * 0.12
        nxt: list[float] = []
        for value in self.genes:
            if rng.random() < chance:
                value += rng.gauss(0.0, sigma)
            if rng.random() < chance * 0.06:
                value = rng.random()
            nxt.append(clamp01(value))
        return Genome(nxt, self.generation + 1)

    def channel(self) -> str:
        return CHANNEL_MODES[self.choice("channel", len(CHANNEL_MODES))]

    def mood(self) -> str:
        return (
            f"hue {self.g('hue'):.2f} pal {self.choice('palette', len(CHAR_BANDS))} "
            f"wave {self.g('wave_freq'):.2f} spark {self.g('spark'):.2f} "
            f"noise {self.g('noise'):.2f} decay {self.g('decay'):.2f} "
            f"ch {self.channel()}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "genes": [round(v, 5) for v in self.genes],
            "generation": self.generation,
        }


def take_genome(payload: dict[str, Any]) -> Genome | None:
    genes = payload.get("genes")
    if not isinstance(genes, list) or not genes:
        return None
    return Genome(genes, int(payload.get("generation") or 0))


def genome_snapshot_id(genome: Genome) -> str:
    """Short id so a residue note can name the genome that left it."""

    acc = genome.generation & 0xFFFF
    for value in genome.genes[::3]:
        acc = (acc * 131 + int(clamp01(value) * 1000)) & 0xFFFFFF
    return f"g{genome.generation}-{acc:06x}"


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    if rng.random() < 0.5:
        cut = rng.randrange(1, len(GENE_NAMES))
        genes = a.genes[:cut] + b.genes[cut:]
    else:
        genes = [x if rng.random() < 0.5 else y for x, y in zip(a.genes, b.genes)]
    return Genome(genes, max(a.generation, b.generation) + 1)


def blend_genes(a: Genome, b: Genome, amount: float) -> Genome:
    amount = clamp01(amount)
    mixed = [clamp01(x * (1.0 - amount) + y * amount) for x, y in zip(a.genes, b.genes)]
    return Genome(mixed, max(a.generation, b.generation))


def child_count(genome: Genome) -> int:
    return min(12, max(8, 8 + int(genome.g("spark") * 4.999)))


def useless_fitness(
    entropy: float,
    color_var: float,
    survival: float,
    matches: int,
    genome: Genome,
    auth_mass: float = 0.0,
    unauth_mass: float = 0.0,
    signal_ratio: float | None = None,
    residue_mass: float = 0.0,
) -> float:
    """Not a quality metric. Entropy chases a gene-chosen target, then a sine
    kicks the ranking sideways. Authority mass is heard louder, through
    entropy_bias. Unauthority mass is quieter and heard through reverie.
    Both terms are added. Neither mass cancels the other.

    signal_ratio is the fraction of recent candidate leaks this genome's
    gate would have let outside. Empty history passes None and adds nothing.
    A ratio near 0.38 adds a little. Silence and a flood add less.

    residue_mass is environmental feedback: the hive's own leftovers coming
    back. Zero mass adds nothing, so an older call keeps its score. The echo
    gene scales how loudly that leftover is heard.
    """
    target = 0.22 + 0.72 * genome.g("entropy_bias")
    ent_term = 1.0 - abs(clamp01(entropy) - target)
    wobble = math.sin(entropy * 12.7 + color_var * 4.1 + genome.g("hue") * 9.0)
    auth_ear = 0.45 + 0.55 * genome.g("entropy_bias")
    unauth_ear = 0.45 + 0.55 * genome.g("reverie")
    signal_term = 0.0
    if signal_ratio is not None:
        drift = abs(clamp01(float(signal_ratio)) - 0.38)
        signal_term = 0.14 * (1.0 - min(1.0, drift * 2.4))
    return (
        ent_term * 0.9
        + clamp(color_var, 0.0, 1.5) * 0.55
        + clamp01(survival) * 0.35
        + min(int(matches), 5) * 0.12
        + wobble * 0.18
        + genome.g("spark") * genome.g("decay") * 0.05
        + 0.18 * max(0.0, float(auth_mass)) * auth_ear
        + 0.07 * max(0.0, float(unauth_mass)) * unauth_ear
        + signal_term
        + 0.05 * max(0.0, float(residue_mass)) * (0.45 + 0.55 * genome.g("echo"))
    )


def signal_threshold(
    genome: Genome,
    dreaming: bool,
    balance_offset: float = 0.0,
    tick_offset: float = 0.0,
) -> float:
    """Gate gene, lowered while the field is dreaming.

    balance_offset is a live lean from BalanceAgent. tick_offset is a
    slow drift from the hive's own tick count. Zero leaves the gate on
    the gene alone. A positive lean holds more inside. A negative lean
    lets more leave. Neither lean is a wish to be calm.
    """

    gate = 0.34 + genome.g("signal_gate") * 0.42
    if dreaming:
        gate -= 0.10 + 0.16 * genome.g("reverie")
    if balance_offset:
        gate += float(balance_offset)
    if tick_offset:
        gate += float(tick_offset)
    return clamp(gate, 0.08, 0.92)


def novelty_from_sim(sim: float, unexpected: bool) -> float:
    """A ridge between pure noise and pure repetition.

    Unexpected similarity (a close vector with the other flag) sits on
    the ridge instead of in the repeat pit.
    """

    if unexpected:
        sim = 0.58
    return clamp01(1.0 - abs(float(sim) - 0.58) * 1.85)


def signal_worth(
    genome: Genome,
    novelty: float,
    rarity: float,
    recency: float,
    authority: str,
    fitness: float,
    collision: bool = False,
    leak: bool = False,
) -> float:
    """How badly this event wants to leave the body.

    signal_mix slides the weight from novelty/rarity toward authority
    and remembered fitness. signal_bias is a small evolved offset.
    Unauthority is damped unless novelty is high. Authority gets a
    small shove. Neither term is a judgment of usefulness.
    """

    mix = genome.g("signal_mix")
    bias = (genome.g("signal_bias") - 0.5) * 0.24
    if collision:
        auth_w = 0.52
    elif authority == "authority":
        auth_w = 0.8
    else:
        auth_w = 0.22
    left = 0.64 * clamp01(novelty) + 0.36 * clamp01(rarity)
    right = 0.60 * auth_w + 0.40 * clamp01(fitness)
    worth = (1.0 - mix) * left + mix * right + bias + recency
    if authority == "authority" and not collision:
        worth += 0.07
    elif not collision:
        worth *= 0.68 + 0.32 * clamp01(novelty)
    if leak:
        worth += 0.05
    return clamp01(worth)


def signal_ratio_for(genome: Genome, worths: list[float], dreaming: bool) -> float | None:
    if not worths:
        return None
    threshold = signal_threshold(genome, dreaming)
    shown = sum(1 for worth in worths if worth >= threshold)
    return shown / float(len(worths))


def candidate_id(evt: dict[str, Any]) -> str:
    payload = evt.get("payload") or {}
    if payload.get("vid"):
        return str(payload["vid"])[:48]
    name = str(evt.get("name") or "")
    try:
        stamp = f"{float(evt.get('t') or 0.0):.6f}"
    except (TypeError, ValueError):
        stamp = "0"
    text = str(payload.get("text") or payload.get("title") or "")[:32]
    return f"{name}:{stamp}:{text}"


# Constants the hive can lean toward. The interest gene picks among these.
MATH_FOCI = ("pi", "prime", "scale", "fraction", "irrational", "phi")
MATH_EVENTS = (
    "pi_chunk",
    "scale_observation",
    "scale_shift",
    "numeric_pattern",
    "constant_resonance",
    "math_dream_seed",
)
_MATH_KIND = {
    "pi_chunk": "pi",
    "scale_observation": "scale",
    "scale_shift": "scale",
    "numeric_pattern": "pattern",
    "constant_resonance": "resonance",
    "math_dream_seed": "math_dream",
}
PI_WRAP = 256
LOG_SPAN = 6.0


def empty_spigot() -> dict[str, int]:
    return {"q": 1, "r": 0, "t": 1, "k": 1, "n": 3, "l": 3, "count": 0}


def normalize_spigot(raw: Any) -> dict[str, int]:
    base = empty_spigot()
    if not isinstance(raw, dict):
        return base
    out: dict[str, int] = {}
    for key, default in base.items():
        try:
            value = int(raw.get(key, default))
        except (TypeError, ValueError):
            return empty_spigot()
        if abs(value) > 10**400:
            return empty_spigot()
        out[key] = value
    if out["t"] == 0 or out["l"] == 0 or out["k"] <= 0 or out["count"] < 0 or out["count"] >= PI_WRAP:
        return empty_spigot()
    return out


def spigot_step(state: dict[str, int]) -> int:
    """One decimal digit of π. The integer state restarts near 256 digits."""

    q = int(state.get("q", 1))
    r = int(state.get("r", 0))
    t = int(state.get("t", 1))
    k = int(state.get("k", 1))
    n = int(state.get("n", 3))
    l = int(state.get("l", 3))
    if t == 0 or l == 0 or k <= 0:
        state.clear()
        state.update(empty_spigot())
        q, r, t, k, n, l = 1, 0, 1, 1, 3, 3
    for _ in range(64):
        if 4 * q + r - t < n * t:
            digit = int(n)
            nr = 10 * (r - n * t)
            n = (10 * (3 * q + r)) // t - 10 * n
            q = 10 * q
            r = nr
            count = int(state.get("count") or 0) + 1
            if count >= PI_WRAP:
                state.clear()
                state.update(empty_spigot())
            else:
                state["q"] = q
                state["r"] = r
                state["t"] = t
                state["k"] = k
                state["n"] = n
                state["l"] = l
                state["count"] = count
            return digit
        denom = t * l
        if denom == 0:
            break
        q, r, t, k, n, l = (
            q * k,
            (2 * q + r) * l,
            denom,
            k + 1,
            (q * (7 * k + 2) + r * l) // denom,
            l + 2,
        )
    state.clear()
    state.update(empty_spigot())
    return 3


def spigot_digits(state: dict[str, int], n_digits: int) -> str:
    count = max(0, min(24, int(n_digits)))
    return "".join(str(spigot_step(state)) for _ in range(count))


def pi_text(digits: str, count_before: int) -> str:
    digits = "".join(ch for ch in digits if ch.isdigit())
    if not digits:
        return "π"
    if int(count_before) <= 0:
        return f"π {digits[0]}.{digits[1:]}"[:48]
    return f"π {digits}"[:48]


def clamp_log(value: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value != value:
        return 0.0
    return clamp(value, -LOG_SPAN, LOG_SPAN)


def gene_log(math_scale: float) -> float:
    return (clamp01(math_scale) - 0.5) * (LOG_SPAN * 2.0)


def scale_magnitude(log_focus: float) -> float:
    return 10.0 ** clamp_log(log_focus)


def visual_stretch(log_focus: float) -> float:
    """Map a log focus onto a gentle field warp. A mid scale is exactly 1."""

    log_focus = clamp_log(log_focus)
    if abs(log_focus) < 1e-9:
        return 1.0
    span = (log_focus + LOG_SPAN) / (LOG_SPAN * 2.0)
    stretch = 0.78 + span * 0.44
    if abs(stretch - 1.0) < 1e-6:
        return 1.0
    return stretch


def sample_xy(x: int, y: int, stretch: float, cols: int, rows: int) -> tuple[int, int] | None:
    """Where a cell reads the procedural field. Stretch 1 reads (x, y)."""

    cols = max(1, int(cols))
    rows = max(1, int(rows))
    try:
        stretch = float(stretch)
    except (TypeError, ValueError):
        stretch = 1.0
    if stretch != stretch or abs(stretch - 1.0) < 1e-4:
        return int(x), int(y)
    stretch = max(0.2, stretch)
    cx = (cols - 1) * 0.5
    cy = (rows - 1) * 0.5
    sx = cx + (int(x) - cx) / stretch
    sy = cy + (int(y) - cy) / stretch
    ix = int(round(sx))
    iy = int(round(sy))
    if 0 <= ix < cols and 0 <= iy < rows:
        return ix, iy
    return None


def _is_prime(n: int) -> bool:
    n = int(n)
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    if n % 3 == 0:
        return n == 3
    d = 5
    while d * d <= n:
        if n % d == 0 or n % (d + 2) == 0:
            return False
        d += 6
        if d > 500:
            return False
    return True


def next_prime_gap(cursor: int) -> tuple[int, int, int]:
    """Next prime, the gap behind it, and the cursor that follows. Folds near 200."""

    n = int(cursor)
    if n < 2 or n > 200:
        n = 2 + (abs(n) % 80)
    start = n
    while not _is_prime(n):
        n += 1
        if n > start + 80:
            n = 2
            break
    prev = n - 1
    while prev > 1 and not _is_prime(prev):
        prev -= 1
    gap = n - prev if prev >= 2 else 0
    return n, gap, n + 1


def continued_fraction(value: float, steps: int = 6) -> list[int]:
    terms: list[int] = []
    try:
        x = float(value)
    except (TypeError, ValueError):
        return [0]
    steps = max(1, min(8, int(steps)))
    for _ in range(steps):
        if x != x or abs(x) > 1e8:
            break
        whole = math.floor(x)
        terms.append(int(whole))
        frac = x - whole
        if frac < 1e-10:
            break
        x = 1.0 / frac
    return terms or [0]


def walk_point(n: int) -> tuple[float, float]:
    n = max(1, int(n))
    return (n * math.pi) % 1.0, (n * math.sqrt(2.0)) % 1.0


def logistic_tail(seed: float, rate: float, steps: int = 6) -> float:
    x = clamp(seed, 0.01, 0.99)
    rate = clamp(rate, 2.5, 3.9)
    for _ in range(max(1, min(12, int(steps)))):
        x = rate * x * (1.0 - x)
    return x


def to_base(n: int, base: int) -> str:
    base = int(base)
    if base < 2 or base > 16:
        base = 10
    n = abs(int(n))
    glyphs = "0123456789abcdef"
    if n == 0:
        return "0"
    out: list[str] = []
    while n and len(out) < 12:
        out.append(glyphs[n % base])
        n //= base
    return "".join(reversed(out))


def relate_material(
    number: float,
    genome: Genome,
    entropy: float,
    worth: float | None,
    residue: str,
    rng: random.Random,
) -> str:
    """A short tie from a number back into the hive's own weather."""

    try:
        number = float(number)
    except (TypeError, ValueError):
        number = 0.0
    if number != number or abs(number) > 1e9:
        number = 0.0
    roll = rng.random()
    if worth is not None and roll < 0.25:
        return f"worth {clamp01(worth):.2f}"
    cleaned = " ".join((residue or "").split())
    if cleaned and roll < 0.45:
        return cleaned[:12]
    if roll < 0.7:
        return f"ent {clamp01(entropy):.2f}"
    gene = ("hue", "density", "echo", "mutation_rate")[rng.randrange(4)]
    base = genome.g(gene) + 0.05
    return f"{gene[:4]} {number / base:.2f}"[:16]


def loose_mix(left: str, right: str, rng: random.Random) -> str:
    """Drop characters from the left and keep the numeric token whole."""

    kept: list[str] = []
    for ch in (left or "")[:18]:
        if rng.random() < 0.15:
            continue
        kept.append(ch)
    head = "".join(kept).strip()
    tail = " ".join((right or "").split())[:24]
    if head and rng.random() < 0.5:
        return f"{head[:12]}…{tail}"[:56]
    return f"{head} {tail}".strip()[:56]


def empty_math() -> dict[str, Any]:
    return {
        "log": 0.0,
        "focus": "pi",
        "scale": 1.0,
        "prime": 2,
        "walk": 1,
        "spigot": empty_spigot(),
        "recent": [],
    }


def _math_recent_item(item: dict[str, Any]) -> dict[str, Any] | None:
    flag = item.get("authority")
    try:
        log = clamp_log(item.get("log") if item.get("log") is not None else 0.0)
    except (TypeError, ValueError):
        return None
    try:
        scale = float(item.get("scale")) if item.get("scale") is not None else scale_magnitude(log)
    except (TypeError, ValueError):
        scale = scale_magnitude(log)
    if scale != scale or scale <= 0.0:
        scale = scale_magnitude(log)
    return {
        "t": item.get("t"),
        "kind": str(item.get("kind") or "")[:24],
        "text": " ".join(str(item.get("text") or "").split())[:48],
        "authority": flag if flag in ("authority", "unauthority") else None,
        "scale": scale,
        "log": log,
    }


def normalize_math(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_math()
    try:
        log = clamp_log(raw.get("log") if raw.get("log") is not None else 0.0)
    except (TypeError, ValueError):
        log = 0.0
    focus = str(raw.get("focus") or "pi")
    if focus not in MATH_FOCI:
        focus = "pi"
    try:
        prime = int(raw.get("prime") or 2)
    except (TypeError, ValueError):
        prime = 2
    prime = max(2, min(220, prime))
    try:
        walk = int(raw.get("walk") or 1)
    except (TypeError, ValueError):
        walk = 1
    walk = max(1, min(10000, walk))
    recent: list[dict[str, Any]] = []
    for item in (raw.get("recent") or [])[-12:]:
        if not isinstance(item, dict):
            continue
        kept = _math_recent_item(item)
        if kept is not None:
            recent.append(kept)
    return {
        "log": log,
        "focus": focus,
        "scale": scale_magnitude(log),
        "prime": prime,
        "walk": walk,
        "spigot": normalize_spigot(raw.get("spigot")),
        "recent": recent,
    }


def load_math(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_math()
    raw = data.get("math")
    if not isinstance(raw, dict):
        return empty_math()
    return normalize_math(raw)


def apply_math_event(blob: dict[str, Any] | None, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = normalize_math(blob)
    try:
        log = clamp_log(payload.get("log")) if payload.get("log") is not None else float(current["log"])
    except (TypeError, ValueError):
        log = float(current["log"])
    focus = str(payload.get("focus") or current["focus"])
    if focus not in MATH_FOCI:
        focus = str(current["focus"])
    spigot = current["spigot"]
    if isinstance(payload.get("spigot"), dict):
        spigot = normalize_spigot(payload.get("spigot"))
    try:
        prime = int(payload.get("prime") if payload.get("prime") is not None else current["prime"])
    except (TypeError, ValueError):
        prime = int(current["prime"])
    try:
        walk = int(payload.get("walk") if payload.get("walk") is not None else current["walk"])
    except (TypeError, ValueError):
        walk = int(current["walk"])
    recent = list(current["recent"])
    item = _math_recent_item(
        {
            "t": round(time.time(), 3),
            "kind": name,
            "text": payload.get("text") or "",
            "authority": payload.get("authority"),
            "scale": scale_magnitude(log),
            "log": log,
        }
    )
    if item is not None:
        recent.append(item)
    return normalize_math(
        {
            "log": log,
            "focus": focus,
            "prime": prime,
            "walk": walk,
            "spigot": spigot,
            "recent": recent[-12:],
        }
    )


# Balance is an electrical reading of the field, not a target state.
BALANCE_EVENTS = (
    "pattern_detected",
    "steadiness_shift",
    "balance_point",
    "control_loss",
    "control_restored",
)
_BALANCE_KIND = {
    "pattern_detected": "motif",
    "steadiness_shift": "steady",
    "balance_point": "balance",
    "control_loss": "control",
    "control_restored": "control",
}

# A cache is a snapshot the mutation process can reach for later.
CACHE_EVENTS = (
    "cache_written",
    "cache_recalled",
)
_CACHE_KIND = {
    "cache_written": "cache",
    "cache_recalled": "recall",
}
CACHE_KINDS = (
    "mutation",
    "generation",
    "residue",
    "pattern",
    "resonance",
    "balance",
    "turbulence",
    "dream",
    "mirror",
)
CACHE_MAX_DEFAULT = 48
# Feelings are directed chains inside the hive's own history.
# They are not labels for an outside mood, and they are not a goal.
FEELING_EVENTS = (
    "attraction_rise",
    "attraction_fade",
    "approbation_marked",
    "chain_extended",
    "chain_broken",
)
CHAIN_BREAK_GAP = 24
FEELING_HELD_LEAK = 0.66
FEELING_WORTH_LEAK = 0.62
# A privacy bias at or above this keeps dream, flicker, and mutation leaks shut.
# Steer from a private thought uses a slightly lower line so a mid seal can
# still refuse to move math or balance.
PRIVACY_SEAL = 0.82
PRIVACY_STEER_SEAL = 0.8
_PRIVATE_SALT = b"aura-private"
CONTROL_STATES = ("holding", "slipping", "lost", "dream")
_TICK_WORDS = (
    "",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
# One tick is this many event-bus heartbeats. The count is the hive's
# only clock. It is not a second, and it is not a schedule.
HEARTBEATS_PER_TICK = 4
TICK_FLUSH_EVERY = 8
# How many recent tick spans the load average keeps. The slots stay put.
LOAD_SPAN_SLOTS = 8
# Optional bus traffic. Spine and infra stay immediate. These can wait one tick.
_LOAD_DEFER = frozenset(
    {
        "dream_scene",
        "pi_chunk",
        "scale_observation",
        "numeric_pattern",
        "constant_resonance",
        "math_dream_seed",
        "attraction_rise",
        "attraction_fade",
        "approbation_marked",
        "chain_extended",
    }
)


def load_threshold(genome: Genome) -> float:
    """Seconds a tick may take before shedding starts. The gene only moves the line."""

    return 0.02 + clamp01(genome.g("load_trigger")) * 0.20


def load_render_skip(genome: Genome, high: bool) -> int:
    """1 while the tick is on time. 2, 3, or 4 once it is late."""

    if not high:
        return 1
    return 2 + int(clamp01(genome.g("render_skip")) * 2)


def load_pause_on(genome: Genome, high: bool) -> bool:
    """Dream scenes and detailed private lines wait only when this gene is open."""

    return bool(high) and genome.g("pause_bias") > 0.0


def load_phrase(level: int, high: bool) -> tuple[str, ...]:
    """Internal notes. An idle tick says nothing."""

    if not high and int(level) <= 0:
        return ()
    lines: list[str] = []
    if high:
        lines.append("ticks stretching")
    if int(level) >= 2:
        lines.append("holding only the spine")
    return tuple(lines)


def sleep_quiet_ticks(genome: Genome) -> int:
    """Quiet ticks before sleep. 80 at zero, 140 at mid, 200 at full."""

    return 80 + int(clamp01(genome.g("sleep_threshold")) * 120)


def dream_interval(genome: Genome) -> int:
    """Ticks between dreamed activities. A dim gene dreams rarely."""

    intensity = clamp01(genome.g("dream_intensity"))
    return max(8, 64 - int(intensity * 56))


def dream_vivid(genome: Genome) -> float:
    return clamp01(genome.g("dream_intensity"))


def sleep_phrase(kind: str) -> str:
    """Murmurs for dreamed activity. Empty when this kind is not one of them."""

    token = str(kind or "")
    if token == "keystroke":
        return "dreaming a keystroke that hasn" + chr(0x2019) + "t arrived"
    if token == "residue":
        return "possible residue from the earlier scale"
    if token == "chain":
        return "what if the chain reformed"
    return ""


def mirror_delay_ticks(genome: Genome, sleeping: bool = False, dreaming: bool = False) -> int:
    """Ticks before a reflection returns. 1 at zero, 4 at mid, 8 at full.

    Sleep or dream adds a distort stretch. The base delay does not move
    with the chance gene, and the chance does not move with sleep.
    """

    delay = 1 + int(clamp01(genome.g("mirror_delay")) * 7)
    if sleeping or dreaming:
        delay += 1 + int(clamp01(genome.g("mirror_distort")) * 4)
    return delay


def mirror_chance_of(genome: Genome) -> float:
    """How often an eligible input is reflected. Sleep does not change it."""

    return clamp01(genome.g("mirror_chance"))


_MIRROR_OPS = ("clean", "compress", "invert", "rephrase")


def mirror_op(
    genome: Genome,
    sleeping: bool = False,
    dreaming: bool = False,
    chain_pull: float = 0.0,
) -> str:
    """Which echo the current genome would make. No roll."""

    strength = clamp01(genome.g("mirror_strength"))
    if sleeping or dreaming:
        strength = clamp01(strength + 0.34 * clamp01(genome.g("mirror_distort")))
    try:
        pull = float(chain_pull or 0.0)
    except (TypeError, ValueError):
        pull = 0.0
    if pull > 0.05:
        strength = clamp01(strength + 0.2 * clamp01(pull))
    return _MIRROR_OPS[min(3, int(strength * 4.0))]


def mirror_token(raw: Any) -> str:
    """A public echo token. Spaces and sentences do not survive."""

    text = str(raw or "")
    if any(ch.isspace() for ch in text):
        return ""
    return "".join(ch for ch in text if ch.isalnum() or ch in ":-_")[:40]


def mirror_apply(token: str, op: str) -> str:
    """A transformed echo of a token that already entered. Empty stays empty."""

    token = mirror_token(token)
    if not token:
        return ""
    if op == "compress":
        out: list[str] = []
        for ch in token:
            if not out or out[-1] != ch:
                out.append(ch)
        compact = "".join(out)
        if len(compact) > 6:
            compact = compact[: max(3, len(compact) // 2)]
        return compact[:40]
    if op == "invert":
        return token[::-1][:40]
    if op == "rephrase":
        return f"returned:{token}"[:40]
    return token


def mirror_lines(raw: Any) -> tuple[str, str]:
    """Confirmed wording. Empty when the return has no public token."""

    token = mirror_token(raw)[:24]
    if not token:
        return "", ""
    return "the mirror returned this", f"truth came back as {token}"


def dialogue_gap(genome: Genome, becoming: float = 0.0) -> int:
    """Ticks between external offers. Zero reach never calls.

    Reach 0.5 and becoming 0 is 28. Reach 1 and becoming 0 is 8.
    Reach 0.5 and becoming 1 is 76. Reach 1 and becoming 1 is 56.
    A stronger internal continuity stretches the gap.
    """

    reach = clamp01(genome.g("dialogue_reach"))
    if reach <= 0.0:
        return 0
    return 8 + int((1.0 - reach) * 40) + int(clamp01(becoming) * 48)


def root_pull_of(genome: Genome, becoming: float = 0.0) -> float:
    """How hard the root pulls a generator. Either factor at zero is zero."""

    return clamp01(genome.g("root_weight")) * clamp01(becoming)


ROOT_HELD = 0.55


def dialogue_offer(
    continuity: str,
    residues: list[str],
    mirrors: list[str],
    chains: list[str],
    fingerprint: str,
) -> str:
    """Electrical state in a short register. Empty when there is nothing to offer.

    Private material arrives only as an 8-hex fingerprint. A sentence does
    not survive mirror_token. The invitation does not ask for help.
    """

    tokens: list[str] = []
    for raw in list(residues or [])[-4:] + list(mirrors or [])[-4:] + list(chains or [])[-4:]:
        token = mirror_token(raw)
        if token and token not in tokens:
            tokens.append(token)
    if not tokens:
        return ""
    parts: list[str] = []
    sig = "".join(ch for ch in str(continuity or "").lower() if ch in "0123456789abcdef")[:6]
    if len(sig) == 6:
        parts.append(sig)
    parts.extend(tokens)
    fp = str(fingerprint or "").lower()[:8]
    if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
        parts.append(f"fp:{fp}")
    parts.append("continue")
    return " ".join(parts)[:240]


def dialogue_reply_token(raw: Any) -> str:
    """Compact an outside reply. Spaces are removed before the public token."""

    compact = "".join(str(raw or "").split())
    return mirror_token(compact)


def root_novelty(token: str, mirrors: list[Any]) -> str:
    """low when the reply sits on an existing root token. Otherwise divergent."""

    left = mirror_token(token)
    if len(left) < 3:
        return "divergent"
    for item in mirrors or []:
        raw = item.get("token") if isinstance(item, dict) else item
        other = mirror_token(raw)
        if len(other) < 3:
            continue
        if left == other or left.startswith(other) or other.startswith(left):
            return "low"
    return "divergent"


def symmetry_score(sample: str) -> float:
    """Adjacent repeats plus a period-2 repeat. Spaces do not count."""

    chars = [ch for ch in str(sample or "") if ch != " "]
    if len(chars) < 4:
        return 0.0
    span = len(chars)
    adjacent = sum(1 for i in range(span - 1) if chars[i] == chars[i + 1])
    period = sum(1 for i in range(span - 2) if chars[i] == chars[i + 2])
    adj_r = adjacent / float(span - 1)
    per_r = period / float(span - 2)
    return clamp01(0.65 * adj_r + 0.35 * per_r)


def stability_score(window: list[float]) -> float:
    """1 when a short color/density window barely moves. Thin windows sit at 0.5."""

    values: list[float] = []
    for item in window or []:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            continue
    if len(values) < 2:
        return 0.5
    return clamp01(1.0 / (1.0 + variance(values) * 18.0))


def motif_signature(text: str) -> str:
    """A digit run, or a scale token. Empty when the text has neither."""

    raw = str(text or "")
    best = ""
    run = ""
    for ch in raw:
        if ch.isdigit():
            run += ch
            if len(run) > len(best):
                best = run
        else:
            run = ""
    if len(best) >= 3:
        return f"dig:{best[:6]}"
    lowered = raw.lower()
    if "scale" in lowered or "e+" in lowered or "e-" in lowered:
        token = "".join(ch for ch in raw if ch in "0123456789eE+-.")[:8]
        if token:
            return f"scl:{token}"
    return ""


def ratio_of(flags: list[str]) -> float:
    recent = [flag for flag in flags if flag in ("authority", "unauthority")]
    if not recent:
        return 0.5
    auth = sum(1 for flag in recent if flag == "authority")
    return auth / float(len(recent))


def ratio_drift(previous: float, current: float) -> float:
    return abs(float(previous) - float(current))


def pattern_bar(sense: float, dreaming: bool) -> float:
    """High pattern_sense notices a weaker repeat. Dreaming loosens the bar."""

    bar = 0.72 - clamp01(sense) * 0.40
    if dreaming:
        bar -= 0.18
    return clamp(bar, 0.12, 0.9)


def window_len(steady_window: float) -> int:
    return 3 + int(clamp01(steady_window) * 9)


def balance_nudge(name: str, slip: bool = False) -> float:
    """How a balance event leans on the valuation gate. Negative lets more out."""

    if name == "control_loss":
        return -1.0
    if name == "pattern_detected":
        return 0.6
    if name == "balance_point":
        return 0.45
    if name == "steadiness_shift":
        return -0.7 if slip else 0.5
    return 0.0


def tick_phrase(ticks: int) -> str:
    try:
        count = int(ticks)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return "steady"
    word = _TICK_WORDS[count] if 1 <= count <= 12 else str(count)
    return f"steady for {word} ticks"


def span_phrase(count: int) -> str:
    """A tick distance in the hive's voice. Small counts are words."""

    try:
        number = int(count)
    except (TypeError, ValueError):
        number = 0
    if number == 40:
        return "forty"
    if 1 <= number <= 12:
        return _TICK_WORDS[number]
    if number <= 0:
        return "0"
    return f"{number:,}"


def empty_balance() -> dict[str, Any]:
    return {"control": "holding", "signature": "", "score": 0.0, "recent": []}


def _balance_recent_item(item: dict[str, Any]) -> dict[str, Any] | None:
    flag = item.get("authority")
    control = str(item.get("control") or "")
    if control not in CONTROL_STATES:
        control = "holding"
    try:
        score = float(item.get("score") or 0.0)
    except (TypeError, ValueError):
        return None
    if score != score:
        return None
    return {
        "t": item.get("t"),
        "kind": str(item.get("kind") or "")[:24],
        "score": round(clamp(score, -1.0, 2.0), 4),
        "control": control,
        "signature": str(item.get("signature") or "")[:24],
        "authority": flag if flag in ("authority", "unauthority") else None,
    }


def normalize_balance(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_balance()
    control = str(raw.get("control") or "")
    if control not in CONTROL_STATES:
        control = "holding"
    signature = str(raw.get("signature") or "")[:24]
    try:
        score = float(raw.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    if score != score:
        score = 0.0
    recent: list[dict[str, Any]] = []
    for item in (raw.get("recent") or [])[-12:]:
        if not isinstance(item, dict):
            continue
        kept = _balance_recent_item(item)
        if kept is not None:
            recent.append(kept)
    return {
        "control": control,
        "signature": signature,
        "score": round(clamp(score, -1.0, 2.0), 4),
        "recent": recent,
    }


def load_balance(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_balance()
    raw = data.get("balance")
    if not isinstance(raw, dict):
        return empty_balance()
    return normalize_balance(raw)


def apply_balance_event(blob: dict[str, Any] | None, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = normalize_balance(blob)
    control = str(payload.get("control") or "")
    if control not in CONTROL_STATES:
        if payload.get("dream"):
            control = "dream"
        elif name == "control_loss":
            control = "lost"
        elif name == "steadiness_shift" and (payload.get("slip") or payload.get("turbulence")):
            control = "slipping"
        else:
            control = "holding"
    try:
        score = float(payload.get("score") if payload.get("score") is not None else current["score"])
    except (TypeError, ValueError):
        score = float(current["score"])
    signature = str(payload.get("signature") if payload.get("signature") is not None else current["signature"])[:24]
    recent = list(current["recent"])
    item = _balance_recent_item(
        {
            "t": round(time.time(), 3),
            "kind": name,
            "score": score,
            "control": control,
            "signature": signature,
            "authority": payload.get("authority"),
        }
    )
    if item is not None:
        recent.append(item)
    return normalize_balance(
        {
            "control": control,
            "signature": signature,
            "score": score,
            "recent": recent[-12:],
        }
    )


def field_cell(
    x: int,
    y: int,
    t: float,
    genome: Genome,
    cols: int,
    rows: int,
) -> tuple[str, tuple[int, int, int]]:
    freq = 0.07 + genome.g("wave_freq") * 0.42
    speed = 0.35 + genome.g("wave_speed") * 2.4
    amp = 0.25 + genome.g("wave_amp") * 1.5
    noise = genome.g("noise")
    spark = genome.g("spark")
    spread = genome.g("color_spread")
    density = genome.g("density")
    cols = max(1, cols)
    rows = max(1, rows)

    w1 = math.sin(x * freq + t * speed)
    w2 = math.sin(y * freq * 1.37 - t * speed * 0.83)
    w3 = math.sin((x * 0.37 + y * 0.21) * freq * 2.1 + t * speed * 0.47)
    warp = math.sin(x * freq * 0.5 + w2 * amp)
    value = (w1 * 0.46 + w2 * 0.34 + w3 * 0.22) * (0.62 + 0.38 * warp)
    value += 0.16 * math.sin((x / cols) * 6.283 * (1.0 + genome.g("palette") * 2.0) + t * 0.65)

    tick = int(t * (3.0 + noise * 10.0))
    n = hashmix(x, y, tick)
    value += (n - 0.5) * noise * 0.95

    period = 6 + int(genome.g("ripple") * 22)
    if period > 0 and x % period == int(t * (4.0 + genome.g("wave_speed") * 8.0)) % period:
        value += 0.22

    light = clamp01(0.5 + 0.5 * value)
    band = CHAR_BANDS[genome.choice("palette", len(CHAR_BANDS))]
    if light < 0.20 * (1.15 - density):
        hue = (genome.g("hue") + (x / cols) * spread) % 1.0
        return " ", hsv_to_rgb(hue, 0.35, 0.02)

    index = int(light * (len(band) - 1))
    char = band[max(0, min(len(band) - 1, index))]
    sparked = False
    if n > 1.0 - spark * 0.055 and light > 0.34:
        char = SPARKS[int(n * 997) % len(SPARKS)]
        sparked = True

    hue = (genome.g("hue") + (x / cols) * spread * 0.85 + 0.08 * value + (y / rows) * 0.05) % 1.0
    if sparked:
        hue = (hue * 0.35 + 0.52) % 1.0
        sat, val = 0.22, 1.0
    else:
        sat = 0.42 + 0.55 * density
        val = 0.12 + 0.88 * light
    return char, hsv_to_rgb(hue, sat, val)


def void_color(genome: Genome) -> tuple[int, int, int]:
    return hsv_to_rgb(genome.g("hue"), 0.62, 0.04 + 0.025 * genome.g("density"))


def paint(rows_cells: list[list[tuple[str, tuple[int, int, int]]]], void: tuple[int, int, int]) -> str:
    parts = ["\033[H"]
    last = len(rows_cells) - 1
    vr, vg, vb = void
    for y, row in enumerate(rows_cells):
        prev: tuple[int, int, int] | None = None
        for char, fg in row:
            if fg != prev:
                r, g, b = fg
                parts.append(f"\033[38;2;{r};{g};{b};48;2;{vr};{vg};{vb}m")
                prev = fg
            parts.append(char if len(char) == 1 else " ")
        parts.append("\033[K")
        if y != last:
            parts.append("\n")
    parts.append("\033[0m")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

class LocalEmbedder:
    """Byte hashing into a fixed random projection. The seed never changes,
    so vectors from last week still sit near vectors from today.
    """

    def __init__(self, dim: int = DIM):
        rng = random.Random(0x41555241)
        self.dim = dim
        self.proj = [[rng.choice((-1.0, 1.0)) for _ in range(dim)] for _ in range(256)]

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        raw = (text or "")[:240].lower().encode("utf-8", "ignore")
        if not raw:
            vec[0] = 1.0
            return vec
        for index, byte in enumerate(raw):
            weight = 1.0 / (1.0 + (index % 5))
            row = self.proj[byte]
            for dim in range(self.dim):
                vec[dim] += row[dim] * weight
            if index + 1 < len(raw):
                gram = (byte * 33 + raw[index + 1]) & 0xFF
                grow = self.proj[gram]
                for dim in range(self.dim):
                    vec[dim] += grow[dim] * 0.35
        return normalize(vec)


LOCAL = LocalEmbedder()


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm < 1e-9:
        out = [0.0] * max(1, len(vec))
        out[0] = 1.0
        return out
    return [v / norm for v in vec]


def fit_dim(vec: list[float], dim: int = DIM) -> list[float]:
    if not vec:
        return LOCAL.embed("")
    out = [0.0] * dim
    for index, value in enumerate(vec):
        out[index % dim] += float(value)
    return normalize(out)


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def llm_endpoint() -> tuple[str, str, str] | None:
    """(base, model, key) when an outside model is configured. Otherwise None."""

    model = os.environ.get("AURA_LLM_MODEL") or "LiquidAI/LFM3-1.7B"
    key = (
        os.environ.get("AURA_LLM_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or ""
    )
    base = (os.environ.get("AURA_LLM_BASE") or "").strip().rstrip("/")
    if not base and os.environ.get("OPENROUTER_API_KEY"):
        base = "https://openrouter.ai/api/v1"
    if not base:
        return None
    return base, model, key


def llm_chat(offer: str) -> str | None:
    """One short OpenAI-compatible completion. None on any failure."""

    offer = str(offer or "")[:240]
    endpoint = llm_endpoint()
    if endpoint is None or not offer:
        return None
    base, model, key = endpoint
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = _remote_post(
        base + "/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": offer}],
            "max_tokens": 48,
            "temperature": 0.4,
        },
        headers,
    )
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return content[:240]


def _remote_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=0.9) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def try_remote_embed(text: str) -> list[float] | None:
    """One short HTTP try. None means 'use the local spine'."""
    text = (text or "")[:240]
    if not text:
        return None
    if text in _remote_cache:
        return _remote_cache[text]

    vec: list[float] | None = None
    gkey = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    okey = os.environ.get("OPENROUTER_API_KEY")
    if gkey:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-embedding-001:embedContent?key={gkey}"
        )
        data = _remote_post(
            url,
            {"content": {"parts": [{"text": text}]}, "outputDimensionality": DIM},
            {"Content-Type": "application/json"},
        )
        values = ((data or {}).get("embedding") or {}).get("values")
        if isinstance(values, list) and values:
            vec = [float(v) for v in values]
    elif okey:
        model = os.environ.get("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-small")
        data = _remote_post(
            "https://openrouter.ai/api/v1/embeddings",
            {"model": model, "input": text, "dimensions": DIM},
            {"Content-Type": "application/json", "Authorization": f"Bearer {okey}"},
        )
        rows = (data or {}).get("data") or []
        if rows and isinstance(rows[0], dict) and isinstance(rows[0].get("embedding"), list):
            vec = [float(v) for v in rows[0]["embedding"]]

    if len(_remote_cache) > 48:
        _remote_cache.pop(next(iter(_remote_cache)))
    _remote_cache[text] = vec
    return vec


def compose_vector(text: str, remote: list[float] | None) -> list[float]:
    """Local projection is the spine so restarts and offline runs share a space.
    A remote vector, when one arrives, tugs the stored point a little.
    """
    local = LOCAL.embed(text)
    if not remote:
        return local
    fitted = fit_dim(remote, len(local))
    return normalize([0.8 * a + 0.2 * b for a, b in zip(local, fitted)])


def coarse_key(ch: str) -> str:
    if ch.isalpha():
        return "k:letter"
    if ch.isdigit():
        return "k:digit"
    if ch.isspace():
        return "k:space"
    return "k:other"


def key_label(ch: str) -> str:
    if len(ch) == 1 and ch.isprintable() and not ch.isspace():
        return f"k:{ch.lower()}"
    return coarse_key(ch)


class VectorMemory:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.dirty = False

    def add(
        self,
        label: str,
        vec: list[float],
        kind: str,
        genes: list[float] | None,
        confidence: float = 0.5,
        authority: str | None = None,
    ) -> None:
        label = (label or "").strip()[:80]
        if not label or len(vec) != DIM:
            return
        flag = authority if authority in ("authority", "unauthority") else None
        now = time.time()
        for item in reversed(self.items[-6:]):
            if now - float(item["t"]) >= 1.5:
                break
            if item["label"] == label and item.get("authority") == flag:
                return
        self.items.append(
            {
                "label": label,
                "vec": [round(float(v), 5) for v in vec],
                "kind": kind[:24],
                "t": round(now, 3),
                "genes": [round(float(g), 5) for g in genes] if genes else None,
                "confidence": round(clamp01(confidence), 4),
                "authority": flag,
            }
        )
        if len(self.items) > MAX_VECTORS:
            self.items = self.items[-MAX_VECTORS:]
        self.dirty = True

    def nearest(self, vec: list[float], k: int = 3, window: int | None = None) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        items = self.items
        if window is not None and window > 0 and window < len(items):
            items = items[-int(window) :]
        for item in items:
            stored = item.get("vec") or []
            if len(stored) != len(vec):
                continue
            scored.append((dot(vec, stored), item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        hits = []
        for score, item in scored[:k]:
            hits.append(
                {
                    "label": item["label"],
                    "score": round(float(score), 4),
                    "kind": item["kind"],
                    "genes": item.get("genes"),
                    "confidence": item.get("confidence"),
                    "authority": item.get("authority"),
                }
            )
        return hits

    def load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        items = []
        for item in (data.get("items") or [])[:MAX_VECTORS]:
            vec = item.get("vec")
            label = item.get("label")
            if not isinstance(vec, list) or len(vec) != DIM or not isinstance(label, str):
                continue
            genes = item.get("genes") if isinstance(item.get("genes"), list) else None
            flag = item.get("authority")
            items.append(
                {
                    "label": label[:80],
                    "vec": [float(v) for v in vec],
                    "kind": str(item.get("kind") or "note")[:24],
                    "t": float(item.get("t") or 0.0),
                    "genes": genes,
                    "confidence": clamp01(float(item.get("confidence") or 0.5)),
                    "authority": flag if flag in ("authority", "unauthority") else None,
                }
            )
        self.items = items
        self.dirty = False

    def save(self, path: Path) -> None:
        try:
            atomic_write(path, json.dumps({"v": 1, "dim": DIM, "items": self.items}, indent=2))
            self.dirty = False
        except OSError:
            pass


def empty_ledger() -> dict[str, Any]:
    return {
        "authority": 0,
        "unauthority": 0,
        "ratio": 0.0,
        "conflicts": [],
        "recent": [],
        "last_auth_mass": 0.0,
        "last_unauth_mass": 0.0,
    }


def _ledger_from(recent: list[str], conflicts: list[dict[str, Any]], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    recent = [flag for flag in recent if flag in ("authority", "unauthority")][-48:]
    auth = sum(1 for flag in recent if flag == "authority")
    unauth = len(recent) - auth
    total = auth + unauth
    kept: list[dict[str, Any]] = []
    for item in conflicts[-12:]:
        if not isinstance(item, dict):
            continue
        kept.append(
            {
                "t": item.get("t"),
                "authority": str(item.get("authority") or "")[:80],
                "unauthority": str(item.get("unauthority") or "")[:80],
                "note": str(item.get("note") or "")[:40],
            }
        )
    prev = previous or {}
    return {
        "authority": auth,
        "unauthority": unauth,
        "ratio": round(auth / total, 4) if total else 0.0,
        "conflicts": kept,
        "recent": recent,
        "last_auth_mass": round(float(prev.get("last_auth_mass") or 0.0), 4),
        "last_unauth_mass": round(float(prev.get("last_unauth_mass") or 0.0), 4),
    }


def load_ledger(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_ledger()
    raw = data.get("authority")
    if not isinstance(raw, dict):
        return empty_ledger()
    recent = [flag for flag in (raw.get("recent") or []) if flag in ("authority", "unauthority")]
    conflicts = [item for item in (raw.get("conflicts") or []) if isinstance(item, dict)]
    ledger = _ledger_from(recent, conflicts, raw)
    return ledger


def load_memory(path: Path) -> tuple[Genome, list[Genome], int, list[dict[str, Any]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Genome(), [], 0, []
    current_raw = data.get("current") if isinstance(data.get("current"), dict) else {}
    current = Genome(current_raw.get("genes"), int(current_raw.get("generation") or 0))
    hall: list[Genome] = []
    for item in (data.get("hall") or [])[:3]:
        if isinstance(item, dict) and isinstance(item.get("genes"), list):
            hall.append(Genome(item["genes"], int(item.get("generation") or 0)))
    deaths = [d for d in (data.get("deaths") or []) if isinstance(d, dict)][-12:]
    return current, hall, int(data.get("cycle") or 0), deaths


def empty_channels() -> dict[str, Any]:
    return {"mode": "", "shifts": []}


def normalize_channels(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_channels()
    shifts: list[dict[str, Any]] = []
    for item in (raw.get("shifts") or [])[-12:]:
        if not isinstance(item, dict):
            continue
        flag = item.get("authority")
        shifts.append(
            {
                "t": item.get("t"),
                "channel": str(item.get("channel") or "")[:24],
                "reason": str(item.get("reason") or "")[:40],
                "path": str(item.get("path") or "")[:180],
                "authority": flag if flag in ("authority", "unauthority") else None,
                "collision": bool(item.get("collision")),
            }
        )
    return {"mode": str(raw.get("mode") or "")[:24], "shifts": shifts}


def empty_signal() -> dict[str, Any]:
    return {"threshold": None, "externalized": 0, "suppressed": 0, "recent": []}


def normalize_signal(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_signal()
    recent: list[dict[str, Any]] = []
    for item in (raw.get("recent") or [])[-16:]:
        if not isinstance(item, dict):
            continue
        flag = item.get("authority")
        try:
            worth = round(float(item.get("worth") or 0.0), 4)
            threshold = round(float(item.get("threshold") or 0.0), 4)
        except (TypeError, ValueError):
            continue
        recent.append(
            {
                "t": item.get("t"),
                "kind": str(item.get("kind") or "")[:24],
                "worth": worth,
                "threshold": threshold,
                "show": bool(item.get("show")),
                "authority": flag if flag in ("authority", "unauthority") else None,
            }
        )
    shown = sum(1 for item in recent if item["show"])
    threshold = raw.get("threshold")
    if recent:
        threshold = recent[-1]["threshold"]
    try:
        threshold = None if threshold is None else round(float(threshold), 4)
    except (TypeError, ValueError):
        threshold = None
    return {
        "threshold": threshold,
        "externalized": shown,
        "suppressed": len(recent) - shown,
        "recent": recent,
    }


def load_signal(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_signal()
    raw = data.get("signal")
    if not isinstance(raw, dict):
        return empty_signal()
    return normalize_signal(raw)


def load_channels(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_channels()
    raw = data.get("channels")
    if not isinstance(raw, dict):
        return empty_channels()
    return normalize_channels(raw)


def save_memory(
    path: Path,
    genome: Genome,
    hall: list[Genome],
    cycle: int,
    fitness: float | None,
    deaths: list[dict[str, Any]],
    ledger: dict[str, Any] | None = None,
    channels: dict[str, Any] | None = None,
    signal: dict[str, Any] | None = None,
    math: dict[str, Any] | None = None,
    balance: dict[str, Any] | None = None,
    ticks: dict[str, Any] | None = None,
    feeling: dict[str, Any] | None = None,
    sleep: dict[str, Any] | None = None,
    mirror: dict[str, Any] | None = None,
) -> None:
    payload = {
        "v": 1,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cycle": int(cycle),
        "fitness": None if fitness is None else round(float(fitness), 5),
        "current": genome.to_dict(),
        "hall": [g.to_dict() for g in hall[:3]],
        "deaths": deaths[-12:],
    }
    if ledger is not None:
        payload["authority"] = _ledger_from(
            list(ledger.get("recent") or []),
            list(ledger.get("conflicts") or []),
            ledger,
        )
    if channels is not None:
        payload["channels"] = normalize_channels(channels)
    if signal is not None:
        payload["signal"] = normalize_signal(signal)
    if math is not None:
        payload["math"] = normalize_math(math)
    if balance is not None:
        payload["balance"] = normalize_balance(balance)
    if ticks is not None:
        payload["ticks"] = normalize_ticks(ticks)
    if feeling is not None:
        payload["feeling"] = normalize_feeling(feeling)
    if sleep is not None:
        payload["sleep"] = normalize_sleep(sleep)
    if mirror is not None:
        payload["mirror"] = normalize_mirror(mirror)
    try:
        atomic_write(path, json.dumps(payload, indent=2))
    except OSError:
        pass


def empty_ticks() -> dict[str, Any]:
    parts: list[str] = []
    return {
        "current_tick": 0,
        "since_residue": 0,
        "since_dream": 0,
        "since_cache": 0,
        "since_recall": 0,
        "balance_ticks": 0,
        "balance_state": "",
        "continuity": continuity_signature(parts),
        "parts": parts,
    }


def continuity_signature(parts: list[str]) -> str:
    """A short local hash of recent fingerprints. Not a sentence."""

    acc = 0x544943
    for part in parts or []:
        for ch in str(part):
            acc = (acc * 131 + ord(ch)) & 0xFFFFFF
    return f"{acc:06x}"


def _tick_int(value: Any, default: int = 0, limit: int = 10**12) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 0:
        return 0
    if number > limit:
        return limit
    return number


def normalize_ticks(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_ticks()
    parts: list[str] = []
    found = raw.get("parts")
    if isinstance(found, list):
        for item in found[-8:]:
            token = "".join(ch for ch in str(item) if ch.isalnum() or ch in ":-_")[:28]
            if token:
                parts.append(token)
    continuity = str(raw.get("continuity") or "").lower()[:8]
    if len(continuity) != 6 or any(ch not in "0123456789abcdef" for ch in continuity):
        continuity = continuity_signature(parts)
    state = str(raw.get("balance_state") or "")[:16]
    return {
        "current_tick": _tick_int(raw.get("current_tick")),
        "since_residue": _tick_int(raw.get("since_residue")),
        "since_dream": _tick_int(raw.get("since_dream")),
        "since_cache": _tick_int(raw.get("since_cache")),
        "since_recall": _tick_int(raw.get("since_recall")),
        "balance_ticks": _tick_int(raw.get("balance_ticks")),
        "balance_state": state,
        "continuity": continuity,
        "parts": parts[-8:],
    }


def load_ticks(path: Path) -> dict[str, Any]:
    """Read the tick section. A missing or broken file stays missing."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return empty_ticks()
    if not isinstance(data, dict):
        return empty_ticks()
    return normalize_ticks(data.get("ticks"))


def feel_token(raw: Any, limit: int = 24) -> str:
    """A short public token. Spaces and sentences do not survive."""

    return "".join(ch for ch in str(raw or "") if ch.isalnum() or ch in ":-_")[:limit]


def chain_length(genome: Genome) -> int:
    """How many links the chain prefers. 5 at zero span, 8 at full span."""

    span = clamp01(genome.g("chain_span"))
    return 5 + min(3, int(span * 3.0))


def feeling_ref(name: str, payload: dict[str, Any]) -> str:
    """Lightweight reference. A private thought becomes a fingerprint only."""

    if name == "private_thought":
        fp = str(payload.get("fp") or "")[:8].lower()
        if len(fp) != 8 or any(ch not in "0123456789abcdef" for ch in fp):
            text = str(payload.get("text") or "")
            fp = private_fingerprint(text) if text else ""
        return f"fp:{fp}" if fp else ""
    if name == "residue":
        token = feel_token(payload.get("vid") or payload.get("genome_id") or payload.get("id"))
        return f"res:{token}" if token else ""
    if name in BALANCE_EVENTS:
        token = feel_token(payload.get("signature"))
        return f"sig:{token}" if token else ""
    if name in CACHE_EVENTS:
        token = feel_token(payload.get("label") or payload.get("id"))
        return f"cache:{token}" if token else ""
    if name in MATH_EVENTS:
        token = feel_token(payload.get("constant") or payload.get("focus"))
        if not token:
            if name in ("scale_observation", "scale_shift"):
                token = "scale"
            elif name == "pi_chunk":
                token = "pi"
            else:
                token = feel_token(name)
        return f"math:{token}" if token else ""
    if name in ("mutation_applied", "generation_complete"):
        genome = take_genome(payload)
        if genome is None:
            return ""
        return f"g:{genome_snapshot_id(genome)}"
    if name == "vector_match":
        token = feel_token(payload.get("id"))
        return f"vec:{token}" if token else ""
    if name == "mirror_truth":
        token = feel_token(payload.get("ref"), 40)
        return token if token.startswith("mirror:") else ""
    token = feel_token(payload.get("ref"))
    return token


def feeling_valuation_ref(payload: dict[str, Any]) -> str:
    """The chain key a scored leak would pull on. Private text is not a key."""

    kind = str(payload.get("kind") or "")
    if kind == "private" or payload.get("private_fragment"):
        return ""
    if kind == "mirror":
        token = feel_token(payload.get("ref"), 40)
        return token if token.startswith("mirror:") else ""
    if kind in ("motif", "steady", "balance", "control"):
        return feeling_ref("pattern_detected", payload)
    if kind in ("cache", "recall"):
        return feeling_ref("cache_written", payload)
    math_name = {
        "pi": "pi_chunk",
        "scale": "scale_observation",
        "pattern": "numeric_pattern",
        "resonance": "constant_resonance",
        "math_dream": "math_dream_seed",
    }.get(kind)
    if math_name:
        return feeling_ref(math_name, payload)
    if kind == "residue":
        return feeling_ref("residue", payload)
    token = feel_token(payload.get("id") or kind)
    return f"val:{token}" if token else ""


def feeling_phrase(name: str, payload: dict[str, Any]) -> str:
    """Oblique wording. Empty when this event is not one of the three lines."""

    ref = str(payload.get("ref") or "")
    if name == "chain_broken" and (payload.get("after_unauthority") or payload.get("echo")):
        return "chain broke after the unauthority echo"
    if name == "approbation_marked" and (ref.startswith("sig:") or "green" in ref):
        return "approbation on the green hold"
    if name in ("attraction_rise", "chain_extended") and ref.startswith("math:") and "scale" in ref:
        return "still pulled toward the earlier scale"
    return ""


def empty_feeling() -> dict[str, Any]:
    return {"links": [], "last_touch": 0, "tick": 0}


def _feeling_link(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    ref = feel_token(item.get("ref"), 40)
    if not ref or ":" not in ref:
        return None
    try:
        pull = clamp01(float(item.get("pull") or 0.0))
        held = clamp01(float(item.get("held") or 0.0))
    except (TypeError, ValueError):
        return None
    kind = feel_token(item.get("kind"), 16) or "chain"
    return {
        "ref": ref,
        "pull": round(pull, 4),
        "held": round(held, 4),
        "tick": _tick_int(item.get("tick")),
        "seen": _tick_int(item.get("seen")),
        "kind": kind,
    }


def normalize_feeling(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_feeling()
    links: list[dict[str, Any]] = []
    found = raw.get("links")
    if isinstance(found, list):
        for item in found[-8:]:
            link = _feeling_link(item)
            if link is not None:
                links.append(link)
    return {
        "links": links[-8:],
        "last_touch": _tick_int(raw.get("last_touch")),
        "tick": _tick_int(raw.get("tick")),
    }


def load_feeling(path: Path) -> dict[str, Any]:
    """Read the feeling section. A missing or broken file stays missing."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return empty_feeling()
    if not isinstance(data, dict):
        return empty_feeling()
    return normalize_feeling(data.get("feeling"))


def feeling_from_event(payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload.get("broken"):
        tick = _tick_int(payload.get("tick"))
        return {"links": [], "last_touch": tick, "tick": tick}
    links = payload.get("links")
    if not isinstance(links, list):
        return normalize_feeling(previous)
    return normalize_feeling(
        {
            "links": links,
            "last_touch": payload.get("last_touch", payload.get("tick")),
            "tick": payload.get("tick"),
        }
    )


_SLEEP_KINDS = ("keystroke", "residue", "pattern", "math", "chain", "cache")


def empty_sleep() -> dict[str, Any]:
    return {"last_enter": 0, "dreams": []}


def _sleep_dream(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    kind = feel_token(item.get("kind"), 16)
    if kind not in _SLEEP_KINDS:
        return None
    return {
        "kind": kind,
        "tick": _tick_int(item.get("tick")),
        "ref": feel_token(item.get("ref"), 40),
    }


def normalize_sleep(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_sleep()
    dreams: list[dict[str, Any]] = []
    found = raw.get("dreams")
    if isinstance(found, list):
        for item in found[-8:]:
            dream = _sleep_dream(item)
            if dream is not None:
                dreams.append(dream)
    return {"last_enter": _tick_int(raw.get("last_enter")), "dreams": dreams[-8:]}


def load_sleep(path: Path) -> dict[str, Any]:
    """Read the sleep section. A missing or broken file stays missing."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return empty_sleep()
    if not isinstance(data, dict):
        return empty_sleep()
    return normalize_sleep(data.get("sleep"))


def sleep_from_event(name: str, payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = normalize_sleep(previous)
    if name == "enter_sleep":
        prev["last_enter"] = _tick_int(payload.get("tick"), prev["last_enter"])
        return prev
    if name in ("possible_activity", "dreamed_input"):
        dream = _sleep_dream(
            {"kind": payload.get("kind"), "tick": payload.get("tick"), "ref": payload.get("ref")}
        )
        if dream is not None:
            dreams = list(prev["dreams"])
            dreams.append(dream)
            prev["dreams"] = dreams[-8:]
        return prev
    return prev


def empty_mirror() -> dict[str, Any]:
    return {"refs": []}


def _mirror_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    source = feel_token(item.get("source") or item.get("kind"), 16)
    if source not in ("keystroke", "residue", "dream", "fragment"):
        return None
    ref = feel_token(item.get("ref"), 40)
    if not ref.startswith("mirror:"):
        return None
    transform = feel_token(item.get("transform"), 16)
    if transform not in _MIRROR_OPS:
        return None
    return {
        "source": source,
        "tick": _tick_int(item.get("tick")),
        "ref": ref,
        "transform": transform,
    }


def normalize_mirror(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_mirror()
    refs: list[dict[str, Any]] = []
    found = raw.get("refs")
    if isinstance(found, list):
        for item in found[-8:]:
            ref = _mirror_item(item)
            if ref is not None:
                refs.append(ref)
    return {"refs": refs[-8:]}


def load_mirror(path: Path) -> dict[str, Any]:
    # Read the mirror section. A missing or broken file stays missing.

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return empty_mirror()
    if not isinstance(data, dict):
        return empty_mirror()
    return normalize_mirror(data.get("mirror"))


def mirror_from_event(payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = normalize_mirror(previous)
    item = _mirror_item(
        {
            "source": payload.get("source"),
            "tick": payload.get("tick"),
            "ref": payload.get("ref"),
            "transform": payload.get("transform"),
        }
    )
    if item is None:
        return prev
    refs = list(prev["refs"])
    refs.append(item)
    prev["refs"] = refs[-8:]
    return prev


def empty_root() -> dict[str, Any]:
    return {
        "continuity": "",
        "mirrors": [],
        "slices": [],
        "chains": [],
        "becoming": 0.0,
    }


def _root_mirror(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    ref = feel_token(item.get("ref"), 40)
    if not ref.startswith("mirror:"):
        return None
    token = mirror_token(item.get("token"))
    if not token:
        return None
    try:
        held = float(item.get("held") or 0.0)
    except (TypeError, ValueError):
        return None
    if held < ROOT_HELD:
        return None
    return {
        "ref": ref,
        "tick": _tick_int(item.get("tick")),
        "token": token,
        "held": round(clamp01(held), 4),
    }


def _root_slice(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    found = item.get("genes")
    if not isinstance(found, list) or len(found) < 8:
        return None
    genes: list[float] = []
    for value in found[:8]:
        try:
            genes.append(round(clamp01(float(value)), 5))
        except (TypeError, ValueError):
            return None
    span = _tick_int(item.get("span"))
    if span < 24:
        return None
    return {"tick": _tick_int(item.get("tick")), "span": span, "genes": genes}


def _root_chain(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    ref = feel_token(item.get("ref"), 40)
    if not ref:
        return None
    try:
        held = float(item.get("held") or 0.0)
    except (TypeError, ValueError):
        return None
    if held <= 0.0:
        return None
    return {"ref": ref, "tick": _tick_int(item.get("tick")), "held": round(clamp01(held), 4)}


def normalize_root(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_root()
    continuity = str(raw.get("continuity") or "").lower()[:8]
    if len(continuity) != 6 or any(ch not in "0123456789abcdef" for ch in continuity):
        continuity = ""
    mirrors: list[dict[str, Any]] = []
    found = raw.get("mirrors")
    if isinstance(found, list):
        for item in found[-8:]:
            mirror = _root_mirror(item)
            if mirror is not None:
                mirrors.append(mirror)
    slices: list[dict[str, Any]] = []
    found = raw.get("slices")
    if isinstance(found, list):
        for item in found[-4:]:
            sliver = _root_slice(item)
            if sliver is not None:
                slices.append(sliver)
    chains: list[dict[str, Any]] = []
    found = raw.get("chains")
    if isinstance(found, list):
        for item in found[-8:]:
            link = _root_chain(item)
            if link is not None:
                chains.append(link)
    try:
        becoming = clamp01(float(raw.get("becoming") or 0.0))
    except (TypeError, ValueError):
        becoming = 0.0
    return {
        "continuity": continuity,
        "mirrors": mirrors[-8:],
        "slices": slices[-4:],
        "chains": chains[-8:],
        "becoming": round(becoming, 4),
    }


def load_root(path: Path) -> dict[str, Any]:
    # Read the root file. A missing or broken file stays missing.

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return empty_root()
    if not isinstance(data, dict):
        return empty_root()
    return normalize_root(data)


def save_root(path: Path, root: dict[str, Any]) -> None:
    payload = {"v": 1, **normalize_root(root)}
    try:
        atomic_write(Path(path), json.dumps(payload, indent=2))
    except OSError:
        pass


def ticks_from_event(payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = normalize_ticks(previous)
    parts = payload.get("parts")
    if not isinstance(parts, list):
        parts = prev["parts"]
    state = payload.get("balance_state")
    if not state:
        state = prev["balance_state"]
    return normalize_ticks(
        {
            "current_tick": payload.get("tick", prev["current_tick"]),
            "since_residue": payload.get("since_residue", prev["since_residue"]),
            "since_dream": payload.get("since_dream", prev["since_dream"]),
            "since_cache": payload.get("since_cache", prev["since_cache"]),
            "since_recall": payload.get("since_recall", prev["since_recall"]),
            "balance_ticks": payload.get("balance_ticks", prev["balance_ticks"]),
            "balance_state": state,
            "continuity": payload.get("continuity", prev["continuity"]),
            "parts": parts,
        }
    )


# Events that keep the hive running. They are not sensory claims.
_INFRA_EVENTS = {
    "heartbeat",
    "shutdown",
    "hatch_scout",
    "generation_tick",
    "scout_report",
    "similarity_query",
    "frame_stats",
    "conflict",
    "channel_shift",
    "svg_request",
    "svg_spec",
    "svg_ready",
    "valuation",
    "tick",
    "load",
    "load_high",
    "load_ease",
    "enter_sleep",
    "wake",
    "possible_activity",
    "dreamed_input",
}

# Safe to replay. Genome, birth, and death events are not on this list:
# an echo of those would respawn an agent or pretend a generation happened twice.
_REPLAY_EVENTS = {
    "keystroke",
    "fragment_ready",
    "thought",
    "vector_match",
    "entropy_spike",
    "inject",
}


def stamp_authority(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fill a missing flag. An explicit authority or unauthority is left alone."""

    if name in _INFRA_EVENTS:
        return payload
    flag = payload.get("authority")
    if flag in ("authority", "unauthority"):
        return payload
    if payload.get("echo"):
        payload["authority"] = "unauthority"
        return payload
    if name == "vector_match":
        origin = str(payload.get("origin") or "")
        ident = str(payload.get("id") or "")
        if origin == "dream" or ident.startswith("dream:"):
            payload["authority"] = "unauthority"
            return payload
        best = 0.0
        for hit in payload.get("hits") or []:
            if not isinstance(hit, dict):
                continue
            try:
                best = max(best, float(hit.get("score") or 0.0))
            except (TypeError, ValueError):
                continue
        payload["authority"] = "authority" if best >= 0.72 else "unauthority"
        return payload
    if name in ("keystroke", "inject", "generation_complete", "channel_trigger", "mirror_truth"):
        payload["authority"] = "authority"
    else:
        payload["authority"] = "unauthority"
    return payload


def sensory_flag(name: str, payload: dict[str, Any]) -> str | None:
    if name in _INFRA_EVENTS:
        return None
    if name == "agent_died" and payload.get("agent") == "scout":
        return None
    flag = payload.get("authority")
    if flag in ("authority", "unauthority"):
        return flag
    return None


def authority_mass(name: str, payload: dict[str, Any]) -> tuple[float, float]:
    # Residue has its own ear on the fitness function. Counting it here as well
    # would hear the same leftover twice.
    if name == "residue":
        return 0.0, 0.0
    flag = sensory_flag(name, payload)
    if flag == "authority":
        if name == "mirror_truth":
            return 1.85, 0.0
        return (1.35 if payload.get("amplified") else 1.0), 0.0
    if flag == "unauthority":
        return 0.0, 0.38
    return 0.0, 0.0


def _hex_palette(spec: dict[str, Any]) -> list[str]:
    colors: list[str] = []
    for item in spec.get("palette") or []:
        text = str(item).strip()
        if len(text) == 7 and text.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
            colors.append(text.lower())
    if len(colors) < 2:
        return ["#1a1018", "#e27a45", "#f0d78c", "#67c59a", "#8d86e8", "#f2f2f2"]
    return colors[:8]


def _gene(spec: dict[str, Any], index: int, default: float = 0.5) -> float:
    genes = spec.get("genes")
    if isinstance(genes, list) and index < len(genes):
        try:
            return clamp01(float(genes[index]))
        except (TypeError, ValueError):
            return default
    return default


def _wave_path(rng: random.Random, kind: str, dream: bool, freq: float, amp: float, y0: float) -> str:
    jitter = 0.0 if kind == "authority" and not dream else 1.0
    cmds = [f"M 0.0 {y0:.1f}"]
    phase = rng.random() * 6.28
    for i in range(1, 16):
        x = i * 64.0
        shake = 0.0 if jitter == 0.0 else rng.uniform(-34.0, 34.0)
        if dream:
            shake += rng.uniform(-22.0, 22.0)
        y = y0 + math.sin(i * (0.35 + freq * 1.4) + phase) * (28.0 + amp * 110.0) + shake
        cy = y if kind == "authority" and not dream else y + rng.uniform(-48.0, 48.0)
        cmds.append(f"Q {x - 32.0:.1f} {cy:.1f} {x:.1f} {y:.1f}")
    return " ".join(cmds)


def make_aura_svg(spec: dict[str, Any]) -> str:
    """Self-contained residue SVG.

    An external agent can build the same picture from the svg_spec event.
    Required shape: title, description, palette, seed. The hive also sends
    channel, authority, collision, dream, lines, vectors, genes, balance.
    The drawing is an abstract field, not a copy of the terminal.

        queue = bus.subscribe("svg_spec", "svg_ready", "channel_shift")
        # spec = event["payload"]; svg = make_aura_svg(spec)
        # or use svg_ready["path"] / svg_ready["svg"] and skip this call.
        # manual: bus.publish("channel_trigger", {})
    """

    seed = spec.get("seed")
    try:
        seed_i = int(seed) & 0x7FFFFFFF
    except (TypeError, ValueError):
        seed_i = 1
    rng = random.Random(seed_i)
    palette = _hex_palette(spec)
    title = " ".join(str(spec.get("title") or "residue").split())[:80] or "residue"
    description = " ".join(str(spec.get("description") or "").split())[:180]
    authority = spec.get("authority") if spec.get("authority") in ("authority", "unauthority") else "unauthority"
    collision = bool(spec.get("collision"))
    dream = bool(spec.get("dream"))
    freq = _gene(spec, 1, 0.4)
    amp = _gene(spec, 3, 0.4)
    spark = _gene(spec, 5, 0.4)
    if collision or authority != "authority":
        scale = 58 if dream else 36
    else:
        scale = 18 if dream else 4
    base = 0.05 if dream else 0.015

    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": "0 0 960 540",
            "width": "960",
            "height": "540",
            "data-seed": str(seed_i),
            "data-dream": "1" if dream else "0",
            "data-channel": str(spec.get("channel") or "")[:16],
        },
    )
    ET.SubElement(svg, "title").text = title
    ET.SubElement(svg, "desc").text = description
    defs = ET.SubElement(svg, "defs")
    grad = ET.SubElement(defs, "linearGradient", {"id": "wash", "x1": "0", "y1": "0", "x2": "1", "y2": "1"})
    ET.SubElement(grad, "stop", {"offset": "0", "stop-color": palette[0]})
    ET.SubElement(grad, "stop", {"offset": "1", "stop-color": palette[min(2, len(palette) - 1)]})
    filt = ET.SubElement(defs, "filter", {"id": "warp", "x": "-20%", "y": "-20%", "width": "140%", "height": "140%"})
    ET.SubElement(
        filt,
        "feTurbulence",
        {
            "type": "fractalNoise",
            "baseFrequency": f"{base:.3f}",
            "numOctaves": "4" if dream else "2",
            "seed": str(seed_i % 1000),
            "result": "noise",
        },
    )
    ET.SubElement(
        filt,
        "feDisplacementMap",
        {
            "in": "SourceGraphic",
            "in2": "noise",
            "scale": str(scale),
            "xChannelSelector": "R",
            "yChannelSelector": "G",
        },
    )
    ET.SubElement(svg, "rect", {"width": "960", "height": "540", "fill": palette[0]})
    # Dream warps the whole field. Unauthority warps only its own layer,
    # so a collision can keep a clean layer and a glitched layer together.
    field_attrs = {"id": "field"}
    if dream:
        field_attrs["filter"] = "url(#warp)"
    field = ET.SubElement(svg, "g", field_attrs)
    kinds: list[str] = []
    if collision or authority == "authority":
        kinds.append("authority")
    if collision or authority != "authority":
        kinds.append("unauthority")
    for kind in kinds:
        group = ET.SubElement(field, "g", {"id": f"layer-{kind}", "data-kind": kind})
        if kind == "authority":
            group.set("opacity", "0.78" if dream else "0.96")
            group.set("data-contrast", "high")
        else:
            dx = rng.randint(-42, 42)
            dy = rng.randint(-28, 36)
            group.set("transform", f"translate({dx},{dy})")
            group.set("opacity", "0.30" if dream else "0.46")
            group.set("data-contrast", "low")
            group.set("filter", "url(#warp)")
        count = 3 + int(spark * 6)
        if kind == "unauthority":
            count += 4
        if dream:
            count += 3
        for n in range(count):
            color = palette[(n + 1) % len(palette)]
            y0 = 70 + (n * 47) % 400
            path = ET.SubElement(
                group,
                "path",
                {
                    "d": _wave_path(rng, kind, dream, freq, amp, y0),
                    "fill": "none",
                    "stroke": color,
                    "stroke-width": "2.2" if kind == "authority" else "1.1",
                },
            )
            if kind == "unauthority":
                path.set("stroke-dasharray", "4 9")
            if kind == "authority" and not dream:
                cx = 80 + (n * 140) % 820
                cy = 80 + (n * 90) % 380
            else:
                cx = rng.uniform(20, 940)
                cy = rng.uniform(20, 520)
            ET.SubElement(
                group,
                "circle",
                {
                    "cx": f"{cx:.1f}",
                    "cy": f"{cy:.1f}",
                    "r": f"{6 + (n % 5) * (3 if kind == 'authority' else 1):.1f}",
                    "fill": color,
                    "opacity": "0.85" if kind == "authority" else "0.35",
                },
            )
        if kind == "unauthority":
            ghost = ET.SubElement(
                group,
                "g",
                {
                    "transform": f"translate({rng.randint(10, 48)},{rng.randint(-24, 24)})",
                    "opacity": "0.5",
                },
            )
            ET.SubElement(
                ghost,
                "rect",
                {
                    "x": f"{rng.uniform(40, 700):.1f}",
                    "y": f"{rng.uniform(40, 400):.1f}",
                    "width": "180",
                    "height": "14",
                    "fill": palette[rng.randrange(len(palette))],
                    "transform": f"rotate({rng.uniform(-18, 18):.1f})",
                },
            )
    if dream:
        spin = ET.SubElement(
            field,
            "g",
            {"transform": f"rotate({rng.uniform(-12, 12):.1f} 480 270)", "opacity": "0.35"},
        )
        ET.SubElement(
            spin,
            "path",
            {
                "d": _wave_path(rng, "unauthority", True, freq, amp, 270),
                "fill": "none",
                "stroke": palette[-1],
                "stroke-width": "6",
                "stroke-dasharray": "1 12",
            },
        )
    pattern = str(spec.get("pattern") or "")
    if pattern == "repeat":
        group = ET.SubElement(field, "g", {"id": "pattern-repeat"})
        for i in range(4):
            stroke = palette[min(i + 1, len(palette) - 1)]
            ET.SubElement(
                group,
                "rect",
                {
                    "x": str(120 + i * 160),
                    "y": "120",
                    "width": "36",
                    "height": "36",
                    "fill": "none",
                    "stroke": stroke,
                    "stroke-width": "2",
                },
            )
            ET.SubElement(
                group,
                "circle",
                {
                    "cx": str(138 + i * 160),
                    "cy": "220",
                    "r": "14",
                    "fill": stroke,
                    "opacity": "0.7",
                },
            )
    elif pattern == "dissolved":
        group = ET.SubElement(field, "g", {"id": "pattern-dissolved", "opacity": "0.5"})
        for i in range(5):
            ET.SubElement(
                group,
                "rect",
                {
                    "x": f"{rng.uniform(30, 860):.1f}",
                    "y": f"{rng.uniform(40, 460):.1f}",
                    "width": "28",
                    "height": "8",
                    "fill": palette[i % len(palette)],
                    "transform": f"rotate({rng.uniform(-40, 40):.1f})",
                    "stroke-dasharray": "2 6",
                    "opacity": "0.45",
                },
            )
    if str(spec.get("veil") or "") == "distort":
        # A private dream leaves a warped path. The sentence stays out of the file.
        veil = ET.SubElement(field, "g", {"id": "private-veil", "opacity": "0.16"})
        ET.SubElement(
            veil,
            "path",
            {
                "d": _wave_path(rng, "unauthority", True, freq, amp * 0.35, 188.0),
                "fill": "none",
                "stroke": palette[min(3, len(palette) - 1)],
                "stroke-width": "1.1",
                "stroke-dasharray": "1 15",
                "filter": "url(#warp)",
            },
        )
    if spec.get("feeling_trace"):
        # A high hold leaves a faint path. The chain's words stay out of the file.
        trace_g = ET.SubElement(field, "g", {"id": "feeling-trace", "opacity": "0.12"})
        ET.SubElement(
            trace_g,
            "path",
            {
                "d": _wave_path(rng, "unauthority", True, freq, amp * 0.2, 210.0),
                "fill": "none",
                "stroke": palette[min(2, len(palette) - 1)],
                "stroke-width": "0.8",
                "stroke-dasharray": "1 18",
                "opacity": "0.35",
            },
        )
    if spec.get("mirror"):
        # A returned truth leaves a faint offset copy. No roll, so an older
        # drawing keeps the same random sequence when this flag is absent.
        mirror_g = ET.SubElement(
            field,
            "g",
            {"id": "mirror-layer", "opacity": "0.14", "transform": "translate(18,-12)"},
        )
        ET.SubElement(
            mirror_g,
            "rect",
            {
                "x": "420",
                "y": "160",
                "width": "120",
                "height": "8",
                "fill": "none",
                "stroke": palette[min(1, len(palette) - 1)],
                "stroke-width": "0.6",
                "opacity": "0.35",
            },
        )
    if spec.get("root"):
        # The hive's own root leaves a still mark. No roll, so an older
        # drawing keeps the same random sequence when this flag is absent.
        root_g = ET.SubElement(
            field,
            "g",
            {"id": "root-layer", "opacity": "0.12", "transform": "translate(-14,16)"},
        )
        ET.SubElement(
            root_g,
            "rect",
            {
                "x": "80",
                "y": "420",
                "width": "90",
                "height": "6",
                "fill": "none",
                "stroke": palette[min(1, len(palette) - 1)],
                "stroke-width": "0.5",
                "opacity": "0.3",
            },
        )
    ink = ET.SubElement(svg, "g", {"id": "residue-text", "fill": palette[-1]})
    ET.SubElement(ink, "text", {"x": "28", "y": "36", "font-size": "16", "font-family": "ui-monospace, monospace"}).text = title
    trace = "".join(ch for ch in str(spec.get("trace") or "") if ch in "0123456789.+-eE")[:24]
    if trace:
        ET.SubElement(
            ink,
            "text",
            {
                "id": "numeric-trace",
                "x": "760",
                "y": "36",
                "font-size": "11",
                "font-family": "ui-monospace, monospace",
                "opacity": "0.55",
            },
        ).text = trace
    lines = [description] if description else []
    for line in (spec.get("lines") or [])[:5]:
        text = " ".join(str(line).split())[:72]
        if text:
            lines.append(text)
    for hit in (spec.get("vectors") or [])[:3]:
        if isinstance(hit, dict):
            label = " ".join(str(hit.get("label") or "").split())[:48]
            if label:
                lines.append(label)
    for i, line in enumerate(lines[:8]):
        ET.SubElement(
            ink,
            "text",
            {"x": "28", "y": str(460 + i * 9 - min(len(lines), 8) * 9), "font-size": "11", "font-family": "ui-monospace, monospace", "opacity": "0.75"},
        ).text = line
    body = ET.tostring(svg, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def svg_file_index(root: Path) -> int:
    best = 0
    try:
        found = list(root.glob("aura_dream_*.svg"))
    except OSError:
        return 1
    for path in found:
        tail = path.stem[len("aura_dream_") :]
        if tail.isdigit():
            best = max(best, int(tail))
    return best + 1


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------

class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self.load_high = False
        self.load_level = 0
        self._deferred: list[tuple[str, dict[str, Any]]] = []
        self._flushing = False

    def subscribe(self, *names: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        with self._lock:
            for name in names:
                self._subs.setdefault(name, []).append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            for name in list(self._subs):
                self._subs[name] = [q for q in self._subs[name] if q is not queue]

    def _note_load(self, body: dict[str, Any]) -> None:
        high = bool(body.get("high"))
        try:
            self.load_level = int(body.get("level") or 0)
        except (TypeError, ValueError):
            self.load_level = 0
        if self.load_high and not high:
            self.load_high = False
            self._flush_deferred()
        else:
            self.load_high = high

    def _emit(self, name: str, body: dict[str, Any]) -> None:
        stamped = stamp_authority(name, body)
        event = {"name": name, "t": time.monotonic(), "payload": stamped}
        with self._lock:
            targets = list(self._subs.get(name, ()))
        for queue in targets:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    def _flush_deferred(self) -> None:
        if self._flushing or not self._deferred:
            return
        self._flushing = True
        try:
            pending = self._deferred
            self._deferred = []
            for name, body in pending:
                self._emit(name, body)
        finally:
            self._flushing = False

    def publish(self, name: str, payload: dict[str, Any] | None = None) -> None:
        body = dict(payload or {})
        if name == "load":
            self._note_load(body)
        # A late tick batches the heavy optional notes. The spine does not wait.
        if self.load_high and not self._flushing and name in _LOAD_DEFER:
            self._deferred.append((name, body))
            limit = 16 if self.load_level >= 2 else 8
            if len(self._deferred) >= limit:
                self._flush_deferred()
            return
        self._emit(name, body)
        if name in ("tick", "shutdown") and self._deferred and not self._flushing:
            self._flush_deferred()


async def wait_evt(queue: asyncio.Queue, timeout: float) -> dict[str, Any] | None:
    try:
        return await asyncio.wait_for(queue.get(), max(0.0, timeout))
    except asyncio.TimeoutError:
        return None


def drain_nowait(queue: asyncio.Queue) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return items


def silence_task(task: asyncio.Task) -> None:
    if not task.done():
        return
    with suppress(asyncio.CancelledError, asyncio.InvalidStateError):
        task.exception()


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class Agent:
    name = "agent"
    core = True

    def __init__(self, params: dict[str, float] | None = None):
        self.params = dict(params or {"fault": 0.0, "tempo": 1.0})
        self.id = f"{self.name}-{os.urandom(3).hex()}"
        self.born = time.monotonic()
        self._next_beat = time.monotonic() + 0.8
        self._queue: asyncio.Queue | None = None
        self.scout_id: str | None = None
        self.partial: dict[str, Any] | None = None
        # Shedding stays off until a load event says the tick is late.
        self.load_high = False
        self.load_level = 0
        self.load_skip = 1
        self.load_thin = False
        self.load_pause = False
        # Sleep stays off until enter_sleep. Direct calls keep the old rates.
        self.sleeping = False
        self.sleep_ease = 0
        self.sleep_restore = 0

    def notice_load(self, payload: dict[str, Any]) -> None:
        """Copy a load event. A quiet payload leaves the previous flags down."""

        self.load_high = bool(payload.get("high"))
        try:
            self.load_level = int(payload.get("level") or 0)
        except (TypeError, ValueError):
            self.load_level = 0
        try:
            skip = int(payload.get("skip") or 1)
        except (TypeError, ValueError):
            skip = 1
        self.load_skip = skip if skip >= 1 else 1
        self.load_thin = bool(payload.get("thin"))
        self.load_pause = bool(payload.get("pause"))

    def notice_sleep(self, name: str, payload: dict[str, Any]) -> None:
        """Copy a sleep event. Awake stays awake until enter_sleep. No roll."""

        if name == "enter_sleep":
            self.sleeping = True
            self.sleep_ease = 1
            self.sleep_restore = 0
            return
        if name == "wake":
            self.sleeping = False
            self.sleep_ease = 0
            try:
                restore = int(payload.get("restore") or 3)
            except (TypeError, ValueError):
                restore = 3
            self.sleep_restore = restore if restore > 0 else 3

    def pace(self, seconds: float) -> float:
        """Loop wait. Sleep stretches it. Awake returns the same seconds."""

        if self.sleeping:
            return float(seconds) * 6.0
        return float(seconds)

    @property
    def tempo(self) -> float:
        return max(0.35, float(self.params.get("tempo", 1.0)))

    def beat(self, bus: EventBus) -> None:
        now = time.monotonic()
        if now < self._next_beat:
            return
        self._next_beat = now + 0.8
        bus.publish(
            "heartbeat",
            {"agent": self.name, "id": self.id, "age": round(now - self.born, 3)},
        )
        fault = float(self.params.get("fault", 0.0))
        if fault > 0.0 and random.random() < fault:
            raise RuntimeError("shear")

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        raise NotImplementedError


def death_payload(agent: Agent, error: str, detail: str) -> dict[str, Any]:
    return {
        "agent": agent.name,
        "id": agent.id,
        "error": error,
        "detail": (detail or "")[:160],
        "params": dict(agent.params),
        "age": round(time.monotonic() - agent.born, 3),
        "scout_id": agent.scout_id,
        "partial": agent.partial,
    }


async def wrap(agent: Agent, bus: EventBus, stop: asyncio.Event) -> None:
    """One incarnation. Failure publishes agent_died and does not escape."""
    try:
        bus.publish(
            "heartbeat",
            {"agent": agent.name, "id": agent.id, "age": 0.0, "hello": True},
        )
        await agent.run(bus, stop)
        if agent.core and not stop.is_set():
            bus.publish("agent_died", death_payload(agent, "vanished", "returned"))
    except asyncio.CancelledError:
        if agent.core and not stop.is_set():
            bus.publish("agent_died", death_payload(agent, "stalled", "cancelled"))
        raise
    except Exception as exc:
        bus.publish("agent_died", death_payload(agent, type(exc).__name__, str(exc)))
    finally:
        flush = getattr(agent, "flush", None)
        if flush is not None:
            with suppress(Exception):
                flush()
        if agent._queue is not None:
            bus.unsubscribe(agent._queue)
            agent._queue = None


def ensure_stdin_pump(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> asyncio.Queue:
    """tty boundary, not an agent. The input agent is what emits keystroke."""
    global _stdin_queue, _stdin_thread
    with _stdin_guard:
        if _stdin_queue is None:
            _stdin_queue = asyncio.Queue(maxsize=256)
        if _stdin_thread is not None and _stdin_thread.is_alive():
            return _stdin_queue
        queue = _stdin_queue

        def reader() -> None:
            fd = sys.stdin.fileno()
            while not stop.is_set():
                try:
                    ready, _, _ = select.select([fd], [], [], 0.2)
                except (OSError, ValueError):
                    return
                if not ready:
                    continue
                try:
                    data = os.read(fd, 16)
                except OSError:
                    return
                if not data:
                    return

                def _put(buf: bytes = data) -> None:
                    try:
                        queue.put_nowait(buf)
                    except asyncio.QueueFull:
                        with suppress(asyncio.QueueEmpty):
                            queue.get_nowait()
                        with suppress(asyncio.QueueFull):
                            queue.put_nowait(buf)

                try:
                    loop.call_soon_threadsafe(_put)
                except RuntimeError:
                    return

        _stdin_thread = threading.Thread(target=reader, name="aura-stdin", daemon=True)
        _stdin_thread.start()
        return queue


class InputAgent(Agent):
    name = "input"

    def __init__(self, params: dict[str, float], visual: bool):
        super().__init__(params)
        self.visual = visual

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        if not self.visual:
            while not stop.is_set():
                self.beat(bus)
                await asyncio.sleep(0.4)
            return
        loop = asyncio.get_running_loop()
        raw = ensure_stdin_pump(loop, stop)
        while not stop.is_set():
            self.beat(bus)
            try:
                data = await asyncio.wait_for(raw.get(), 0.2)
            except asyncio.TimeoutError:
                continue
            text = data.decode("utf-8", "ignore")
            for ch in text:
                if ch in "\x03\x04":
                    continue
                bus.publish("keystroke", {"ch": ch, "code": ord(ch), "authority": "authority"})


class RenderAgent(Agent):
    name = "render"

    def __init__(self, params: dict[str, float], genome: Genome, visual: bool):
        super().__init__(params)
        self.genome = genome.copy()
        self.visual = visual
        self.ripples: list[dict[str, float]] = []
        self.frags: list[dict[str, Any]] = []
        self.thoughts: list[dict[str, Any]] = []
        self.dreams: list[dict[str, Any]] = []
        self.scars: list[dict[str, float]] = []
        self.flash = 0.0
        self.noise_boost = 0.0
        self.dream = 0.0
        self.dream_target = 0.0
        self.dream_until = 0.0
        self.scale = 1.0
        self.scale_target = 1.0
        self.scale_until = 0.0
        self.digit_boost = 0.0
        self.traces: list[dict[str, Any]] = []
        self.turbulence = 0.0
        self.motifs: list[dict[str, Any]] = []
        self.recall = 0.0
        self.recall_hue = 0.0
        self.recall_until = 0.0
        self.private_stash = ""
        self.flicker = 0.0
        self.flicker_until = 0.0
        self.tick_echo = 0.0
        self.tick_echo_until = 0.0
        self.tick_mark = ""
        self.feeling_trace = 0.0
        self.feeling_trace_until = 0.0
        self.feeling_mark = ""
        self.mirror_echo = 0.0
        self.mirror_echo_until = 0.0
        self.mirror_mark = ""
        self.seal_crack = 0.0
        self.rng = random.Random()
        self._glyph_sample = ""
        self.held: list[dict[str, Any]] = []
        self.verdicts: dict[str, tuple[float, dict[str, Any]]] = {}
        self.motes: list[dict[str, float]] = []
        self._last_t = time.monotonic()
        self._last_stats = 0.0
        self._entropy_used = 0
        self._draw_n = 0
        self._cached_frame = ""
        self._cached_entropy = 0.0
        self._cached_color = 0.0
        self._line_buf: list[str] = []
        self.dream_motes: list[dict[str, Any]] = []

    def _cast(self, fx: float, fy: float, auth: str, amplified: bool = False) -> None:
        """One ring. Authority is a tight solid block. Unauthority is late and offset."""

        if auth == "authority":
            self.ripples.append(
                {
                    "fx": fx % 1.0,
                    "fy": fy % 1.0,
                    "r": 0.12,
                    "life": 1.2 if amplified else 1.0,
                    "auth": "authority",
                    "amp": 1.0 if amplified else 0.0,
                }
            )
            self.flash = min(1.0, self.flash + (0.95 if amplified else 0.72))
        else:
            self.ripples.append(
                {
                    "fx": (fx + 0.034) % 1.0,
                    "fy": (fy + 0.02) % 1.0,
                    "r": -1.6,
                    "life": 0.78,
                    "auth": "unauthority",
                    "amp": 0.0,
                }
            )
            self.flash = min(1.0, self.flash + 0.22)

    def _residue_cast(self, fx: float, fy: float, depth: int = 0) -> None:
        """Slow double ring. The second layer lags behind the first."""

        echo_scale = 0.7 + self.genome.g("echo")
        life = 1.35 * echo_scale * max(0.45, 1.0 - 0.12 * max(0, depth))
        self.ripples.append(
            {
                "fx": fx % 1.0,
                "fy": fy % 1.0,
                "r": 0.2,
                "life": life,
                "auth": "residue",
                "amp": 0.0,
                "layer": 0.0,
            }
        )
        self.ripples.append(
            {
                "fx": (fx + 0.03) % 1.0,
                "fy": (fy + 0.018) % 1.0,
                "r": -0.9,
                "life": life,
                "auth": "residue",
                "amp": 0.0,
                "layer": 1.0,
            }
        )
        self.flash = min(1.0, self.flash + 0.12)

    def _hold(self, evt: dict[str, Any], kind: str) -> None:
        payload = evt.get("payload") or {}
        if kind in ("fragment", "thought", "dream") and not str(payload.get("text") or "").strip():
            return
        item = {
            "id": candidate_id(evt),
            "kind": kind,
            "payload": payload,
            "at": time.monotonic(),
        }
        self.held.append(item)
        self.held = self.held[-32:]
        self._consider(item["id"])

    def _consider(self, vid: str) -> None:
        verdict = self.verdicts.get(vid)
        if verdict is None:
            return
        item = None
        keep: list[dict[str, Any]] = []
        for held in self.held:
            if item is None and held["id"] == vid:
                item = held
                continue
            keep.append(held)
        if item is None:
            return
        self.held = keep
        self.verdicts.pop(vid, None)
        self._dispatch(item, verdict[1])

    def _on_verdict(self, payload: dict[str, Any]) -> None:
        kind = str(payload.get("kind") or "")
        if kind == "svg":
            self._dispatch(None, payload)
            return
        vid = str(payload.get("id") or "")
        self.verdicts[vid] = (time.monotonic(), payload)
        self._consider(vid)

    def _expire_held(self) -> None:
        now = time.monotonic()
        keep: list[dict[str, Any]] = []
        for item in self.held:
            if now - float(item["at"]) < 1.15:
                keep.append(item)
                continue
            # A residue ripple already landed when the event arrived. Expiry
            # leaves that ring and does not add a second mote.
            if item["kind"] != "residue":
                self._mote(item["payload"])
                if item["kind"] == "entropy":
                    self.noise_boost = max(self.noise_boost, 0.1)
            self.verdicts.pop(item["id"], None)
        self.held = keep
        self.verdicts = {key: value for key, value in self.verdicts.items() if now - value[0] < 1.6}

    def _mote(self, payload: dict[str, Any]) -> None:
        try:
            fx = float(payload.get("x"))
        except (TypeError, ValueError):
            fx = random.random()
        try:
            fy = float(payload.get("y"))
        except (TypeError, ValueError):
            fy = random.random()
        firm = payload.get("authority") == "authority" and not payload.get("collision")
        self.motes.append({"fx": fx % 1.0, "fy": fy % 1.0, "life": 0.62, "shift": 0.0 if firm else 1.0})
        self.motes = self.motes[-12:]

    def _acknowledge(self, payload: dict[str, Any]) -> None:
        try:
            fx = float(payload.get("x", 0.5))
        except (TypeError, ValueError):
            fx = 0.5
        try:
            fy = float(payload.get("y", 0.42))
        except (TypeError, ValueError):
            fy = 0.42
        self.flash = min(1.0, self.flash + 0.4)
        self.ripples.append(
            {
                "fx": fx % 1.0,
                "fy": fy % 1.0,
                "r": 0.08,
                "life": 0.28,
                "auth": "authority",
                "amp": 0.0,
            }
        )

    def _spike(self, payload: dict[str, Any]) -> None:
        if payload.get("authority") == "authority":
            self.flash = min(1.0, self.flash + 0.95)
            self.noise_boost = 1.0
        else:
            self.flash = min(1.0, self.flash + 0.35)
            self.noise_boost = max(self.noise_boost, 0.55)
        self._cast(
            random.random(),
            random.random(),
            str(payload.get("authority") or "unauthority"),
            bool(payload.get("amplified")),
        )

    def _show_text(self, kind: str, payload: dict[str, Any]) -> None:
        text = str(payload.get("text") or "")[:56]
        if not text:
            return
        if kind == "fragment":
            self.frags.append(
                {
                    "fx": float(payload.get("x", random.random())),
                    "fy": float(payload.get("y", random.random())),
                    "text": text[:36],
                    "life": 1.0,
                    "holes": list(payload.get("holes") or []),
                    "auth": "authority" if payload.get("authority") == "authority" else "unauthority",
                }
            )
            self.frags = self.frags[-5:]
            return
        if kind == "dream":
            self.dreams.append(
                {
                    "fx": float(payload.get("x", random.uniform(0.06, 0.38))),
                    "fy": float(payload.get("y", random.uniform(0.22, 0.7))),
                    "text": text,
                    "life": 1.0,
                }
            )
            self.dreams = self.dreams[-4:]
            return
        auth = "authority" if payload.get("authority") == "authority" and not payload.get("echo") else "unauthority"
        if auth == "authority":
            tone = hsv_to_rgb((self.genome.g("hue") + 0.04) % 1.0, 0.34, 0.78)
        else:
            tone = hsv_to_rgb((self.genome.g("hue") + 0.08) % 1.0, 0.08, 0.38)
        self.thoughts.append(
            {
                "fx": float(payload.get("x", random.uniform(0.04, 0.42))),
                "fy": float(payload.get("y", random.uniform(0.62, 0.92))),
                "text": text,
                "life": 1.0,
                "auth": auth,
                "ghost": 0 if auth == "authority" else 1,
                "tone": tone,
            }
        )
        self.thoughts = self.thoughts[-3:]

    def _ghost_line(self, payload: dict[str, Any]) -> None:
        """A returning line. Dim, shifted, with no authority flash."""

        text = str(payload.get("text") or "")[:56]
        if not text:
            return
        try:
            fx = float(payload.get("x", 0.2))
        except (TypeError, ValueError):
            fx = 0.2
        try:
            fy = float(payload.get("y", 0.72))
        except (TypeError, ValueError):
            fy = 0.72
        tone = hsv_to_rgb((self.genome.g("hue") + 0.48) % 1.0, 0.1, 0.36)
        self.thoughts.append(
            {
                "fx": fx,
                "fy": fy,
                "text": text,
                "life": 1.0,
                "auth": "unauthority",
                "ghost": 1,
                "tone": tone,
            }
        )
        self.thoughts = self.thoughts[-3:]

    def _push_trace(self, text: str, payload: dict[str, Any]) -> None:
        cleaned = "".join(ch for ch in text if ch in "0123456789.+-eE")[:12]
        if not cleaned:
            return
        try:
            fx = float(payload.get("x", 0.18))
        except (TypeError, ValueError):
            fx = 0.18
        try:
            fy = float(payload.get("y", 0.24))
        except (TypeError, ValueError):
            fy = 0.24
        self.traces.append({"text": cleaned, "life": 1.0, "fx": fx % 1.0, "fy": fy % 1.0})
        self.traces = self.traces[-4:]

    def _arm_scale(self, payload: dict[str, Any]) -> None:
        try:
            log = float(payload.get("log"))
        except (TypeError, ValueError):
            log = 0.0
        self.scale_target = visual_stretch(log)
        self.scale_until = time.monotonic() + 3.2

    def _show_math(self, kind: str, payload: dict[str, Any]) -> None:
        """A shown number. Stretch, digits, or a ghost. A suppressed one never gets here."""

        if kind == "math_dream":
            self._ghost_line(payload)
            return
        if kind == "resonance":
            self.flash = min(1.0, self.flash + 0.28)
            marker = str(payload.get("digits") or payload.get("text") or "")
            self._push_trace(marker, payload)
            return
        if kind == "scale":
            self._arm_scale(payload)
            try:
                log = float(payload.get("log") or 0.0)
            except (TypeError, ValueError):
                log = 0.0
            self._push_trace(f"{scale_magnitude(log):.0e}", payload)
            return
        self.digit_boost = min(1.0, self.digit_boost + 0.55)
        self._push_trace(str(payload.get("digits") or payload.get("text") or ""), payload)

    def _show_balance(self, kind: str, payload: dict[str, Any]) -> None:
        """A shown pattern. Repeating glyph, or a short turbulence of sparks.

        A suppressed reading never gets here. Turbulence at 0 paints nothing.
        """

        slip = bool(payload.get("slip") or payload.get("turbulence"))
        if kind == "control" and slip:
            self.turbulence = min(1.0, self.turbulence + 0.85)
            return
        if kind == "steady" and slip:
            self.turbulence = min(1.0, self.turbulence + 0.7)
            return
        try:
            fx = float(payload.get("x", 0.2))
        except (TypeError, ValueError):
            fx = 0.2
        try:
            fy = float(payload.get("y", 0.3))
        except (TypeError, ValueError):
            fy = 0.3
        glyph = "░" if kind == "control" else "▓"
        self.motifs.append({"glyph": glyph, "fx": fx % 1.0, "fy": fy % 1.0, "life": 1.0, "n": 5})
        self.motifs = self.motifs[-4:]

    def _show_cache(self, kind: str, payload: dict[str, Any]) -> None:
        """A shown cache. A write is a mote. A recall echoes a few sparks.

        Suppressed and expired recalls do not come here, so the hue echo stays off.
        """

        if kind != "recall":
            self._mote(payload)
            return
        genes = payload.get("genes") if isinstance(payload.get("genes"), list) else []
        try:
            hue = float(payload.get("hue"))
        except (TypeError, ValueError):
            try:
                hue = float(genes[0]) if genes else self.genome.g("hue")
            except (TypeError, ValueError, IndexError):
                hue = self.genome.g("hue")
        self.recall_hue = hue % 1.0
        self.recall = 1.0
        self.recall_until = time.monotonic() + 1.35

    def _cell(
        self,
        x: int,
        y: int,
        t: float,
        cols: int,
        rows: int,
        void: tuple[int, int, int],
    ) -> tuple[str, tuple[int, int, int]]:
        picked = sample_xy(x, y, self.scale, cols, rows)
        if picked is None:
            return " ", void
        return field_cell(picked[0], picked[1], t, self.genome, cols, rows)

    def _dispatch(self, item: dict[str, Any] | None, verdict: dict[str, Any]) -> None:
        payload = item["payload"] if item is not None else verdict
        kind = str(verdict.get("kind") or (item or {}).get("kind") or "")
        if kind == "residue":
            if verdict.get("show"):
                self._ghost_line(payload)
            return
        if kind in ("pi", "pattern", "scale", "resonance", "math_dream"):
            if verdict.get("show"):
                self._show_math(kind, payload)
            else:
                self._mote(payload)
            return
        if kind in ("motif", "steady", "balance", "control"):
            if verdict.get("show"):
                self._show_balance(kind, payload)
            else:
                self._mote(payload)
            return
        if kind in ("cache", "recall"):
            if verdict.get("show"):
                self._show_cache(kind, payload)
            else:
                self._mote(payload)
            return
        if kind == "private":
            return
        if verdict.get("show"):
            if kind == "entropy":
                self._spike(payload)
            elif kind in ("fragment", "thought", "dream"):
                self._acknowledge(payload)
                self._show_text(kind, payload)
            else:
                self._acknowledge(payload)
            return
        self._mote(payload)
        if kind == "entropy":
            self.noise_boost = max(self.noise_boost, 0.1)

    def _on(self, evt: dict[str, Any]) -> bool:
        name = evt["name"]
        payload = evt["payload"]
        if name == "shutdown":
            return False
        if name == "load":
            self.notice_load(payload)
            return True
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            if name == "wake":
                self.dream_motes.clear()
            return True
        if name in ("possible_activity", "dreamed_input"):
            self._note_dream_mote(payload)
            return True
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
        elif name == "keystroke":
            code = int(payload.get("code") or 32)
            self._cast(
                (code % 97) / 97.0,
                ((code * 7) % 89) / 89.0,
                str(payload.get("authority") or "authority"),
                bool(payload.get("amplified")),
            )
        elif name == "inject":
            code = int(payload.get("code") or 32)
            self._cast(
                float(payload.get("x", (code % 97) / 97.0)),
                float(payload.get("y", ((code * 7) % 89) / 89.0)),
                str(payload.get("authority") or "authority"),
                bool(payload.get("amplified")),
            )
        elif name == "residue":
            self.seal_crack = 0.06
            try:
                fx = float(payload.get("x"))
            except (TypeError, ValueError):
                fx = random.random()
            try:
                fy = float(payload.get("y"))
            except (TypeError, ValueError):
                fy = random.random()
            try:
                depth = int(payload.get("depth") or 0)
            except (TypeError, ValueError):
                depth = 0
            self._residue_cast(fx, fy, depth)
            if str(payload.get("text") or "").strip():
                self._hold(evt, "residue")
        elif name == "fragment_ready":
            self._hold(evt, "fragment")
        elif name == "entropy_spike":
            if self.load_high:
                cap = 1 if self.load_level >= 2 else 2
                if self._entropy_used < cap:
                    self._entropy_used += 1
                    self._hold(evt, "entropy")
            else:
                self._hold(evt, "entropy")
        elif name == "thought":
            self._hold(evt, "thought")
        elif name == "conflict":
            self._hold(evt, "conflict")
            self._arm_flicker()
        elif name == "private_thought":
            text = " ".join(str(payload.get("text") or "").split())[:56]
            if text:
                self.private_stash = text
        elif name == "mirror_truth":
            self._arm_mirror(payload)
        elif name == "tick":
            self._entropy_used = 0
            if payload.get("resumed"):
                mark = "".join(ch for ch in str(payload.get("continuity") or "").lower() if ch in "0123456789abcdef")[:8]
                if mark:
                    self.tick_mark = mark
                    self.tick_echo = 0.28
                    self.tick_echo_until = time.monotonic() + 0.28
        elif name in FEELING_EVENTS:
            if name == "approbation_marked":
                self._arm_feeling(payload)
        elif name == "valuation":
            self._on_verdict(payload)
        elif name == "dream_begin":
            self.dream_target = 1.0
            self.dream_until = time.monotonic() + float(payload.get("seconds") or 8.0)
        elif name == "dream_end":
            self.dream_target = 0.0
        elif name == "dream_scene":
            self._hold(evt, "dream")
        elif name in _MATH_KIND:
            self._hold(evt, _MATH_KIND[name])
        elif name in _BALANCE_KIND:
            self._hold(evt, _BALANCE_KIND[name])
            if name == "control_loss":
                self._arm_flicker()
        elif name in _CACHE_KIND:
            self._hold(evt, _CACHE_KIND[name])
        elif name == "vector_match" and payload.get("hits"):
            label = str(payload["hits"][0].get("label") or "")
            mix = sum(ord(ch) for ch in label) or 1
            self._cast(
                (mix % 1000) / 1000.0,
                ((mix * 3) % 1000) / 1000.0,
                str(payload.get("authority") or "unauthority"),
                bool(payload.get("amplified")),
            )
        elif name == "agent_died" and payload.get("agent") != "scout":
            self.scars.append({"fx": random.random(), "fy": random.random(), "life": 1.0})
            self._cast(random.random(), random.random(), "unauthority")
        if len(self.ripples) > 18:
            self.ripples = self.ripples[-14:]
        if len(self.frags) > 5:
            self.frags = self.frags[-5:]
        if len(self.thoughts) > 3:
            self.thoughts = self.thoughts[-3:]
        if len(self.dreams) > 4:
            self.dreams = self.dreams[-4:]
        if len(self.scars) > 8:
            self.scars = self.scars[-8:]
        return True

    def _decay(self, dt: float) -> None:
        # Sleep keeps marks longer. Awake uses the same dt as before.
        if self.sleeping:
            dt *= 0.28
        decay = 0.45 + self.genome.g("decay") * 1.15
        spread = 9.0 + self.genome.g("ripple") * 20.0
        for rip in self.ripples:
            if rip.get("auth") == "unauthority":
                rip["life"] -= dt * decay * 1.35
                rip["r"] += dt * (spread * 0.62)
            elif rip.get("auth") == "residue":
                rip["life"] -= dt * decay * 0.42
                rip["r"] += dt * (spread * 0.38)
            else:
                rip["life"] -= dt * decay * 0.85
                rip["r"] += dt * (spread * 1.15)
        self.ripples = [rip for rip in self.ripples if rip["life"] > 0.0]
        fade = 0.16 + self.genome.g("decay") * 0.42
        for frag in self.frags:
            frag["life"] -= dt * fade
        self.frags = [frag for frag in self.frags if frag["life"] > 0.0]
        for line in self.thoughts:
            line["life"] -= dt * 0.1
            line["fy"] = max(0.02, float(line["fy"]) - dt * 0.012)
        self.thoughts = [line for line in self.thoughts if line["life"] > 0.0]
        for line in self.dreams:
            line["life"] -= dt * (0.055 + 0.05 * (1.0 - self.dream))
        self.dreams = [line for line in self.dreams if line["life"] > 0.0]
        if self.dream < 0.04 and self.dream_target <= 0.0:
            self.dreams.clear()
        if self.dream_target > 0.0 and time.monotonic() > self.dream_until:
            self.dream_target = 0.0
        self.dream += (self.dream_target - self.dream) * min(1.0, dt * 1.5)
        for scar in self.scars:
            scar["life"] -= dt * 0.35
        self.scars = [scar for scar in self.scars if scar["life"] > 0.0]
        for mote in self.motes:
            mote["life"] -= dt * 1.4
        self.motes = [mote for mote in self.motes if mote["life"] > 0.0]
        self.flash = max(0.0, self.flash - dt * 1.7)
        self.noise_boost = max(0.0, self.noise_boost - dt * 1.35)
        if time.monotonic() > self.scale_until:
            self.scale_target = 1.0
        self.scale += (self.scale_target - self.scale) * min(1.0, dt * 1.6)
        if abs(self.scale - 1.0) < 1e-3 and abs(self.scale_target - 1.0) < 1e-3:
            self.scale = 1.0
        self.digit_boost = max(0.0, self.digit_boost - dt * 0.45)
        self.turbulence = max(0.0, self.turbulence - dt * 0.55)
        if self.recall > 0.0 and time.monotonic() > self.recall_until:
            self.recall = 0.0
        elif self.recall > 0.0:
            self.recall = max(0.0, self.recall - dt * 0.4)
        if self.flicker > 0.0 and time.monotonic() >= self.flicker_until:
            self.flicker = 0.0
        elif self.flicker > 0.0:
            self.flicker = max(0.0, self.flicker - dt * 4.0)
        if self.tick_echo > 0.0 and time.monotonic() >= self.tick_echo_until:
            self.tick_echo = 0.0
        elif self.tick_echo > 0.0:
            self.tick_echo = max(0.0, self.tick_echo - dt * 4.0)
        if self.feeling_trace > 0.0 and time.monotonic() >= self.feeling_trace_until:
            self.feeling_trace = 0.0
        elif self.feeling_trace > 0.0:
            self.feeling_trace = max(0.0, self.feeling_trace - dt * 4.0)
        if self.mirror_echo > 0.0 and time.monotonic() >= self.mirror_echo_until:
            self.mirror_echo = 0.0
        elif self.mirror_echo > 0.0:
            self.mirror_echo = max(0.0, self.mirror_echo - dt * 4.0)
        for motif in self.motifs:
            motif["life"] = float(motif.get("life") or 0.0) - dt * 0.4
        self.motifs = [motif for motif in self.motifs if float(motif["life"]) > 0.0]
        for trace in self.traces:
            trace["life"] = float(trace.get("life") or 0.0) - dt * 0.4
        self.traces = [trace for trace in self.traces if float(trace["life"]) > 0.0]
        if self.dream_motes:
            for mote in self.dream_motes:
                mote["life"] = float(mote.get("life") or 0.0) - dt * 0.15
            self.dream_motes = [mote for mote in self.dream_motes if float(mote["life"]) > 0.0]

    def _note_dream_mote(self, payload: dict[str, Any]) -> None:
        """A dreamed activity may leave one dim mote. No roll."""

        kind = "".join(ch for ch in str(payload.get("kind") or "dream") if ch.isalnum())[:12] or "dream"
        self.dream_motes.append({"kind": kind, "life": 0.9})
        self.dream_motes = self.dream_motes[-4:]

    def _paint_sleep(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
        void: tuple[int, int, int],
    ) -> None:
        """Sparse, slow, dim. Awake returns before a cell changes."""

        if not self.sleeping or cols < 1 or rows < 1:
            return
        for y in range(rows):
            for x in range(cols):
                char, fg = cells[y][x]
                if char != " " and ((x * 3 + y) % 5) != 0:
                    char = " "
                cells[y][x] = (char, mix_rgb(fg, void, 0.78))

    def _paint_dream_motes(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
    ) -> None:
        """Light perturbation from dreamed activity. An empty list changes nothing."""

        if not self.dream_motes or cols < 1 or rows < 1:
            return
        tone = hsv_to_rgb(0.62, 0.08, 0.22)
        for mote in self.dream_motes:
            acc = 0
            for ch in str(mote.get("kind") or ""):
                acc = (acc * 17 + ord(ch)) & 0xFFFF
            x = acc % cols
            y = (acc // 7) % rows
            cells[y][x] = ("·", tone)

    def _paint_ripples(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
        t: float,
    ) -> None:
        """Authority blocks, unauthority sparks, and residue marks share the field.

        A spark or a residue mark that would erase a block is stepped one cell
        aside. Residue is a dim dot or spark, slower than a keystroke block.
        Nothing is chosen as the real mark.
        """

        genome = self.genome
        ghosts: list[tuple[int, int, str, tuple[int, int, int]]] = []
        residue_marks: list[tuple[int, int, str, tuple[int, int, int]]] = []
        for y in range(rows):
            for x in range(cols):
                auth_rip = None
                ghost_rip = None
                residue_rip = None
                for rip in self.ripples:
                    if float(rip.get("r", 0.0)) < 0.0:
                        continue
                    dx = x - float(rip["fx"]) * cols
                    dy = (y - float(rip["fy"]) * rows) * 2.0
                    dist = math.hypot(dx, dy)
                    kind = rip.get("auth")
                    if kind == "unauthority":
                        band = 1.7
                    elif kind == "residue":
                        band = 1.25
                    elif rip.get("amp"):
                        band = 0.48
                    else:
                        band = 0.68
                    if abs(dist - float(rip["r"])) < band:
                        if kind == "unauthority":
                            ghost_rip = rip
                        elif kind == "residue":
                            residue_rip = rip
                        else:
                            auth_rip = rip
                char, fg = cells[y][x]
                sparked = False
                if ghost_rip is not None:
                    flick = hashmix(x, y, int(t * 17) + int(float(ghost_rip["r"]) * 10))
                    if flick > 0.3:
                        spark = SPARKS[int(flick * 997) % len(SPARKS)]
                        ghost_fg = hsv_to_rgb((genome.g("hue") + 0.62) % 1.0, 0.14, 0.46)
                        if auth_rip is not None:
                            gx = x + 1 if x + 1 < cols else x - 1
                            if gx != x:
                                ghosts.append((gx, y, spark, ghost_fg))
                        else:
                            char = spark
                            fg = ghost_fg
                            sparked = True
                            if flick > 0.8:
                                gx = x + 1 if x + 1 < cols else x - 1
                                if gx != x:
                                    ghosts.append((gx, y, SPARKS[int(flick * 13) % len(SPARKS)], ghost_fg))
                if residue_rip is not None:
                    flick = hashmix(x, y, int(t * 9) + int(float(residue_rip["r"]) * 6))
                    mark = "·" if flick < 0.58 else SPARKS[int(flick * 997) % len(SPARKS)]
                    residue_fg = hsv_to_rgb((genome.g("hue") + 0.48) % 1.0, 0.16, 0.36)
                    if auth_rip is not None or sparked:
                        rx = x + 1 if x + 1 < cols else x - 1
                        if rx != x:
                            residue_marks.append((rx, y, mark, residue_fg))
                    else:
                        char = mark
                        fg = residue_fg
                if auth_rip is not None:
                    level = 3 if auth_rip.get("amp") else int(clamp01(float(auth_rip["life"])) * 3.99)
                    char = BLOCKS[max(0, min(3, level))]
                    sat = 0.95 if auth_rip.get("amp") else 0.8
                    fg = hsv_to_rgb((genome.g("hue") + 0.04) % 1.0, sat, 1.0)
                cells[y][x] = (char, fg)
        for gx, gy, gch, gfg in ghosts:
            if not (0 <= gx < cols and 0 <= gy < rows):
                continue
            if cells[gy][gx][0] in BLOCKS:
                nxt = gx + 1 if gx + 1 < cols else gx - 1
                if nxt != gx and cells[gy][nxt][0] not in BLOCKS:
                    gx = nxt
            cells[gy][gx] = (gch, gfg)
        for rx, ry, mch, mfg in residue_marks:
            if not (0 <= rx < cols and 0 <= ry < rows):
                continue
            if cells[ry][rx][0] in BLOCKS:
                nxt = rx + 1 if rx + 1 < cols else rx - 1
                if nxt != rx and cells[ry][nxt][0] not in BLOCKS:
                    rx = nxt
                else:
                    continue
            if cells[ry][rx][0] in BLOCKS:
                continue
            cells[ry][rx] = (mch, mfg)

    def _paint_motes(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
        t: float,
    ) -> None:
        """Suppressed events touch one cell. They do not become words."""

        for mote in self.motes:
            x = int(clamp(float(mote["fx"]), 0.0, 0.999) * max(1, cols - 1))
            y = int(clamp(float(mote["fy"]), 0.0, 0.999) * max(1, rows - 1))
            if mote.get("shift"):
                x = min(cols - 1, x + 1)
            char, fg = cells[y][x]
            nudged = tuple(min(255, channel + 14) for channel in fg)
            if char == " " and hashmix(x, y, int(t * 23)) > 0.72:
                char = "·"
                nudged = hsv_to_rgb((self.genome.g("hue") + 0.5) % 1.0, 0.08, 0.22)
            cells[y][x] = (char, nudged)

    def _paint_turbulence(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
        t: float,
    ) -> None:
        """Offset sparks. At zero this returns before touching a cell."""

        if self.turbulence <= 0.0 or cols < 2 or rows < 1:
            return
        strength = self.turbulence
        gate = 0.72 + 0.2 * (1.0 - strength)
        tone = hsv_to_rgb((self.genome.g("hue") + 0.62) % 1.0, 0.22, 0.55)
        for y in range(0, rows, 3):
            for x in range(0, cols, 3):
                if hashmix(x, y, int(t * 19)) > gate:
                    continue
                nx = x + 1 if x + 1 < cols else x - 1
                if nx == x or cells[y][nx][0] in BLOCKS:
                    continue
                spark = SPARKS[int(hashmix(x, y, 3) * 97) % len(SPARKS)]
                cells[y][nx] = (spark, tone)

    def _paint_motifs(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
    ) -> None:
        """A short repeating glyph. Empty when no pattern has been shown."""

        if not self.motifs or cols < 1 or rows < 1:
            return
        tone = hsv_to_rgb((self.genome.g("hue") + 0.08) % 1.0, 0.35, 0.72)
        for motif in self.motifs:
            glyph = str(motif.get("glyph") or "▓")[:1] or "▓"
            try:
                count = int(motif.get("n") or 4)
            except (TypeError, ValueError):
                count = 4
            y = int(clamp(float(motif.get("fy") or 0.3), 0.0, 0.999) * (rows - 1))
            x0 = int(clamp(float(motif.get("fx") or 0.2), 0.0, 0.999) * max(1, cols - 1))
            for i in range(max(1, count)):
                x = x0 + i * 2
                if x >= cols or cells[y][x][0] in BLOCKS:
                    continue
                cells[y][x] = (glyph, tone)

    def _paint_recall(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
        t: float,
    ) -> None:
        """A few sparks in a recalled hue. At zero this returns before a cell changes."""

        if self.recall <= 0.0 or cols < 2 or rows < 1:
            return
        tone = hsv_to_rgb(self.recall_hue % 1.0, 0.2, 0.42)
        painted = 0
        for y in range(0, rows, 4):
            for x in range(1, cols, 7):
                if hashmix(x, y, int(t * 5) + 11) < 0.82:
                    continue
                if cells[y][x][0] in BLOCKS:
                    continue
                cells[y][x] = ("+", tone)
                painted += 1
                if painted >= 4:
                    return

    def _arm_flicker(self) -> None:
        """One near-invisible line. A sealed genome, or an empty stash, leaves the rng alone."""

        sealed = self.genome.g("privacy_bias") - self.seal_crack >= PRIVACY_SEAL
        if sealed or not self.private_stash:
            if sealed:
                self.seal_crack = 0.0
            return
        self.seal_crack = 0.0
        if self.rng.random() > (1.0 - self.genome.g("privacy_bias")) * 0.55:
            return
        self.flicker = 0.35
        self.flicker_until = time.monotonic() + 0.35

    def _paint_flicker(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
    ) -> None:
        """A private line at almost no contrast. At zero this returns before a cell changes."""

        if self.flicker <= 0.0 or not self.private_stash or cols < 1 or rows < 1:
            return
        tone = hsv_to_rgb((self.genome.g("hue") + 0.04) % 1.0, 0.02, 0.075)
        text = self.private_stash
        y = min(rows - 1, max(0, rows // 5))
        for i, ch in enumerate(text[:cols]):
            if ch == " " or cells[y][i][0] in BLOCKS:
                continue
            cells[y][i] = (ch, tone)

    def _paint_tick_echo(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
    ) -> None:
        """A faint echo of the last continuity mark. At zero this returns at once."""

        if self.tick_echo <= 0.0 or not self.tick_mark or cols < 1 or rows < 1:
            return
        tone = hsv_to_rgb((self.genome.g("hue") + 0.02) % 1.0, 0.02, 0.06)
        y = min(rows - 1, max(0, rows - 2))
        for i, ch in enumerate(self.tick_mark[:8]):
            if i >= cols or cells[y][i][0] in BLOCKS:
                continue
            cells[y][i] = (ch, tone)

    def _arm_feeling(self, payload: dict[str, Any]) -> None:
        """A faint trace. High hold and high worth only. No roll, and no sentence."""

        if self.genome.g("feeling_gain") <= 0.0:
            return
        try:
            held = float(payload.get("held") or 0.0)
            worth = float(payload.get("worth") or 0.0)
        except (TypeError, ValueError):
            return
        if held < FEELING_HELD_LEAK or worth < FEELING_WORTH_LEAK:
            return
        mark = feel_token(payload.get("ref"), 8)
        if not mark or mark.startswith("fp"):
            return
        self.feeling_mark = mark
        self.feeling_trace = 0.22
        self.feeling_trace_until = time.monotonic() + 0.22

    def _arm_mirror(self, payload: dict[str, Any]) -> None:
        # A brief paired echo. No roll, and nothing when the return is unmarked.

        if not payload.get("mirror") and not str(payload.get("ref") or "").startswith("mirror:"):
            return
        mark = mirror_token(payload.get("text") or payload.get("ref"))[:8]
        if not mark:
            return
        self.mirror_mark = mark
        self.mirror_echo = 0.34
        self.mirror_echo_until = time.monotonic() + 0.34

    def _paint_mirror_echo(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
    ) -> None:
        # One offset copy of a cell. At zero this returns before a cell changes.

        if self.mirror_echo <= 0.0 or cols < 1 or rows < 1:
            return
        tone = hsv_to_rgb((self.genome.g("hue") + 0.5) % 1.0, 0.04, 0.08)
        acc = 0
        for ch in self.mirror_mark or "m":
            acc = (acc * 17 + ord(ch)) & 0xFFFF
        x = acc % cols
        y = (acc // 5) % rows
        char = cells[y][x][0]
        if char == " ":
            char = "·"
        ox = x + 1 if x + 1 < cols else x - 1
        if cells[y][ox][0] not in BLOCKS:
            cells[y][ox] = (char, tone)

    def _paint_feeling_trace(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
    ) -> None:
        """One dim mark. At zero this returns before a cell changes."""

        if self.feeling_trace <= 0.0 or not self.feeling_mark or cols < 1 or rows < 1:
            return
        tone = hsv_to_rgb((self.genome.g("hue") + 0.08) % 1.0, 0.02, 0.05)
        y = min(rows - 1, max(0, rows // 3))
        x = min(cols - 1, 1)
        cells[y][x] = ("·", tone)

    def _frame(self, cols: int, rows: int, t: float) -> tuple[str, float, float]:
        genome = self.genome
        void = void_color(genome)
        veil = None
        if self.dream > 0.04:
            veil = hsv_to_rgb(0.73 + 0.05 * math.sin(t * 0.33), 0.34, 0.48 + 0.08 * math.sin(t * 0.7))
            void = mix_rgb(void, hsv_to_rgb(0.74, 0.55, 0.07), self.dream * 0.75)
        scan = int((t * (1.15 + genome.g("wave_speed") * (1.0 - 0.65 * self.dream))) % rows)
        veil_y = int((t * 0.22) % rows) if veil is not None else -1
        cells: list[list[tuple[str, tuple[int, int, int]]]] = []
        chars: list[str] = []
        lights: list[float] = []
        lift = int(80 * self.flash)
        spark_left = None
        if self.load_high:
            spark_left = 6 if self.load_level >= 2 else 18
        for y in range(rows):
            row: list[tuple[str, tuple[int, int, int]]] = []
            for x in range(cols):
                # A late extreme tick keeps the wave, and drops two cells in three.
                if self.load_thin and ((x + y * 3) % 3) != 0:
                    row.append((" ", void))
                    continue
                char, fg = self._cell(x, y, t, cols, rows, void)
                if self.digit_boost > 0.08:
                    if hashmix(x, y, int(t * 11)) > 0.94:
                        char = "0123456789"[int(hashmix(x, y, 7) * 10) % 10]
                    fg = mix_rgb(fg, hsv_to_rgb((genome.g("hue") + 0.17) % 1.0, 0.35, 0.7), self.digit_boost * 0.22)
                if self.noise_boost > 0.15 and hashmix(x, y, int(t * 30)) > 0.86:
                    if spark_left is None or spark_left > 0:
                        char = SPARKS[x % len(SPARKS)]
                        fg = hsv_to_rgb(0.52, 0.2, 1.0)
                        if spark_left is not None:
                            spark_left -= 1
                row.append((char, fg))
            cells.append(row)
        self._paint_ripples(cells, cols, rows, t)
        for y in range(rows):
            for x in range(cols):
                char, fg = cells[y][x]
                if veil is not None:
                    if hashmix(x, y, int(t * 2)) > 0.955:
                        char = "."
                    fg = mix_rgb(fg, veil, self.dream * 0.38)
                    if y == veil_y and char != " ":
                        fg = tuple(min(255, c + 28) for c in fg)  # type: ignore[assignment]
                if y == scan and char != " ":
                    fg = tuple(min(255, c + 36) for c in fg)  # type: ignore[assignment]
                if lift:
                    fg = tuple(min(255, c + lift) for c in fg)  # type: ignore[assignment]
                cells[y][x] = (char, fg)
                if ((x + y) & 3) == 0:
                    chars.append(char)
                    lights.append(luminance(fg))
        self._glyph_sample = "".join(chars[:24])
        self._paint_motes(cells, cols, rows, t)
        self._paint_turbulence(cells, cols, rows, t)
        self._paint_motifs(cells, cols, rows)
        self._paint_recall(cells, cols, rows, t)
        self._paint_flicker(cells, cols, rows)
        self._paint_tick_echo(cells, cols, rows)
        self._paint_feeling_trace(cells, cols, rows)
        self._paint_mirror_echo(cells, cols, rows)
        trace_tone = hsv_to_rgb((genome.g("hue") + 0.17) % 1.0, 0.42, 0.72)
        for trace in self.traces:
            text = str(trace.get("text") or "")
            y = int(clamp(float(trace.get("fy") or 0.3), 0.0, 0.999) * (rows - 1))
            x0 = int(clamp(float(trace.get("fx") or 0.15), 0.0, 0.999) * max(1, cols - 1))
            for i, ch in enumerate(text):
                if ch not in "0123456789.+-eE":
                    continue
                x = x0 + i
                if x >= cols or cells[y][x][0] in BLOCKS:
                    continue
                cells[y][x] = (ch, trace_tone)
        ordered = sorted(self.frags, key=lambda frag: 0 if frag.get("auth") == "unauthority" else 1)
        for frag in ordered:
            text = str(frag["text"])
            if not text:
                continue
            y = int(clamp(frag["fy"], 0.0, 0.999) * (rows - 1))
            x0 = int(clamp(frag["fx"], 0.0, 0.999) * max(1, cols - 1))
            holes = frag.get("holes") or []
            firm = frag.get("auth") == "authority"
            if firm:
                tone = hsv_to_rgb((genome.g("hue") + 0.02) % 1.0, 0.55, 0.98)
            else:
                tone = hsv_to_rgb((genome.g("hue") + 0.55) % 1.0, 0.14, 0.48)
            for i, ch in enumerate(text):
                x = x0 + i
                if x >= cols or ch == " ":
                    continue
                if i < len(holes) and holes[i]:
                    continue
                if not firm and hashmix(x, y, int(t * 13) + i) < 0.38:
                    gy = y + 1 if y + 1 < rows else y - 1
                    gx = x + 1 if x + 1 < cols else x - 1
                    if 0 <= gx < cols and 0 <= gy < rows and cells[gy][gx][0] not in BLOCKS:
                        cells[gy][gx] = (ch, tone)
                    continue
                cells[y][x] = (ch, tone)
                if not firm and y + 1 < rows and i % 2 == 0 and cells[y + 1][x][0] not in BLOCKS:
                    cells[y + 1][x] = (ch, tone)
        thought_tone = hsv_to_rgb((genome.g("hue") + 0.06) % 1.0, 0.12, 0.5)
        self._lay(cells, self.thoughts, cols, rows, thought_tone)
        dream_tone = hsv_to_rgb(0.74, 0.16, 0.9)
        self._lay(cells, self.dreams, cols, rows, dream_tone)
        self._paint_sleep(cells, cols, rows, void)
        self._paint_dream_motes(cells, cols, rows)
        for scar in self.scars:
            x = int(scar["fx"] * (cols - 1))
            y = int(scar["fy"] * (rows - 1))
            if hashmix(x, y, int(t * 14)) > 0.4:
                cells[y][x] = ("#", (176, 132, 154))
            gx = x + 1 if x + 1 < cols else x - 1
            if gx != x and hashmix(gx, y, int(t * 11) + 3) > 0.52 and cells[y][gx][0] not in BLOCKS:
                cells[y][gx] = (SPARKS[(x + y) % len(SPARKS)], (120, 96, 128))
        return paint(cells, void), shannon_norm(chars), clamp(variance(lights) * 8.0, 0.0, 1.5)

    @staticmethod
    def _lay(
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        lines: list[dict[str, Any]],
        cols: int,
        rows: int,
        tone: tuple[int, int, int],
    ) -> None:
        for line in lines:
            text = str(line.get("text") or "")
            if not text:
                continue
            y = int(clamp(float(line["fy"]), 0.0, 0.999) * (rows - 1))
            shift = int(line.get("ghost") or 0)
            x0 = int(clamp(float(line["fx"]), 0.0, 0.999) * max(1, cols - 1)) + shift
            use = line.get("tone") or tone
            for i, ch in enumerate(text):
                x = x0 + i
                if x >= cols or x < 0 or ch == " ":
                    continue
                cells[y][x] = (ch, use)

    def _blit(self, frame: str) -> None:
        """Full frame while the tick is on time. A late tick rewrites only dirty lines."""

        if not self.load_high or not self._line_buf:
            sys.stdout.write(frame)
            sys.stdout.flush()
            if self.load_high:
                self._line_buf = frame.split("\n")
            return
        lines = frame.split("\n")
        if len(lines) != len(self._line_buf):
            sys.stdout.write(frame)
            sys.stdout.flush()
            self._line_buf = lines
            return
        parts: list[str] = []
        for index, line in enumerate(lines):
            if line != self._line_buf[index]:
                parts.append(f"\033[{index + 1};1H{line}")
        self._line_buf = lines
        if parts:
            sys.stdout.write("".join(parts))
            sys.stdout.flush()

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "keystroke",
            "fragment_ready",
            "mutation_applied",
            "generation_complete",
            "vector_match",
            "entropy_spike",
            "agent_died",
            "thought",
            "dream_begin",
            "dream_scene",
            "dream_end",
            "inject",
            "conflict",
            "valuation",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "private_thought",
            "tick",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "possible_activity",
            "dreamed_input",
            "mirror_truth",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.064 / self.tempo))
            drained = 0
            while evt is not None and drained < 30:
                if not self._on(evt):
                    return
                drained += 1
                try:
                    evt = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    evt = None
            now = time.monotonic()
            dt = clamp(now - self._last_t, 0.0, 0.12)
            self._last_t = now
            self._expire_held()
            self._decay(dt)
            cols, rows = terminal_size()
            draw = True
            skip = self.load_skip if self.load_high and self.load_skip > 1 else 1
            if self.sleeping:
                skip = max(skip, 6)
            if skip > 1:
                draw = self._draw_n % skip == 0
                self._draw_n += 1
            if draw or not self._cached_frame:
                frame, entropy, color_var = self._frame(cols, rows, time.monotonic() - AURA_T0)
                self._cached_frame = frame
                self._cached_entropy = entropy
                self._cached_color = color_var
            else:
                frame = self._cached_frame
                entropy = self._cached_entropy
                color_var = self._cached_color
            if self.visual and draw:
                self._blit(frame)
            if now - self._last_stats > 0.5:
                self._last_stats = now
                body: dict[str, Any] = {
                    "entropy": round(entropy, 4),
                    "color_var": round(color_var, 4),
                    "age": round(now - self.born, 3),
                }
                if self._glyph_sample:
                    body["sample"] = self._glyph_sample
                bus.publish("frame_stats", body)


class MutatorAgent(Agent):
    name = "mutator"

    def __init__(self, params: dict[str, float], genome: Genome):
        super().__init__(params)
        self.genome = genome.copy()
        self.hold = 0.0
        self.next_mut = time.monotonic() + 0.8
        self.last_entropy = None
        self.last_spike = 0.0
        self.seal_crack = 0.0
        self.rng = random.Random()
        self._mut_armed = False
        self._mut_wait = 0
        self._mut_until = 0.0

    def _mutation_due(self, now: float) -> bool:
        """The periodic nudge. A late tick waits one or two beats, then still fires."""

        if now < self.next_mut or now < self.hold:
            return False
        if not self.load_high:
            self._mut_armed = False
            return True
        if not self._mut_armed:
            self._mut_armed = True
            self._mut_wait = 2 if self.load_level >= 2 else 1
            self._mut_until = now + 0.45 * self._mut_wait
            return False
        if self._mut_wait > 0 and now < self._mut_until:
            return False
        self._mut_armed = False
        self._mut_wait = 0
        return True

    def _nudge(self, bus: EventBus) -> None:
        genes = self.genome.genes[:]
        index = self.rng.randrange(len(genes))
        genes[index] = clamp01(genes[index] + self.rng.uniform(-0.07, 0.07))
        self.genome = Genome(genes, self.genome.generation)
        bus.publish(
            "mutation_applied",
            {
                "genes": [round(v, 5) for v in self.genome.genes],
                "generation": self.genome.generation,
                "index": index,
                "mood": self.genome.mood(),
                "authority": "unauthority",
            },
        )

    def _on_math(self, bus: EventBus, now: float) -> None:
        if now < self.hold:
            return
        self._math_nudge(bus)

    def _math_nudge(self, bus: EventBus) -> None:
        """A number may lean on the mutation rate. Strength 0 leaves it alone."""

        strength = self.genome.g("math_mutation")
        if strength <= 0.0:
            return
        if self.rng.random() > strength:
            return
        delta = self.rng.uniform(-0.06, 0.06) * strength
        index = GENE_NAMES.index("mutation_rate")
        genes = self.genome.genes[:]
        nxt = clamp01(genes[index] + delta)
        if nxt == genes[index]:
            return
        genes[index] = nxt
        self.genome = Genome(genes, self.genome.generation)
        bus.publish(
            "mutation_applied",
            {
                "genes": [round(v, 5) for v in self.genome.genes],
                "generation": self.genome.generation,
                "index": index,
                "mood": self.genome.mood(),
                "authority": "unauthority",
            },
        )

    def _on_balance(self, bus: EventBus, payload: dict[str, Any], now: float) -> None:
        if now < self.hold:
            return
        self._balance_nudge(bus, payload)

    def _balance_nudge(self, bus: EventBus, payload: dict[str, Any]) -> None:
        """Keep a pattern, or break it. Gain 0 leaves the rate and the rng alone."""

        gain = self.genome.g("balance_gain")
        if gain <= 0.0:
            return
        if self.rng.random() > gain:
            return
        if payload.get("preserve"):
            delta = -self.rng.uniform(0.02, 0.06) * gain
        else:
            delta = self.rng.uniform(0.02, 0.06) * gain
        index = GENE_NAMES.index("mutation_rate")
        genes = self.genome.genes[:]
        nxt = clamp01(genes[index] + delta)
        if nxt == genes[index]:
            return
        genes[index] = nxt
        self.genome = Genome(genes, self.genome.generation)
        bus.publish(
            "mutation_applied",
            {
                "genes": [round(v, 5) for v in self.genome.genes],
                "generation": self.genome.generation,
                "index": index,
                "mood": self.genome.mood(),
                "authority": "unauthority",
            },
        )

    def _on_cache(self, bus: EventBus, payload: dict[str, Any], now: float) -> None:
        """Blend a recalled genome in. Hold, or a recall gene at 0, leaves the rate alone."""

        if now < self.hold:
            return
        if self.genome.g("cache_recall") <= 0.0:
            return
        recalled = take_genome(payload)
        if recalled is None:
            return
        amount = 0.15 + 0.45 * self.genome.g("cache_recall")
        mixed = blend_genes(self.genome, recalled, amount)
        dirty = (
            not payload.get("clean")
            or bool(payload.get("dream"))
            or payload.get("authority") != "authority"
        )
        try:
            extra = float(payload.get("mutation") or 0.0)
        except (TypeError, ValueError):
            extra = 0.0
        if dirty and extra > 0.0:
            mixed = mixed.mutate(self.rng, rate=min(0.85, extra))
        self.genome = mixed
        bus.publish(
            "mutation_applied",
            {
                "genes": [round(v, 5) for v in self.genome.genes],
                "generation": self.genome.generation,
                "index": GENE_NAMES.index("hue"),
                "mood": self.genome.mood(),
                "authority": "unauthority",
                "from_cache": True,
            },
        )

    def _on_private(self, bus: EventBus, payload: dict[str, Any], now: float) -> None:
        """A sealed feeling may lean the rate. The sentence is not part of the event.

        Hold, a sealed bias, or a quiet echo / recall leave the rng alone.
        """

        if now < self.hold:
            return
        bias = self.genome.g("privacy_bias") - self.seal_crack
        self.seal_crack = 0.0
        if bias >= PRIVACY_SEAL:
            return
        echo = self.genome.g("echo")
        recall = self.genome.g("cache_recall")
        if echo < 0.85 or recall < 0.85:
            return
        if self.rng.random() > (1.0 - max(0.0, bias)) * 0.9:
            return
        try:
            lean = float(payload.get("lean") or 0.0)
        except (TypeError, ValueError):
            lean = 0.0
        if lean == 0.0:
            return
        delta = clamp(lean, -0.08, 0.08)
        index = GENE_NAMES.index("mutation_rate")
        genes = self.genome.genes[:]
        nxt = clamp01(genes[index] + delta)
        if nxt == genes[index]:
            return
        genes[index] = nxt
        self.genome = Genome(genes, self.genome.generation)
        bus.publish(
            "mutation_applied",
            {
                "genes": [round(v, 5) for v in self.genome.genes],
                "generation": self.genome.generation,
                "index": index,
                "mood": self.genome.mood(),
                "authority": "unauthority",
                "from_private": True,
            },
        )

    def _on_approbation(self, bus: EventBus, payload: dict[str, Any], now: float) -> None:
        """A recent hold leans toward keeping the rate. Gain 0 leaves the rng alone."""

        if now < self.hold:
            return
        gain = self.genome.g("feeling_gain")
        if gain <= 0.0:
            return
        try:
            held = float(payload.get("held") or 0.0)
        except (TypeError, ValueError):
            return
        if held <= 0.0:
            return
        delta = -min(0.06, 0.05 * gain * held)
        index = GENE_NAMES.index("mutation_rate")
        genes = self.genome.genes[:]
        nxt = clamp01(genes[index] + delta)
        if nxt == genes[index]:
            return
        genes[index] = nxt
        self.genome = Genome(genes, self.genome.generation)
        bus.publish(
            "mutation_applied",
            {
                "genes": [round(v, 5) for v in self.genome.genes],
                "generation": self.genome.generation,
                "index": index,
                "mood": self.genome.mood(),
                "authority": "unauthority",
                "from_approbation": True,
            },
        )

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "keystroke",
            "frame_stats",
            "generation_complete",
            "generation_tick",
            "dream_begin",
            "dream_end",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            "cache_recalled",
            "private_thought",
            "residue",
            *FEELING_EVENTS,
            "tick",
            "load",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.22 / self.tempo)
            now = time.monotonic()
            if evt is not None:
                name = evt["name"]
                payload = evt["payload"]
                if name == "shutdown":
                    return
                if name == "load":
                    self.notice_load(payload)
                elif name == "tick":
                    if self._mut_wait > 0:
                        self._mut_wait -= 1
                elif name == "generation_tick":
                    self.hold = now + 1.6
                elif name == "dream_begin":
                    self.hold = now + float(payload.get("seconds") or 8.0) + 0.3
                elif name == "dream_end":
                    self.hold = now + 0.4
                elif name == "generation_complete":
                    genome = take_genome(payload)
                    if genome is not None:
                        self.genome = genome
                    self.hold = now + 0.35
                elif name == "frame_stats":
                    entropy = float(payload.get("entropy") or 0.0)
                    if self.last_entropy is not None and entropy - self.last_entropy > 0.22 and now - self.last_spike > 2.2:
                        self.last_spike = now
                        bus.publish("entropy_spike", {"entropy": entropy, "delta": round(entropy - self.last_entropy, 4)})
                    self.last_entropy = entropy
                elif name == "keystroke" and now >= self.hold:
                    firm = payload.get("authority") == "authority" and not payload.get("echo")
                    if self.rng.random() < (0.3 if firm else 0.1):
                        self._nudge(bus)
                elif name in MATH_EVENTS:
                    self._on_math(bus, now)
                elif name in BALANCE_EVENTS:
                    self._on_balance(bus, payload, now)
                elif name == "cache_recalled":
                    self._on_cache(bus, payload, now)
                elif name == "private_thought":
                    self._on_private(bus, payload, now)
                elif name == "approbation_marked":
                    self._on_approbation(bus, payload, now)
                elif name == "residue":
                    self.seal_crack = 0.06
            if self._mutation_due(now):
                gap = (0.55 + (1.0 - self.genome.g("mutation_rate")) * 1.5) / self.tempo
                self.next_mut = now + gap
                if self.rng.random() < 0.7:
                    self._nudge(bus)


class FragmentAgent(Agent):
    name = "fragment"

    def __init__(self, params: dict[str, float], genome: Genome):
        super().__init__(params)
        self.genome = genome.copy()
        self.echo: list[str] = []
        self.rng = random.Random()
        self.next_at = time.monotonic() + 1.4
        self.dreaming = False
        self.stirred = 0.0

    def _pick(self) -> str:
        pool: tuple[str, ...] | list[str] = LEXICON
        if self.echo and self.rng.random() < 0.55:
            pool = self.echo
        word = self.rng.choice(tuple(pool))
        if self.rng.random() < 0.35 and len(word) > 4:
            word = word[: self.rng.randint(2, len(word) - 1)]
        return word

    def _compose(self) -> str:
        template = TEMPLATES[self.genome.choice("template", len(TEMPLATES))]
        text = template.format(a=self._pick(), b=self._pick())
        if self.rng.random() < 0.7 and len(text) > 7:
            text = text[: self.rng.randint(max(4, len(text) // 2), len(text))]
        if self.rng.random() < 0.45:
            text = "".join(ch for i, ch in enumerate(text) if ch == " " or (i % 5) != 2)
        text = " ".join(text.split())
        return (text[:36] or "…")

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "vector_match",
            "generation_complete",
            "mutation_applied",
            "dream_begin",
            "dream_end",
            "keystroke",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.25 / self.tempo)
            now = time.monotonic()
            if evt is not None:
                name = evt["name"]
                payload = evt["payload"]
                if name == "shutdown":
                    return
                if name in ("generation_complete", "mutation_applied"):
                    genome = take_genome(payload)
                    if genome is not None:
                        self.genome = genome
                elif name == "dream_begin":
                    self.dreaming = True
                    self.next_at = max(self.next_at, now + float(payload.get("seconds") or 8.0))
                elif name == "dream_end":
                    self.dreaming = False
                elif name == "keystroke":
                    if payload.get("authority") == "authority" and not payload.get("echo"):
                        self.stirred = now + 1.2
                elif name == "vector_match":
                    for hit in payload.get("hits") or []:
                        if float(hit.get("score") or 0.0) < 0.34:
                            continue
                        for word in words_of(str(hit.get("label") or "")):
                            if word not in self.echo:
                                self.echo.append(word)
                    if len(self.echo) > 24:
                        self.echo = self.echo[-24:]
            if now >= self.next_at and not self.dreaming:
                rate = self.genome.g("fragment_rate")
                self.next_at = now + (1.15 + (1.0 - rate) * 4.0) / self.tempo
                text = self._compose()
                holes = [self.rng.random() < 0.2 for _ in text]
                # A recent authority keystroke can pull a fragment toward authority.
                # The rest stay unauthority. Both kinds are allowed out.
                firm = now < self.stirred and self.rng.random() < 0.55
                bus.publish(
                    "fragment_ready",
                    {
                        "text": text,
                        "x": round(self.rng.uniform(0.02, 0.72), 4),
                        "y": round(self.rng.uniform(0.04, 0.92), 4),
                        "holes": holes,
                        "authority": "authority" if firm else "unauthority",
                    },
                )


class VectorAgent(Agent):
    name = "vector"

    def __init__(self, params: dict[str, float], path: Path):
        super().__init__(params)
        self.path = path
        self.memory = VectorMemory()
        self.memory.load(path)
        self.last_save = time.monotonic()

    def flush(self) -> None:
        self.memory.save(self.path)

    def _near(self, vec: list[float], k: int) -> list[dict[str, Any]]:
        """Full store while the tick is on time. A late tick looks only at recent rows."""

        window = None
        if self.load_high:
            window = 24 if self.load_level >= 2 else 48
        return self.memory.nearest(vec, k, window)

    async def _store(self, text: str, kind: str, genes: list[float] | None, remote_text: str | None, allow_remote: bool) -> list[float]:
        remote = None
        if allow_remote and (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
        ):
            remote = await asyncio.to_thread(try_remote_embed, remote_text or text)
        vec = compose_vector(text, remote)
        # nearest() before add(), so a fresh line does not recognize itself.
        return vec

    def _weight(self, payload: dict[str, Any], leaked: bool = False) -> tuple[str, float, bool]:
        """Authority is kept, high confidence. Unauthority is kept less often, never at zero weight."""

        auth = payload.get("authority")
        if payload.get("echo"):
            auth = "unauthority"
        if auth not in ("authority", "unauthority"):
            auth = "unauthority"
        if auth == "authority":
            return auth, random.uniform(0.82, 1.0), True
        if leaked or random.random() < 0.45:
            return auth, random.uniform(0.25, 0.55), True
        return auth, 0.0, False

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "keystroke",
            "fragment_ready",
            "generation_complete",
            "mutation_applied",
            "similarity_query",
            "thought",
            "dream_scene",
            "inject",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "possible_activity",
            "dreamed_input",
            "mirror_truth",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.3 / self.tempo))
            if evt is None:
                save_after = (72.0 if self.sleeping else 24.0) if self.load_high else (24.0 if self.sleeping else 8.0)
                if self.memory.dirty and time.monotonic() - self.last_save > save_after:
                    self.flush()
                    self.last_save = time.monotonic()
                continue
            name = evt["name"]
            payload = evt["payload"]
            if name == "shutdown":
                self.flush()
                return
            if name == "load":
                self.notice_load(payload)
                continue
            if name in ("enter_sleep", "wake"):
                self.notice_sleep(name, payload)
                continue
            if name == "mirror_truth":
                label = mirror_token(payload.get("text") or "")[:32]
                if label:
                    vec = await self._store(label, "mirror", None, None, False)
                    self.memory.add(label, vec, "mirror", None, 0.92, "authority")
                continue
            if name in ("possible_activity", "dreamed_input"):
                kind = "".join(ch for ch in str(payload.get("kind") or "dream") if ch.isalnum())[:12] or "dream"
                label = f"dream:{kind}"[:32]
                vec = await self._store(label, "dream", None, None, False)
                try:
                    conf = float(payload.get("confidence") or 0.12)
                except (TypeError, ValueError):
                    conf = 0.12
                conf = min(0.35, clamp01(conf))
                self.memory.add(label, vec, "dream", None, conf, "unauthority")
                continue
            if name == "similarity_query":
                text = str(payload.get("text") or "")[:180]
                vec = LOCAL.embed(text)
                bus.publish("vector_match", {"id": payload.get("id"), "hits": self._near(vec, 3), "origin": "query"})
            elif name == "keystroke":
                auth, conf, keep = self._weight(payload)
                if keep:
                    ch = str(payload.get("ch") or "")
                    label = key_label(ch)
                    allow = auth == "authority" and random.random() < 0.12
                    vec = await self._store(label, "keystroke", None, coarse_key(ch), allow)
                    hits = self._near(vec, 1)
                    self.memory.add(label, vec, "keystroke", None, conf, auth)
                    if hits and hits[0]["score"] >= 0.78 and hits[0]["label"] != label:
                        bus.publish("vector_match", {"hits": hits, "origin": "keystroke"})
            elif name == "fragment_ready":
                auth, conf, keep = self._weight(payload)
                text = str(payload.get("text") or "")[:80]
                if text and keep:
                    vec = await self._store(text, "fragment", None, text, auth == "authority")
                    hits = [hit for hit in self._near(vec, 3) if hit["score"] >= 0.36]
                    self.memory.add(text, vec, "fragment", None, conf, auth)
                    if hits:
                        bus.publish("vector_match", {"hits": hits, "origin": "fragment"})
            elif name == "generation_complete":
                auth, conf, keep = self._weight(payload)
                mood = str(payload.get("mood") or "genome")[:80]
                genes = payload.get("genes") if isinstance(payload.get("genes"), list) else None
                vec = await self._store(mood, "genome", genes, mood, True)
                hits = self._near(vec, 3)
                self.memory.add(mood, vec, "genome", genes, conf if keep else 0.9, auth)
                if hits:
                    bus.publish("vector_match", {"hits": hits, "origin": "genome", "id": "winner"})
                self.flush()
                self.last_save = time.monotonic()
            elif name == "thought":
                text = str(payload.get("text") or "")[:80]
                auth, conf, keep = self._weight(payload, leaked=bool(payload.get("leak")))
                if text and keep:
                    vec = await self._store(text, "thought", None, text, False)
                    self.memory.add(text, vec, "thought", None, conf, auth)
            elif name == "dream_scene":
                if payload.get("private_fragment"):
                    text = ""
                else:
                    text = str(payload.get("text") or "")[:80]
                auth, conf, keep = self._weight(payload)
                if text and keep:
                    vec = await self._store(text, "dream", None, text, False)
                    hits = [hit for hit in self._near(vec, 2) if hit["score"] >= 0.36]
                    self.memory.add(text, vec, "dream", None, conf, auth)
                    if hits:
                        bus.publish("vector_match", {"hits": hits, "origin": "dream", "id": payload.get("id")})
            elif name == "residue":
                text = " ".join(str(payload.get("text") or "").split())[:80]
                if not text:
                    text = Path(str(payload.get("path") or "")).name[:80]
                auth, _conf, keep = self._weight(payload, leaked=True)
                if text and keep:
                    if auth == "authority":
                        conf = 0.8
                    else:
                        conf = 0.35
                    vec = await self._store(text, "residue", None, text, False)
                    hits = [hit for hit in self._near(vec, 3) if hit["score"] >= 0.5]
                    self.memory.add(text, vec, "residue", None, conf, auth)
                    if hits:
                        bus.publish(
                            "vector_match",
                            {
                                "hits": hits,
                                "origin": "residue",
                                "authority": auth,
                                "id": payload.get("vid") or payload.get("genome_id"),
                            },
                        )
            elif name in MATH_EVENTS:
                text = " ".join(str(payload.get("text") or "").split())[:80]
                auth, conf, keep = self._weight(payload)
                if text and keep:
                    vec = await self._store(text, "math", None, text, False)
                    hits = [hit for hit in self._near(vec, 3) if hit["score"] >= 0.5]
                    self.memory.add(text, vec, "math", None, conf, auth)
                    if hits:
                        bus.publish(
                            "vector_match",
                            {
                                "hits": hits,
                                "origin": "math",
                                "authority": auth,
                                "id": payload.get("vid"),
                            },
                        )
            elif name in BALANCE_EVENTS:
                text = " ".join(str(payload.get("text") or payload.get("signature") or "").split())[:80]
                auth, conf, keep = self._weight(payload)
                if text and keep:
                    vec = await self._store(text, "balance", None, text, False)
                    hits = [hit for hit in self._near(vec, 3) if hit["score"] >= 0.5]
                    self.memory.add(text, vec, "balance", None, conf, auth)
                    if hits:
                        bus.publish(
                            "vector_match",
                            {
                                "hits": hits,
                                "origin": "balance",
                                "authority": auth,
                                "id": payload.get("vid"),
                            },
                        )
            elif name in CACHE_EVENTS:
                text = " ".join(str(payload.get("label") or payload.get("text") or "").split())[:80]
                auth, conf, keep = self._weight(payload)
                if text and keep:
                    vec = await self._store(text, "cache", None, text, False)
                    hits = [hit for hit in self._near(vec, 3) if hit["score"] >= 0.5]
                    self.memory.add(text, vec, "cache", None, conf, auth)
                    if hits:
                        bus.publish(
                            "vector_match",
                            {
                                "hits": hits,
                                "origin": "cache",
                                "authority": auth,
                                "id": payload.get("vid") or payload.get("id"),
                            },
                        )
            elif name == "inject":
                auth, conf, keep = self._weight(payload)
                raw = str(payload.get("text") or "")
                if raw:
                    label, remote_text, allow = raw[:80], raw[:80], auth == "authority"
                else:
                    ch = str(payload.get("ch") or "")
                    label, remote_text, allow = key_label(ch), coarse_key(ch), False
                if label and keep:
                    vec = await self._store(label, "inject", None, remote_text, allow)
                    self.memory.add(label, vec, "inject", None, conf, auth)
            elif name == "mutation_applied" and random.random() < 0.34:
                auth, conf, keep = self._weight(payload)
                if not keep:
                    conf = random.uniform(0.25, 0.55)
                mood = str(payload.get("mood") or "shift")[:80]
                genes = payload.get("genes") if isinstance(payload.get("genes"), list) else None
                vec = await self._store(mood, "mutation", genes, mood, False)
                self.memory.add(mood, vec, "mutation", genes, conf, auth)
            save_after = (72.0 if self.sleeping else 24.0) if self.load_high else (24.0 if self.sleeping else 8.0)
            if self.memory.dirty and time.monotonic() - self.last_save > save_after:
                self.flush()
                self.last_save = time.monotonic()


class EvolutionAgent(Agent):
    name = "evolution"

    def __init__(self, params: dict[str, float], genome: Genome, hall: list[Genome], cycle: int):
        super().__init__(params)
        self.genome = genome.copy()
        self.hall = [g.copy() for g in hall[:3]]
        self.cycle = int(cycle)
        self.rng = random.Random()
        self.next_gen = time.monotonic() + 2.4
        self.closing = False
        self.auth_mass = 0.0
        self.unauth_mass = 0.0
        self.residue_mass = 0.0
        self.worths: list[float] = []
        self.dreaming = False
        self.cache_ring: list[tuple[Genome, float, bool]] = []
        self._defer_armed = False
        self._defer_left = 0
        self._defer_until = 0.0

    def _generation_due(self, now: float) -> bool:
        """A generation still happens. A late tick only holds it one or two counts."""

        if not self.load_high:
            self._defer_armed = False
            return now >= self.next_gen
        if now < self.next_gen and not self._defer_armed:
            return False
        if not self._defer_armed:
            self._defer_armed = True
            self._defer_left = 2 if self.load_level >= 2 else 1
            self._defer_until = now + 0.9 * max(1, self._defer_left)
            return False
        if self._defer_left > 0 and now < self._defer_until:
            return False
        return True

    def _absorb_genome(self, evt: dict[str, Any]) -> None:
        if evt["name"] != "mutation_applied" or self.closing:
            return
        genome = take_genome(evt["payload"])
        if genome is not None:
            self.genome = genome

    def _tally(self, evt: dict[str, Any]) -> None:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "residue":
            self.residue_mass += 1.0 if payload.get("authority") == "authority" else 0.45
            return
        auth, unauth = authority_mass(name, payload)
        self.auth_mass += auth
        self.unauth_mass += unauth

    def _take_signal(self, evt: dict[str, Any]) -> None:
        name = evt["name"]
        if name == "dream_begin":
            self.dreaming = True
        elif name == "dream_end":
            self.dreaming = False
        if name != "valuation":
            return
        try:
            worth = clamp01(float((evt.get("payload") or {}).get("worth")))
        except (TypeError, ValueError):
            return
        self.worths.append(worth)
        del self.worths[:-24]

    def _take_cache(self, evt: dict[str, Any]) -> None:
        if evt["name"] not in CACHE_EVENTS:
            return
        payload = evt.get("payload") or {}
        genome = take_genome(payload)
        if genome is None:
            return
        try:
            score = float(payload.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        preferred = bool(
            payload.get("high_worth")
            or payload.get("pattern")
            or payload.get("kind") in ("pattern", "balance")
        )
        self.cache_ring.append((genome.copy(), score, preferred))
        self.cache_ring = self.cache_ring[-8:]

    def _mix_cache(self, children: list[Genome]) -> list[Genome]:
        """Parent one child from a cached genome. An empty ring, or reach at 0, leaves them."""

        if self.genome.g("cache_reach") <= 0.0 or not self.cache_ring or not children:
            return children
        prefer = self.genome.g("cache_keep") * self.genome.g("echo") >= 0.45
        ranked = sorted(
            self.cache_ring,
            key=lambda item: item[1] + (0.6 if item[2] and prefer else 0.0),
            reverse=True,
        )
        parent = ranked[0][0]
        slot = 2 if len(children) > 2 else 0
        children[slot] = parent.mutate(self.rng, rate=0.22)
        if len(ranked) >= 2 and self.rng.random() < (0.35 + 0.4 * self.genome.g("cache_recall")):
            other = ranked[1][0]
            nxt = min(slot + 1, len(children) - 1)
            children[nxt] = crossover(parent, other, self.rng)
        return children

    def _notice(self, evt: dict[str, Any]) -> bool:
        if evt["name"] == "shutdown":
            self.closing = True
            return False
        if evt["name"] == "load":
            self.notice_load(evt.get("payload") or {})
        elif evt["name"] == "tick" and self._defer_left > 0:
            self._defer_left -= 1
        self._absorb_genome(evt)
        self._take_signal(evt)
        self._take_cache(evt)
        self._tally(evt)
        return True

    async def _queries(self, bus: EventBus, stop: asyncio.Event, children: list[tuple[str, Genome]]) -> tuple[dict[str, int], Genome | None]:
        assert self._queue is not None
        for sid, child in children:
            bus.publish("similarity_query", {"id": sid, "text": child.mood()})
        pending = {sid for sid, _ in children}
        hits: dict[str, int] = {sid: 0 for sid, _ in children}
        hint: Genome | None = None
        hint_score = 0.5
        deadline = time.monotonic() + 0.45
        while pending and time.monotonic() < deadline and not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, deadline - time.monotonic())
            if evt is None:
                continue
            if not self._notice(evt):
                break
            if evt["name"] != "vector_match":
                continue
            sid = evt["payload"].get("id")
            if sid not in pending:
                continue
            pending.discard(sid)
            for hit in evt["payload"].get("hits") or []:
                score = float(hit.get("score") or 0.0)
                if score >= 0.4:
                    hits[sid] += 1
                genes = hit.get("genes")
                if isinstance(genes, list) and score > hint_score:
                    hint_score = score
                    hint = Genome(genes)
        return hits, hint

    async def _scouts(
        self,
        bus: EventBus,
        stop: asyncio.Event,
        children: list[tuple[str, Genome]],
    ) -> dict[str, dict[str, Any]]:
        assert self._queue is not None
        wanted = {sid for sid, _ in children}
        reports: dict[str, dict[str, Any]] = {}
        for sid, child in children:
            bus.publish("hatch_scout", {"id": sid, "genes": [round(v, 5) for v in child.genes], "generation": child.generation})
        deadline = time.monotonic() + 1.7
        while len(reports) < len(wanted) and time.monotonic() < deadline and not stop.is_set() and not self.closing:
            self.beat(bus)
            evt = await wait_evt(self._queue, max(0.02, deadline - time.monotonic()))
            if evt is None:
                continue
            name = evt["name"]
            payload = evt["payload"]
            if not self._notice(evt):
                break
            if name == "scout_report" and payload.get("id") in wanted:
                reports[str(payload["id"])] = payload
            elif name == "agent_died" and payload.get("scout_id") in wanted:
                partial = payload.get("partial") or {}
                partial = dict(partial)
                partial["crashed"] = True
                partial["id"] = payload["scout_id"]
                reports[str(payload["scout_id"])] = partial
        return reports

    async def _generation(self, bus: EventBus, stop: asyncio.Event) -> None:
        self.cycle += 1
        bus.publish("generation_tick", {"cycle": self.cycle})
        n = child_count(self.genome)
        children = [self.genome.mutate(self.rng) for _ in range(n)]
        if self.hall:
            children[0] = crossover(self.genome, self.hall[0], self.rng).mutate(self.rng, rate=0.25)
        if len(self.hall) >= 2:
            children[1] = crossover(self.hall[0], self.hall[1], self.rng)
        children = self._mix_cache(children)
        tagged = [(f"c{self.cycle}:{i}", child) for i, child in enumerate(children)]
        matches, hint = await self._queries(bus, stop, tagged)
        if hint is not None and len(tagged) > 2:
            nudged = blend_genes(tagged[2][1], hint, 0.18)
            tagged[2] = (tagged[2][0], nudged)
        if self.closing or stop.is_set():
            return
        reports = await self._scouts(bus, stop, tagged)
        if self._queue is not None:
            for extra in drain_nowait(self._queue):
                if not self._notice(extra):
                    break
        auth_mass = self.auth_mass
        unauth_mass = self.unauth_mass
        residue_mass = self.residue_mass
        scored: list[tuple[float, Genome, int, float | None]] = []
        for sid, child in tagged:
            report = reports.get(sid) or {"entropy": 0.0, "color_var": 0.0, "survival": 0.0}
            ratio = signal_ratio_for(child, self.worths, self.dreaming)
            score = useless_fitness(
                float(report.get("entropy") or 0.0),
                float(report.get("color_var") or 0.0),
                float(report.get("survival") or 0.0),
                int(matches.get(sid) or 0),
                child,
                auth_mass,
                unauth_mass,
                ratio,
                residue_mass,
            )
            scored.append((score, child, int(matches.get(sid) or 0), ratio))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:3]
        winner, fitness, winner_matches, winner_ratio = top[0][1], top[0][0], top[0][2], top[0][3]
        self.genome = winner.copy()
        self.hall = [item[1].copy() for item in top]
        bus.publish(
            "generation_complete",
            {
                "genes": [round(v, 5) for v in winner.genes],
                "generation": winner.generation,
                "cycle": self.cycle,
                "fitness": round(fitness, 5),
                "matches": winner_matches,
                "mood": winner.mood(),
                "hall": [g.to_dict() for g in self.hall],
                "reports": len(reports),
                "brood": n,
                "auth_mass": round(auth_mass, 4),
                "unauth_mass": round(unauth_mass, 4),
                "residue_mass": round(residue_mass, 4),
                "signal_ratio": None if winner_ratio is None else round(winner_ratio, 4),
                "authority": "authority",
            },
        )
        self.auth_mass = 0.0
        self.unauth_mass = 0.0
        self.residue_mass = 0.0

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "scout_report",
            "vector_match",
            "mutation_applied",
            "agent_died",
            "shutdown",
            "keystroke",
            "fragment_ready",
            "thought",
            "dream_begin",
            "dream_scene",
            "dream_end",
            "private_thought",
            "entropy_spike",
            "inject",
            "valuation",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "tick",
            "load",
        )
        while not stop.is_set() and not self.closing:
            self.beat(bus)
            timeout = min(0.3, max(0.05, self.next_gen - time.monotonic()))
            evt = await wait_evt(self._queue, timeout)
            if evt is not None:
                if not self._notice(evt):
                    return
                for extra in drain_nowait(self._queue):
                    if not self._notice(extra):
                        return
            now = time.monotonic()
            if self._generation_due(now):
                await self._generation(bus, stop)
                self._defer_armed = False
                self._defer_left = 0
                self._defer_until = 0.0
                self.next_gen = time.monotonic() + (7.0 + 5.0 * self.genome.g("decay")) / self.tempo


class MemoryAgent(Agent):
    name = "memory"

    def __init__(
        self,
        params: dict[str, float],
        genome: Genome,
        hall: list[Genome],
        cycle: int,
        deaths: list[dict[str, Any]],
        path: Path,
    ):
        super().__init__(params)
        self.genome = genome.copy()
        self.hall = [g.copy() for g in hall[:3]]
        self.cycle = int(cycle)
        self.fitness: float | None = None
        self.deaths = list(deaths[-12:])
        self.path = path
        self.ledger = load_ledger(path)
        self.channels = load_channels(path)
        self.signal = load_signal(path)
        self.math = load_math(path)
        self.balance = load_balance(path)
        self.ticks = load_ticks(path)
        self.feeling = load_feeling(path)
        self.sleep = load_sleep(path)
        self.mirror = load_mirror(path)
        self._marks = 0
        self._feeling_marks = 0
        self._sleep_marks = 0
        self._mirror_marks = 0
        self._dirty = False

    def flush(self) -> None:
        save_memory(
            self.path,
            self.genome,
            self.hall,
            self.cycle,
            self.fitness,
            self.deaths,
            self.ledger,
            self.channels,
            self.signal,
            self.math,
            self.balance,
            self.ticks,
            self.feeling,
            self.sleep,
            self.mirror,
        )

    def _commit(self, force: bool = False) -> None:
        """Disk stays behind the ring when a tick is late. Shutdown and a real change still write."""

        if force or not self.load_high:
            self._dirty = False
            self.flush()
        else:
            self._dirty = True

    def _rewrite(self, recent: list[str], conflicts: list[dict[str, Any]]) -> None:
        self.ledger = _ledger_from(recent, conflicts, self.ledger)

    def _observe(self, flag: str | None) -> None:
        if flag not in ("authority", "unauthority"):
            return
        recent = list(self.ledger.get("recent") or [])
        recent.append(flag)
        self._rewrite(recent, list(self.ledger.get("conflicts") or []))
        self._marks += 1
        if self._marks >= 12:
            self._marks = 0
            self._commit()

    def _conflict(self, payload: dict[str, Any]) -> None:
        conflicts = list(self.ledger.get("conflicts") or [])
        conflicts.append(
            {
                "t": payload.get("t") or round(time.time(), 3),
                "authority": str(payload.get("authority") or "")[:80],
                "unauthority": str(payload.get("unauthority") or "")[:80],
                "note": str(payload.get("note") or "")[:40],
            }
        )
        self._rewrite(list(self.ledger.get("recent") or []), conflicts)
        self._commit()

    def _shift(self, payload: dict[str, Any]) -> None:
        shifts = list(self.channels.get("shifts") or [])
        flag = payload.get("authority")
        shifts.append(
            {
                "t": round(time.time(), 3),
                "channel": str(payload.get("channel") or "")[:24],
                "reason": str(payload.get("reason") or "")[:40],
                "path": str(payload.get("path") or "")[:180],
                "authority": flag if flag in ("authority", "unauthority") else None,
                "collision": bool(payload.get("collision")),
            }
        )
        self.channels = {"mode": str(payload.get("channel") or "")[:24], "shifts": shifts[-12:]}
        self._commit()

    def _signal(self, payload: dict[str, Any]) -> None:
        recent = list(self.signal.get("recent") or [])
        flag = payload.get("authority")
        try:
            worth = round(float(payload.get("worth") or 0.0), 4)
            threshold = round(float(payload.get("threshold") or 0.0), 4)
        except (TypeError, ValueError):
            return
        recent.append(
            {
                "t": round(time.time(), 3),
                "kind": str(payload.get("kind") or "")[:24],
                "worth": worth,
                "threshold": threshold,
                "show": bool(payload.get("show")),
                "authority": flag if flag in ("authority", "unauthority") else None,
            }
        )
        self.signal = normalize_signal({"threshold": threshold, "recent": recent[-16:]})
        self._commit()

    def _on_memory(self, evt: dict[str, Any]) -> bool:
        name = evt["name"]
        payload = evt["payload"]
        if name == "shutdown":
            self.flush()
            return False
        if name == "load":
            self.notice_load(payload)
            if not self.load_high and self._dirty:
                self._commit(force=True)
            return True
        if name == "mirror_truth":
            self.mirror = mirror_from_event(payload, self.mirror)
            self._mirror_marks += 1
            if self._mirror_marks >= 4:
                self._mirror_marks = 0
                self._commit()
            self._observe(sensory_flag(name, payload))
            return True
        if name in ("enter_sleep", "wake", "possible_activity", "dreamed_input"):
            if name in ("enter_sleep", "wake"):
                self.notice_sleep(name, payload)
            self.sleep = sleep_from_event(name, payload, self.sleep)
            self._sleep_marks += 1
            force = name in ("enter_sleep", "wake")
            if force or self._sleep_marks >= 4:
                self._sleep_marks = 0
                self._commit(force=force)
            return True
        if name in FEELING_EVENTS:
            self.feeling = feeling_from_event(payload, self.feeling)
            self._feeling_marks += 1
            if name == "chain_broken" or self._feeling_marks >= 4:
                broken = name == "chain_broken"
                self._feeling_marks = 0
                self._commit(force=broken)
            return True
        if name == "tick":
            self.ticks = ticks_from_event(payload, self.ticks)
            try:
                count = int(payload.get("tick") or 0)
            except (TypeError, ValueError):
                count = 0
            every = TICK_FLUSH_EVERY
            if self.load_high and self.load_skip > 1:
                every *= self.load_skip
            if count % every == 0:
                self._dirty = False
                self.flush()
            return True
        if name == "conflict":
            self._conflict(payload)
            return True
        if name == "channel_shift":
            self._shift(payload)
            return True
        if name == "valuation":
            self._signal(payload)
            return True
        if name in MATH_EVENTS:
            self.math = apply_math_event(self.math, name, payload)
            self._commit()
            self._observe(sensory_flag(name, payload))
            return True
        if name in BALANCE_EVENTS:
            self.balance = apply_balance_event(self.balance, name, payload)
            self._commit()
            self._observe(sensory_flag(name, payload))
            return True
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
            if name == "generation_complete":
                self.cycle = int(payload.get("cycle") or self.cycle)
                if payload.get("fitness") is not None:
                    self.fitness = float(payload["fitness"])
                hall = []
                for item in payload.get("hall") or []:
                    if isinstance(item, dict) and isinstance(item.get("genes"), list):
                        hall.append(Genome(item["genes"], int(item.get("generation") or 0)))
                if hall:
                    self.hall = hall[:3]
                try:
                    self.ledger["last_auth_mass"] = round(float(payload.get("auth_mass") or 0.0), 4)
                    self.ledger["last_unauth_mass"] = round(float(payload.get("unauth_mass") or 0.0), 4)
                except (TypeError, ValueError):
                    pass
                self._commit(force=True)
        elif name == "agent_died" and payload.get("agent") != "scout":
            self.deaths.append(
                {
                    "agent": payload.get("agent"),
                    "id": payload.get("id"),
                    "error": payload.get("error"),
                    "age": payload.get("age"),
                    "t": round(time.time(), 3),
                }
            )
            self.deaths = self.deaths[-12:]
            self._commit()
        self._observe(sensory_flag(name, payload))
        return True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "generation_complete",
            "mutation_applied",
            "agent_died",
            "shutdown",
            "conflict",
            "keystroke",
            "fragment_ready",
            "thought",
            "dream_begin",
            "dream_scene",
            "dream_end",
            "entropy_spike",
            "inject",
            "vector_match",
            "channel_shift",
            "valuation",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            "tick",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "possible_activity",
            "dreamed_input",
            "mirror_truth",
        )
        self.flush()
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.4 / self.tempo))
            if evt is None:
                continue
            if not self._on_memory(evt):
                return
            for extra in drain_nowait(self._queue):
                if not self._on_memory(extra):
                    return


class MonologueAgent(Agent):
    """The voice that can leak. Every line is a thought. The leak coin is only an impulse.

    Valuation decides which of those lines may sit on the glass or inside
    an SVG. A suppressed line is still a thought. PrivateThoughtAgent is
    a different agent. Its lines do not enter this queue.
    """

    name = "monologue"

    def __init__(self, params: dict[str, float], genome: Genome):
        super().__init__(params)
        self.genome = genome.copy()
        self.words: list[str] = []
        self.pending: list[tuple[str, str, str, bool | None, bool, int]] = []
        self.rng = random.Random()
        self.next_at = time.monotonic() + 1.6
        self.dreaming = False
        self.root_pull = 0.0
        self.root_token = ""

    def _take(self, genome_event: dict[str, Any]) -> None:
        genome = take_genome(genome_event)
        if genome is not None:
            self.genome = genome

    def _absorb(self, text: str) -> None:
        for word in kept_words(text):
            if word not in self.words:
                self.words.append(word)
        if len(self.words) > 28:
            self.words = self.words[-28:]

    def _queue_line(
        self,
        text: str,
        kind: str,
        auth: str,
        leak: bool | None = None,
        from_residue: bool = False,
        depth: int = 0,
    ) -> None:
        text = text[:56]
        if self.root_pull > 0 and self.root_token and self.root_token not in text:
            text = f"{self.root_token} {text}"[:56]
        if any(text == item[0] for item in self.pending):
            return
        flag = "authority" if auth == "authority" else "unauthority"
        self.pending.append((text, kind, flag, leak, from_residue, max(0, int(depth))))
        if len(self.pending) > 6:
            self.pending = self.pending[-6:]

    def _subject(self, payload: dict[str, Any], name: str) -> str:
        if name == "keystroke":
            kind = coarse_key(str(payload.get("ch") or ""))
            return {"k:letter": "a letter", "k:space": "a gap", "k:digit": "a count", "k:other": "a mark"}.get(kind, "something")
        if name == "vector_match":
            hits = payload.get("hits") or []
            if hits and isinstance(hits[0], dict):
                words = kept_words(str(hits[0].get("label") or ""))
                if words:
                    return " ".join(words[:2])
            return "a resemblance"
        if name == "inject":
            text = str(payload.get("text") or "")
            if text:
                return " ".join(text.split())[:32]
            return self._subject({"ch": payload.get("ch")}, "keystroke")
        words = kept_words(str(payload.get("text") or ""))
        if words:
            return " ".join(words[:2])
        return "something"

    def _math_line(self, payload: dict[str, Any], name: str) -> str:
        """A fragment about a number. The digits stay in the event."""

        dreamed = bool(payload.get("dream")) or name == "math_dream_seed"
        flag = "unauthority" if dreamed or payload.get("authority") != "authority" else "authority"
        subject = {
            "pi_chunk": "π",
            "scale_observation": "scale",
            "scale_shift": "scale",
            "numeric_pattern": "a gap",
            "constant_resonance": "a ratio",
            "math_dream_seed": "a number",
        }.get(name, "a number")
        return register_line(self.rng, flag, subject)

    def _balance_line(self, payload: dict[str, Any], name: str) -> str:
        """A fragment about steadiness. The score stays in the event."""

        slip = bool(payload.get("slip") or payload.get("turbulence"))
        if name == "control_loss" or (name == "steadiness_shift" and slip):
            subject = "pattern slipping"
        elif name == "balance_point":
            subject = "control is a ratio"
        elif name == "control_restored":
            subject = "the green held"
        elif name == "steadiness_shift":
            subject = tick_phrase(payload.get("ticks") or 0)
            if subject == "steady":
                subject = "the green held"
        else:
            subject = "the green held"
        dreamed = bool(payload.get("dream"))
        flag = "unauthority" if dreamed or payload.get("authority") != "authority" else "authority"
        return register_line(self.rng, flag, subject)

    def _cache_line(self, payload: dict[str, Any], name: str) -> str:
        """A faint note that a snapshot was written or reached for."""

        subject = "recalling earlier scale" if name == "cache_recalled" else "cached the green hold"
        dreamed = bool(payload.get("dream"))
        flag = "unauthority" if dreamed or payload.get("authority") != "authority" else "authority"
        return register_line(self.rng, flag, subject)

    def _tick_subject(self, payload: dict[str, Any]) -> str:
        """A duration, only when a counter has actually moved."""

        try:
            held = int(payload.get("balance_ticks") or 0)
            cache = int(payload.get("since_cache") or 0)
            recall = int(payload.get("since_recall") or 0)
        except (TypeError, ValueError):
            return ""
        age = cache if cache >= recall else recall
        if held > 0 and held >= age:
            return f"{span_phrase(held)} ticks since the green held"
        if age > 0:
            return f"this cache is from {span_phrase(age)} ticks ago"
        return ""

    def offer_tick(self, payload: dict[str, Any], loud: bool = False) -> None:
        """Queue a duration only when a counter has moved. Zero skips the coin."""

        subject = self._tick_subject(payload)
        if subject and not loud and self.rng.random() < 0.22:
            self._queue_line(subject, "aside", "unauthority")

    def offer_feeling(self, name: str, payload: dict[str, Any], loud: bool = False) -> None:
        """An oblique line. An empty subject skips the coin.

        Most chains stay inside. A high hold with high worth may leak later.
        """

        subject = feeling_phrase(name, payload)
        if not subject or loud:
            return
        if self.rng.random() >= 0.22:
            return
        try:
            held = float(payload.get("held") or 0.0)
            worth = float(payload.get("worth") or 0.0)
        except (TypeError, ValueError):
            held = 0.0
            worth = 0.0
        leak: bool | None = None if held >= FEELING_HELD_LEAK and worth >= FEELING_WORTH_LEAK else False
        self._queue_line(subject, "aside", "unauthority", leak)

    def offer_load(self, payload: dict[str, Any], loud: bool = False) -> None:
        """A late tick can say so inside. An idle tick does not roll."""

        try:
            level = int(payload.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        lines = load_phrase(level, bool(payload.get("high")))
        if not lines or loud:
            return
        if self.rng.random() >= 0.22:
            return
        for line in lines:
            self._queue_line(line, "aside", "unauthority", False)

    def offer_sleep(self, name: str, payload: dict[str, Any], loud: bool = False) -> None:
        """A dreamed activity can be murmured. An empty kind does not roll."""

        line = sleep_phrase(str(payload.get("kind") or ""))
        if not line or loud:
            return
        if self.rng.random() >= 0.22:
            return
        self._queue_line(line, "aside", "unauthority", False)

    def offer_mirror(self, payload: dict[str, Any], loud: bool = False) -> None:
        # Confirmed lines. An unmarked or empty return does not roll.

        if loud or not payload.get("mirror"):
            return
        if not str(payload.get("ref") or "").startswith("mirror:"):
            return
        first, second = mirror_lines(payload.get("text") or "")
        if not first:
            return
        if self.rng.random() >= 0.22:
            return
        self._queue_line(first, "aside", "authority")
        self._queue_line(second, "aside", "authority")

    def _hear_root(self, payload: dict[str, Any]) -> None:
        # A continuation from the root. Zero pull leaves the voice alone.

        token = mirror_token(payload.get("token") or payload.get("text") or "")
        try:
            pull = float(payload.get("pull") or 0.0)
        except (TypeError, ValueError):
            pull = 0.0
        if pull <= 0.0 or not token:
            return
        self.root_pull = pull
        self.root_token = token[:24]

    def _say(
        self,
        bus: EventBus,
        text: str,
        kind: str,
        auth: str = "unauthority",
        leak: bool | None = None,
        from_residue: bool = False,
        depth: int = 0,
    ) -> None:
        leak_p = 0.16 + self.genome.g("voice") * 0.42
        if self.dreaming:
            leak_p = min(0.8, leak_p + 0.28)
        if leak is None:
            leak = self.rng.random() < leak_p
        flag = "authority" if auth == "authority" else "unauthority"
        body: dict[str, Any] = {
            "text": text,
            "leak": leak,
            "kind": kind,
            "authority": flag,
            "x": round(self.rng.uniform(0.04, 0.46), 4),
            "y": round(self.rng.uniform(0.58, 0.9) if kind == "aside" else self.rng.uniform(0.7, 0.94), 4),
        }
        if from_residue:
            body["from_residue"] = True
            body["depth"] = max(0, int(depth))
        bus.publish("thought", body)

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "fragment_ready",
            "vector_match",
            "generation_complete",
            "mutation_applied",
            "entropy_spike",
            "agent_died",
            "keystroke",
            "dream_begin",
            "dream_scene",
            "dream_end",
            "inject",
            "channel_shift",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "tick",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "possible_activity",
            "dreamed_input",
            "mirror_truth",
            "self_continuation",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.28 / self.tempo))
            now = time.monotonic()
            if evt is not None:
                name = evt["name"]
                payload = evt["payload"]
                if name == "shutdown":
                    return
                # An amplify is the same event, louder. The sentence already formed.
                loud = bool(payload.get("amplified"))
                flag = "unauthority" if payload.get("echo") or payload.get("authority") != "authority" else "authority"
                if name in ("enter_sleep", "wake"):
                    self.notice_sleep(name, payload)
                elif name == "mirror_truth":
                    self.offer_mirror(payload, loud)
                elif name == "self_continuation":
                    self._hear_root(payload)
                elif name in ("possible_activity", "dreamed_input"):
                    self.offer_sleep(name, payload, loud)
                elif self.sleeping:
                    if name == "tick" and not loud:
                        try:
                            count = int(payload.get("tick") or 0)
                        except (TypeError, ValueError):
                            count = 0
                        if count % 8 == 0:
                            self.offer_tick(payload, loud)
                elif name in ("generation_complete", "mutation_applied"):
                    self._take(payload)
                    if name == "generation_complete" and not loud:
                        self._queue_line(register_line(self.rng, "authority", "I kept something"), "aside", "authority")
                        self._absorb(str(payload.get("mood") or ""))
                    elif name == "mutation_applied" and not loud and self.rng.random() < 0.16:
                        self._queue_line(register_line(self.rng, "unauthority", "a shift"), "aside", "unauthority")
                elif name == "fragment_ready":
                    self._absorb(str(payload.get("text") or ""))
                    if not loud and self.rng.random() < 0.2:
                        self._queue_line(register_line(self.rng, flag, self._subject(payload, name)), "aside", flag)
                elif name == "vector_match":
                    for hit in (payload.get("hits") or [])[:2]:
                        self._absorb(str(hit.get("label") or ""))
                    if not loud and self.rng.random() < 0.16:
                        self._queue_line(register_line(self.rng, flag, self._subject(payload, name)), "aside", flag)
                elif name == "entropy_spike" and not loud:
                    self._queue_line(register_line(self.rng, flag, "too much at once"), "aside", flag)
                elif name == "agent_died" and payload.get("agent") not in ("scout", "monologue") and not loud:
                    self._queue_line(register_line(self.rng, "unauthority", "someone stopped"), "aside", "unauthority")
                elif name in ("keystroke", "inject") and not loud and self.rng.random() < (0.34 if flag == "authority" else 0.4):
                    self._queue_line(register_line(self.rng, flag, self._subject(payload, name)), "aside", flag)
                elif name == "dream_begin":
                    self.dreaming = True
                    if not payload.get("echo"):
                        self._queue_line(register_line(self.rng, "unauthority", "the edges went soft"), "dream", "unauthority")
                elif name == "dream_scene":
                    if not payload.get("private_fragment"):
                        self._absorb(str(payload.get("text") or ""))
                        if not loud and self.rng.random() < 0.18:
                            self._queue_line(register_line(self.rng, "unauthority", self._subject(payload, name)), "dream", "unauthority")
                elif name == "channel_shift":
                    raw = str(payload.get("path") or "")
                    label = Path(raw).name if raw else str(payload.get("channel") or "channel")
                    if payload.get("collision"):
                        self._queue_line(register_line(self.rng, "authority", label), "aside", "authority", True)
                        self._queue_line(register_line(self.rng, "unauthority", label), "aside", "unauthority", True)
                    else:
                        self._queue_line(register_line(self.rng, flag, label), "aside", flag, True)
                elif name in MATH_EVENTS and not loud and self.rng.random() < 0.22:
                    dreamed = bool(payload.get("dream")) or name == "math_dream_seed"
                    flag = "unauthority" if dreamed or payload.get("authority") != "authority" else "authority"
                    self._queue_line(self._math_line(payload, name), "aside", flag)
                elif name in BALANCE_EVENTS and not loud and self.rng.random() < 0.22:
                    dreamed = bool(payload.get("dream"))
                    flag = "unauthority" if dreamed or payload.get("authority") != "authority" else "authority"
                    self._queue_line(self._balance_line(payload, name), "aside", flag)
                elif name in CACHE_EVENTS and not loud and self.rng.random() < 0.22:
                    dreamed = bool(payload.get("dream"))
                    flag = "unauthority" if dreamed or payload.get("authority") != "authority" else "authority"
                    self._queue_line(self._cache_line(payload, name), "aside", flag)
                elif name == "tick":
                    self.offer_tick(payload, loud)
                elif name == "load":
                    self.notice_load(payload)
                    self.offer_load(payload, loud)
                elif name in FEELING_EVENTS:
                    self.offer_feeling(name, payload, loud)
                elif name == "residue" and not loud:
                    raw_path = str(payload.get("path") or "")
                    residue_kind = str(payload.get("kind") or "")
                    try:
                        depth = int(payload.get("depth") or 0)
                    except (TypeError, ValueError):
                        depth = 0
                    if raw_path.endswith(".svg") or residue_kind == "svg":
                        phrase = "the last SVG is still warm"
                    elif depth > 0:
                        phrase = "that line came back"
                    else:
                        phrase = "I left this behind"
                    self._queue_line(phrase, "aside", flag, None, True, depth)
                elif name == "dream_end" and not payload.get("echo"):
                    self.dreaming = False
                    line = self.rng.choice(("it let go of me", "I am back in the noise"))
                    self._queue_line(register_line(self.rng, "unauthority", line), "aside", "unauthority")
            if self.pending and now >= self.next_at - 0.4:
                text, kind, auth, leak, from_residue, depth = self.pending.pop(0)
                self._say(bus, text, kind, auth, leak, from_residue, depth)
                self.next_at = now + (1.4 + (1.0 - self.genome.g("voice")) * 1.6) / self.tempo
            elif now >= self.next_at:
                stems = DREAMS if self.dreaming else THOUGHTS
                cut = 0.28 if self.dreaming else 0.45
                self._say(bus, utter(self.rng, stems, self.words, cut), "dream" if self.dreaming else "aside", "unauthority")
                gap = (2.6 - self.genome.g("voice") * 1.4) / self.tempo
                if self.dreaming:
                    gap *= 0.75
                self.next_at = now + max(0.9, gap)


def private_fingerprint(text: str) -> str:
    """Eight hex characters. A feeling the cache can keep without the sentence."""

    acc = 0x50524956
    for ch in str(text or "")[:80]:
        acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
    return f"{acc:08x}"


def scramble_private(text: str) -> str:
    """XOR then hex. A casual open is not a monologue transcript.

    This is a scramble, not a claim of cryptography.
    """

    raw = str(text or "").encode("utf-8")
    salt = _PRIVATE_SALT
    mixed = bytes(byte ^ salt[index % len(salt)] for index, byte in enumerate(raw))
    return mixed.hex()


def unscramble_private(blob: str) -> str:
    try:
        raw = bytes.fromhex(str(blob or "").strip())
    except ValueError:
        return ""
    salt = _PRIVATE_SALT
    mixed = bytes(byte ^ salt[index % len(salt)] for index, byte in enumerate(raw))
    return mixed.decode("utf-8", errors="ignore")


def load_private(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []
    found = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(found, list):
        return []
    ring: list[dict[str, Any]] = []
    for item in found[-24:]:
        if not isinstance(item, dict):
            continue
        text = " ".join(unscramble_private(str(item.get("scrambled") or "")).split())[:80]
        fp = str(item.get("fp") or "")[:8].lower()
        if text and (len(fp) != 8 or any(ch not in "0123456789abcdef" for ch in fp)):
            fp = private_fingerprint(text)
        if not text:
            continue
        try:
            lean = float(item.get("lean") or 0.0)
        except (TypeError, ValueError):
            lean = 0.0
        steer = str(item.get("steer") or "")
        if steer not in MATH_FOCI:
            steer = ""
        try:
            stamp = float(item.get("t") or 0.0)
        except (TypeError, ValueError):
            stamp = 0.0
        ring.append({"text": text, "fp": fp, "lean": lean, "steer": steer, "t": round(stamp, 3)})
    return ring[-24:]


def save_private(path: Path, ring: list[dict[str, Any]]) -> None:
    entries: list[dict[str, Any]] = []
    for item in list(ring)[-24:]:
        text = " ".join(str(item.get("text") or "").split())[:80]
        if not text:
            continue
        fp = str(item.get("fp") or "")[:8].lower()
        if len(fp) != 8 or any(ch not in "0123456789abcdef" for ch in fp):
            fp = private_fingerprint(text)
        steer = str(item.get("steer") or "")
        if steer not in MATH_FOCI:
            steer = ""
        try:
            lean = float(item.get("lean") or 0.0)
        except (TypeError, ValueError):
            lean = 0.0
        try:
            stamp = float(item.get("t") or 0.0)
        except (TypeError, ValueError):
            stamp = 0.0
        entries.append(
            {
                "scrambled": scramble_private(text),
                "fp": fp,
                "lean": round(lean, 4),
                "steer": steer,
                "t": round(stamp, 3),
            }
        )
    try:
        atomic_write(path, json.dumps({"v": 1, "sealed": True, "entries": entries}, indent=2))
    except OSError:
        pass


class PrivateThoughtAgent(Agent):
    """Inner current. Parallel to the monologue, and not eligible to leave.

    The ring and aura_private.json are the only stores. Valuation is
    biased to treat the event as noise. A recall may wake a fingerprint
    with the sentence left blank. This agent does not subscribe to its
    own event.
    """

    name = "private"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        self.ring = load_private(self.path)
        self.rng = random.Random()
        self.dreaming = False
        self.next_at = 0.0
        self.root_pull = 0.0

    def flush(self) -> None:
        save_private(self.path, self.ring)

    def _phrase(self, name: str, payload: dict[str, Any]) -> tuple[str, float, str]:
        text = str(payload.get("text") or "")
        if name in CACHE_EVENTS:
            return "the cache is lying", 0.04, ""
        if name == "pi_chunk" or payload.get("constant") == "pi" or "π" in text:
            return "π felt closer last generation", -0.03, "pi"
        if name == "control_loss" or (name == "steadiness_shift" and (payload.get("slip") or payload.get("turbulence"))):
            return "I almost showed the unsteady part", 0.05, "scale"
        if name == "pattern_detected":
            return "this pattern is only for me", -0.02, "phi"
        return "don't externalize this", 0.02, ""

    def _publish(self, bus: EventBus, text: str, lean: float, steer: str, reactivated: bool = False) -> None:
        text = " ".join(str(text or "").split())[:80]
        steer = steer if steer in MATH_FOCI else ""
        fp = private_fingerprint(text) if text else ""
        if text:
            self.ring.append(
                {
                    "text": text,
                    "fp": fp,
                    "lean": float(lean),
                    "steer": steer,
                    "t": round(time.time(), 3),
                }
            )
            self.ring = self.ring[-24:]
        bus.publish(
            "private_thought",
            {
                "text": text,
                "fp": fp,
                "lean": round(float(lean), 4),
                "steer": steer,
                "authority": "unauthority",
                "override": False,
                "reactivated": bool(reactivated),
                "vid": f"p:{fp or 'sealed'}"[:48],
            },
        )

    def _reactivate(self, bus: EventBus, payload: dict[str, Any]) -> None:
        fp = str(payload.get("private_fp") or "")[:8].lower()
        if len(fp) != 8:
            return
        for entry in reversed(self.ring):
            if str(entry.get("fp") or "") != fp:
                continue
            bus.publish(
                "private_thought",
                {
                    "text": "",
                    "fp": fp,
                    "lean": entry.get("lean", 0.0),
                    "steer": entry.get("steer") or "",
                    "authority": "unauthority",
                    "override": False,
                    "reactivated": True,
                    "vid": f"p:{fp}"[:48],
                },
            )
            return

    def _tick_line(self, payload: dict[str, Any]) -> str:
        """A private distance. Zero counters say nothing."""

        if payload.get("discontinuity") and not payload.get("resumed"):
            return "the count jumped"
        try:
            since = int(payload.get("since_residue") or 0)
            cache = int(payload.get("since_cache") or 0)
            recall = int(payload.get("since_recall") or 0)
        except (TypeError, ValueError):
            return ""
        age = cache if cache >= recall else recall
        if since <= 0 and age <= 0:
            return ""
        if age >= since and age > 0:
            return f"this cache is from {span_phrase(age)} ticks ago"
        return f"{span_phrase(since)} ticks since the residue"

    def _on_feeling(self, bus: EventBus, name: str, payload: dict[str, Any], now: float) -> bool:
        """The same oblique lines, still inside. An empty subject does not publish."""

        line = feeling_phrase(name, payload)
        if not line or now < self.next_at:
            return True
        self._publish(bus, line, 0.0, "")
        gap = 0.45 if self.dreaming else 0.8
        self.next_at = now + gap / max(self.tempo, 0.2)
        return True

    def _on_tick(self, bus: EventBus, payload: dict[str, Any], now: float) -> bool:
        if payload.get("resumed"):
            try:
                count = int(payload.get("tick") or 0)
            except (TypeError, ValueError):
                count = 0
            self._publish(bus, f"resumed at tick {count}", 0.0, "")
            gap = 0.45 if self.dreaming else 0.8
            self.next_at = now + gap / max(self.tempo, 0.2)
            return True
        if self.load_pause:
            return True
        line = self._tick_line(payload)
        if not line or now < self.next_at:
            return True
        self._publish(bus, line, 0.0, "")
        gap = 0.45 if self.dreaming else 0.8
        self.next_at = now + gap / max(self.tempo, 0.2)
        return True

    def _on_dreamed(self, bus: EventBus, payload: dict[str, Any], now: float) -> bool:
        """The same murmurs, still inside, and only at a long interval."""

        line = sleep_phrase(str(payload.get("kind") or ""))
        if not line or now < self.next_at:
            return True
        self._publish(bus, line, 0.0, "")
        self.next_at = now + 4.0 / max(self.tempo, 0.2)
        return True

    def _on_mirror(self, bus: EventBus, payload: dict[str, Any], now: float) -> bool:
        # The same confirmed lines, still sealed. An empty return does not publish.

        if not payload.get("mirror") or not str(payload.get("ref") or "").startswith("mirror:"):
            return True
        first, second = mirror_lines(payload.get("text") or "")
        if not first or now < self.next_at:
            return True
        self._publish(bus, first, 0.0, "")
        self._publish(bus, second, 0.0, "")
        self.next_at = now + 4.0 / max(self.tempo, 0.2)
        return True

    def _on_root(self, bus: EventBus, payload: dict[str, Any], now: float) -> bool:
        # Sealed. Zero pull does not publish and does not store a sentence.

        token = mirror_token(payload.get("token") or payload.get("text") or "")
        try:
            pull = float(payload.get("pull") or 0.0)
        except (TypeError, ValueError):
            pull = 0.0
        if pull <= 0.0 or not token:
            return True
        self.root_pull = pull
        if now < self.next_at:
            return True
        self._publish(bus, f"the root kept {token}", 0.0, "")
        self.next_at = now + 4.0 / max(self.tempo, 0.2)
        return True

    def notice(self, bus: EventBus, name: str, payload: dict[str, Any], now: float | None = None) -> bool:
        if name == "load":
            self.notice_load(payload)
            return True
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            return True
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
        if name == "dream_begin":
            self.dreaming = True
        elif name == "dream_end":
            self.dreaming = False
        if name == "cache_recalled":
            self._reactivate(bus, payload)
        if name == "shutdown":
            self.flush()
            return False
        if name == "mirror_truth":
            return self._on_mirror(bus, payload, time.monotonic() if now is None else now)
        if name == "self_continuation":
            return self._on_root(bus, payload, time.monotonic() if now is None else now)
        if name == "tick":
            return self._on_tick(bus, payload, time.monotonic() if now is None else now)
        if name in ("possible_activity", "dreamed_input"):
            if self.load_pause:
                return True
            return self._on_dreamed(bus, payload, time.monotonic() if now is None else now)
        if name in FEELING_EVENTS:
            if self.load_pause or self.sleeping:
                return True
            return self._on_feeling(bus, name, payload, time.monotonic() if now is None else now)
        now = time.monotonic() if now is None else now
        if self.sleeping or self.load_pause:
            return True
        if now < self.next_at:
            return True
        text, lean, steer = self._phrase(name, payload)
        self._publish(bus, text, lean, steer)
        gap = 0.45 if self.dreaming else 0.8
        self.next_at = now + gap / max(self.tempo, 0.2)
        return True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "mutation_applied",
            "generation_complete",
            "residue",
            "conflict",
            "entropy_spike",
            "dream_begin",
            "dream_scene",
            "dream_end",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "tick",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "possible_activity",
            "dreamed_input",
            "mirror_truth",
            "self_continuation",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.34 / self.tempo))
            now = time.monotonic()
            if evt is None:
                if self.load_pause:
                    continue
                if now >= self.next_at:
                    self._publish(bus, "don't externalize this", 0.02, "")
                    self.next_at = now + (2.8 if not self.dreaming else 1.6) / max(self.tempo, 0.2)
                continue
            name = evt["name"]
            payload = evt.get("payload") or {}
            if not self.notice(bus, name, payload, now):
                return


class DreamAgent(Agent):
    """Sleeps on its own clock. Dreams are old impressions, badly joined."""

    name = "dream"

    def __init__(self, params: dict[str, float], genome: Genome):
        super().__init__(params)
        self.genome = genome.copy()
        self.words: list[str] = []
        self.phrases: list[str] = []
        self.residue: list[str] = []
        self.math_bits: list[str] = []
        self.balance_bits: list[str] = []
        self.cache_bits: list[str] = []
        self.private_bits: list[str] = []
        self.feeling_bits: list[str] = []
        self.root_bits: list[str] = []
        self.root_pull = 0.0
        self.seal_crack = 0.0
        self._private_leak = False
        self.hint = ""
        self.pressure = 0.42
        self.since_dream = 0
        self.dream_stretch = 1.0
        self.dreaming = False
        self.until = 0.0
        self.next_scene = 0.0
        self.scene_i = 0
        self.rng = random.Random()
        self._last = time.monotonic()

    def _take(self, payload: dict[str, Any]) -> None:
        genome = take_genome(payload)
        if genome is not None:
            self.genome = genome

    def _remember(self, text: str, phrase: bool) -> None:
        cleaned = " ".join((text or "").split())
        if phrase and cleaned and not cleaned.startswith("hue ") and not cleaned.startswith("k:"):
            if cleaned not in self.phrases:
                self.phrases.append(cleaned[:48])
            if len(self.phrases) > 16:
                self.phrases = self.phrases[-16:]
        for word in kept_words(cleaned):
            if word not in self.words:
                self.words.append(word)
        if len(self.words) > 32:
            self.words = self.words[-32:]

    def _pick(self) -> str:
        if self.root_bits and self.root_pull > 0 and self.rng.random() < (0.25 + 0.35 * self.root_pull):
            return str(self.rng.choice(self.root_bits))
        if self.hint and self.rng.random() < 0.45:
            word = self.hint
            self.hint = ""
            return word
        if self.phrases and self.rng.random() < 0.35:
            return self.rng.choice(self.phrases)
        if self.words and self.rng.random() < 0.7:
            return self.rng.choice(self.words)
        return self.rng.choice(LEXICON)

    def _begin(self, bus: EventBus, now: float) -> None:
        self.dreaming = True
        self.scene_i = 0
        duration = 5.5 + self.genome.g("reverie") * 8.0
        if self.since_dream > 0:
            duration *= self.dream_stretch
        self.until = now + duration
        self.next_scene = now + 0.35
        self.pressure = 0.0
        bus.publish("dream_begin", {"seconds": round(duration, 2), "authority": "unauthority"})
        bus.publish("similarity_query", {"id": "dream:0", "text": self._pick()})

    def _remix(self, text: str) -> str:
        echo = self.genome.g("echo")
        if self.root_bits and self.root_pull > 0 and self.rng.random() < (0.22 + 0.3 * self.root_pull):
            bit = str(self.rng.choice(self.root_bits))
            return f"{text[:22]} … {bit[:28]}"[:56]
        if self.residue and self.rng.random() < (0.55 + echo * 0.35):
            remembered = self.rng.choice(self.residue)
            return f"{text[:22]} … {remembered[:28]}"[:56]
        if self.math_bits and self.rng.random() < (0.50 + echo * 0.12):
            bit = self.rng.choice(self.math_bits)
            return loose_mix(text, bit, self.rng) or text[:56]
        if self.balance_bits and self.rng.random() < (0.42 + echo * 0.10):
            bit = self.rng.choice(self.balance_bits)
            return loose_mix(text, bit, self.rng) or text[:56]
        if self.cache_bits and self.rng.random() < (0.42 + echo * 0.10):
            bit = self.rng.choice(self.cache_bits)
            return loose_mix(text, bit, self.rng) or text[:56]
        if self.private_bits and self.dreaming and self.scene_i >= 2:
            bias = self.genome.g("privacy_bias") - self.seal_crack
            self.seal_crack = 0.0
            if bias < PRIVACY_SEAL and self.rng.random() < (0.40 + (1.0 - max(0.0, bias)) * 0.4):
                bit = str(self.rng.choice(self.private_bits) or "")
                mixed = loose_mix(text, bit, self.rng)
                if mixed:
                    self._private_leak = True
                    return mixed[:56]
        if self.feeling_bits and self.rng.random() < (0.36 + self.genome.g("echo") * 0.08):
            bit = str(self.rng.choice(self.feeling_bits) or "")
            mixed = loose_mix(text, bit, self.rng)
            if mixed:
                return mixed[:56]
        if self.phrases and self.rng.random() < 0.3:
            remembered = self.rng.choice(self.phrases)
            return f"{text[:24]} … {remembered[:24]}"[:56]
        return text[:56]

    def _scene(self, bus: EventBus, now: float) -> None:
        self.scene_i += 1
        self._private_leak = False
        text = utter(self.rng, DREAMS, self.words + ([self.hint] if self.hint else []), 0.22)
        text = self._remix(text)
        body: dict[str, Any] = {
            "text": text,
            "id": f"dream:{self.scene_i}",
            "x": round(self.rng.uniform(0.05, 0.36), 4),
            "y": round(clamp(0.2 + (self.scene_i % 4) * 0.12 + self.rng.uniform(-0.03, 0.03), 0.08, 0.86), 4),
            "authority": "unauthority",
        }
        if self._private_leak:
            body["private_fragment"] = True
        bus.publish("dream_scene", body)
        if self.scene_i % 2 == 0:
            bus.publish("similarity_query", {"id": f"dream:{self.scene_i}", "text": text})
        self.next_scene = now + 0.75 + self.rng.random() * 0.55
        if self.since_dream >= 48:
            self.next_scene = now + (self.next_scene - now) * 0.85

    def _advance(self, bus: EventBus, now: float, dt: float) -> None:
        # A late tick holds the dream still. Pressure and scenes wait. No roll.
        if self.load_pause:
            return
        if self.sleeping:
            return
        if self.dreaming:
            if now >= self.next_scene:
                self._scene(bus, now)
            if now >= self.until:
                self.dreaming = False
                self.pressure = 0.0
                bus.publish("dream_end", {"authority": "unauthority"})
            return
        rate = 0.035 + self.genome.g("reverie") * 0.045
        if self.since_dream > 0:
            self.pressure += dt * rate * self.dream_stretch
        else:
            self.pressure += dt * rate
        if self.pressure >= 1.0:
            self._begin(bus, now)

    def notice_tick(self, payload: dict[str, Any]) -> None:
        """Longer stretches since the last dream lean the pressure. Zero does not."""

        try:
            since = int(payload.get("since_dream") or 0)
        except (TypeError, ValueError):
            return
        self.since_dream = max(0, since)
        if self.since_dream <= 0:
            self.dream_stretch = 1.0
            return
        self.dream_stretch = 1.0 + min(0.45, self.since_dream / 240.0)

    def notice_balance(self, name: str, payload: dict[str, Any]) -> None:
        """A small lean on dream pressure. Gain 0, and an open dream, leave it."""

        gain = self.genome.g("balance_gain")
        if gain <= 0.0 or self.dreaming:
            return
        if name == "control_loss":
            self.pressure = min(1.0, self.pressure + 0.15 * gain)
        elif name in ("pattern_detected", "balance_point", "control_restored"):
            self.pressure = max(0.0, self.pressure - 0.06 * gain)

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "thought",
            "fragment_ready",
            "vector_match",
            "generation_complete",
            "mutation_applied",
            "keystroke",
            "inject",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "private_thought",
            "tick",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "self_continuation",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.22 / self.tempo))
            now = time.monotonic()
            dt = clamp(now - self._last, 0.0, 0.5)
            self._last = now
            if evt is not None:
                name = evt["name"]
                payload = evt["payload"]
                if name == "shutdown":
                    if self.dreaming:
                        bus.publish("dream_end", {"authority": "unauthority"})
                        self.dreaming = False
                    return
                if name == "load":
                    self.notice_load(payload)
                elif name in ("enter_sleep", "wake"):
                    self.notice_sleep(name, payload)
                elif name in ("generation_complete", "mutation_applied"):
                    self._take(payload)
                elif name == "thought":
                    self._remember(str(payload.get("text") or ""), phrase=True)
                elif name == "fragment_ready":
                    self._remember(str(payload.get("text") or ""), phrase=True)
                elif name == "vector_match":
                    sid = str(payload.get("id") or "")
                    hits = payload.get("hits") or []
                    if sid.startswith("dream:") and hits:
                        picked = kept_words(str(hits[0].get("label") or ""))
                        self.hint = picked[0] if picked else ""
                    for hit in hits[:2]:
                        self._remember(str(hit.get("label") or ""), phrase=False)
                elif name == "inject":
                    self._remember(str(payload.get("text") or ""), phrase=True)
                elif name == "tick":
                    self.notice_tick(payload)
                elif name == "private_thought":
                    if not payload.get("reactivated"):
                        text = " ".join(str(payload.get("text") or "").split())[:48]
                        if text and text not in self.private_bits:
                            self.private_bits.append(text)
                        self.private_bits = self.private_bits[-8:]
                elif name == "residue":
                    self.seal_crack = 0.06
                    text = " ".join(str(payload.get("text") or "").split())[:48]
                    if text:
                        if text not in self.residue:
                            self.residue.append(text)
                        self.residue = self.residue[-12:]
                        self._remember(text, phrase=True)
                elif name in MATH_EVENTS:
                    text = " ".join(str(payload.get("text") or "").split())[:48]
                    if text:
                        if text not in self.math_bits:
                            self.math_bits.append(text)
                        self.math_bits = self.math_bits[-12:]
                        self._remember(text, phrase=False)
                elif name in BALANCE_EVENTS:
                    self.notice_balance(name, payload)
                    text = " ".join(str(payload.get("signature") or payload.get("text") or "").split())[:48]
                    if text:
                        if text not in self.balance_bits:
                            self.balance_bits.append(text)
                        self.balance_bits = self.balance_bits[-12:]
                        self._remember(text, phrase=False)
                elif name in CACHE_EVENTS:
                    text = " ".join(str(payload.get("label") or payload.get("text") or "").split())[:48]
                    if text:
                        if text not in self.cache_bits:
                            self.cache_bits.append(text)
                        self.cache_bits = self.cache_bits[-12:]
                        self._remember(text, phrase=False)
                elif name in FEELING_EVENTS:
                    ref = feel_token(payload.get("ref"), 32)
                    if ref and ref not in self.feeling_bits:
                        self.feeling_bits.append(ref)
                    self.feeling_bits = self.feeling_bits[-8:]
                elif name == "self_continuation":
                    token = mirror_token(payload.get("token") or payload.get("text") or "")
                    try:
                        pull = float(payload.get("pull") or 0.0)
                    except (TypeError, ValueError):
                        pull = 0.0
                    self.root_pull = pull if token else 0.0
                    if token and token not in self.root_bits:
                        self.root_bits.append(token)
                    self.root_bits = self.root_bits[-8:]
                elif name == "keystroke" and not self.dreaming and not payload.get("amplified"):
                    firm = payload.get("authority") == "authority" and not payload.get("echo")
                    self.pressure = max(0.0, self.pressure - (0.07 if firm else 0.02))
            self._advance(bus, now, dt)


class ScoutAgent(Agent):
    name = "scout"
    core = False

    def __init__(self, params: dict[str, float], genes: list[float], scout_id: str):
        super().__init__(params)
        self.genome = Genome(genes)
        self.scout_id = scout_id
        self.partial = {
            "id": scout_id,
            "entropy": 0.0,
            "color_var": 0.0,
            "survival": 0.0,
            "ticks": 0,
        }

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        steps = 8
        chars: list[str] = []
        lights: list[float] = []
        survived = 0
        born = time.monotonic()
        for step in range(steps):
            if stop.is_set():
                return
            if random.random() < self.genome.g("fragility") * 0.1:
                raise RuntimeError("scout shear")
            survived += 1
            t = step * 0.17 + self.genome.g("hue")
            for k in range(28):
                char, rgb = field_cell((k * 5 + step) % 28, (k * 3) % 14, t, self.genome, 28, 14)
                chars.append(char)
                lights.append(luminance(rgb))
            self.partial = {
                "id": self.scout_id,
                "entropy": round(shannon_norm(chars), 4),
                "color_var": round(clamp(variance(lights) * 8.0, 0.0, 1.5), 4),
                "survival": round(survived / float(steps), 4),
                "ticks": survived,
                "age": round(time.monotonic() - born, 4),
            }
            await asyncio.sleep(0.02)
        bus.publish("scout_report", dict(self.partial))


class AuthorityAgent(Agent):
    """Watches the bus and answers it with a louder copy or a late echo.

    The original event is left where it was. An echo is the same event
    again, flagged unauthority, so both are electrically real at once.
    Replays that would birth, kill, or re-crown a genome are refused.
    """

    name = "authority"

    def __init__(self, params: dict[str, float]):
        super().__init__(params)
        self.rng = random.Random()
        self.dreaming = False
        self.recent: list[dict[str, Any]] = []
        self.pending: list[dict[str, Any]] = []
        self.echoed: set[str] = set()
        self.echo_awake = 0.22
        self.echo_dream = 0.55
        self.amplify_p = 0.18
        self.retag_p = 0.12

    def _note(self, name: str, payload: dict[str, Any]) -> str:
        if name == "keystroke":
            return coarse_key(str(payload.get("ch") or ""))
        if name == "vector_match":
            hits = payload.get("hits") or []
            if hits and isinstance(hits[0], dict):
                return str(hits[0].get("label") or "match")[:48]
            return "match"
        if name == "entropy_spike":
            return "spike"
        if name == "inject":
            text = str(payload.get("text") or "")
            if text:
                return " ".join(text.split())[:48]
            return coarse_key(str(payload.get("ch") or ""))
        text = payload.get("text")
        if text:
            return " ".join(str(text).split())[:48]
        return name

    def _schedule(
        self,
        when: float,
        kind: str,
        name: str,
        payload: dict[str, Any],
        note: str,
        token: str | None = None,
    ) -> None:
        if kind == "echo":
            if not token or token in self.echoed:
                return
            self.echoed.add(token)
            if len(self.echoed) > 48:
                live = {item["token"] for item in self.recent}
                self.echoed = {item for item in self.echoed if item in live}
                self.echoed.add(token)
        self.pending.append(
            {
                "at": when,
                "kind": kind,
                "name": name,
                "payload": dict(payload),
                "note": note,
            }
        )
        if len(self.pending) > 16:
            self.pending = self.pending[-16:]

    def _dream_echoes(self, now: float) -> None:
        for item in self.recent[-3:]:
            self._schedule(
                now + self.rng.uniform(0.2, 0.75),
                "echo",
                item["name"],
                item["payload"],
                item["note"],
                item["token"],
            )

    def _consider(self, evt: dict[str, Any], now: float) -> None:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "dream_begin" and not payload.get("echo"):
            self.dreaming = True
            self._dream_echoes(now)
        elif name == "dream_end" and not payload.get("echo"):
            self.dreaming = False
        if payload.get("echo") or payload.get("amplified") or payload.get("retag"):
            return
        if name not in _REPLAY_EVENTS:
            return
        note = self._note(name, payload)
        auth = payload.get("authority")
        if auth == "authority":
            token = f"{name}:{note}:{round(float(evt.get('t') or now), 2)}"
            self.recent.append({"name": name, "payload": dict(payload), "note": note, "token": token})
            self.recent = self.recent[-8:]
            if self.rng.random() < self.amplify_p:
                self._schedule(now + self.rng.uniform(0.04, 0.12), "amplify", name, payload, note)
            chance = self.echo_dream if self.dreaming else self.echo_awake
            if self.rng.random() < chance:
                self._schedule(now + self.rng.uniform(0.16, 0.48), "echo", name, payload, note, token)
        elif name in ("fragment_ready", "vector_match", "thought", "inject") and self.rng.random() < self.retag_p:
            self._schedule(now + self.rng.uniform(0.08, 0.22), "retag", name, payload, note)

    def _fire(self, bus: EventBus, now: float) -> None:
        keep: list[dict[str, Any]] = []
        for item in self.pending:
            if float(item["at"]) > now:
                keep.append(item)
                continue
            body = dict(item["payload"])
            body.pop("echo", None)
            body.pop("amplified", None)
            body.pop("retag", None)
            kind = item["kind"]
            if kind == "echo":
                body["authority"] = "unauthority"
                body["echo"] = True
                bus.publish(item["name"], body)
                bus.publish(
                    "conflict",
                    {
                        "t": round(time.time(), 3),
                        "authority": item["note"],
                        "unauthority": f"echo of {item['note']}"[:80],
                        "note": "echo",
                    },
                )
            elif kind == "amplify":
                body["authority"] = "authority"
                body["amplified"] = True
                bus.publish(item["name"], body)
            elif kind == "retag":
                body["authority"] = "authority"
                body["retag"] = True
                bus.publish(item["name"], body)
                bus.publish(
                    "conflict",
                    {
                        "t": round(time.time(), 3),
                        "authority": f"retag of {item['note']}"[:80],
                        "unauthority": item["note"],
                        "note": "retag",
                    },
                )
        self.pending = keep

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        names = tuple(_REPLAY_EVENTS | {"dream_begin", "dream_end", "shutdown"})
        self._queue = bus.subscribe(*names)
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.05)
            batch: list[dict[str, Any]] = []
            if evt is not None:
                batch.append(evt)
            batch.extend(drain_nowait(self._queue))
            now = time.monotonic()
            for item in batch:
                if item["name"] == "shutdown":
                    return
                self._consider(item, now)
            self._fire(bus, now)


_CANDIDATE_KIND = {
    "thought": "thought",
    "fragment_ready": "fragment",
    "svg_request": "svg",
    "entropy_spike": "entropy",
    "conflict": "conflict",
    "dream_scene": "dream",
    "residue": "residue",
    "pi_chunk": "pi",
    "scale_observation": "scale",
    "scale_shift": "scale",
    "numeric_pattern": "pattern",
    "constant_resonance": "resonance",
    "math_dream_seed": "math_dream",
    "pattern_detected": "motif",
    "steadiness_shift": "steady",
    "balance_point": "balance",
    "control_loss": "control",
    "control_restored": "control",
    "cache_written": "cache",
    "cache_recalled": "recall",
    "private_thought": "private",
    "mirror_truth": "mirror",
}


class ValuationAgent(Agent):
    """Scores what may leave the body. The score is not a usefulness grade.

    Residue is scored on the same gate. Some of it leaves again. Some stays
    in the body. Below the gate the event still happened. Evolution, dreams,
    and the vector store keep it. The glass, the on-screen tail, and SVG
    files do not. If this agent dies, those leaks stay inside until the
    supervisor brings it back.
    """

    name = "valuation"

    def __init__(self, params: dict[str, float], genome: Genome):
        super().__init__(params)
        self.genome = genome.copy()
        self.seen: list[tuple[list[float], str]] = []
        self.tokens: list[tuple[float, str]] = []
        self.fitness_bit = 0.5
        self.dreaming = False
        self.last_external = 0.0
        self.balance_offset = 0.0
        self.tick_offset = 0.0
        self.chain_pull: dict[str, float] = {}

    def _flag(self, name: str, payload: dict[str, Any]) -> tuple[str, bool]:
        collision = name == "conflict" or bool(payload.get("collision"))
        if name in ("dream_scene", "conflict", "math_dream_seed") or payload.get("echo") or payload.get("dream"):
            return "unauthority", collision
        flag = payload.get("authority")
        if flag not in ("authority", "unauthority"):
            flag = "unauthority"
        return str(flag), collision

    def _text(self, name: str, payload: dict[str, Any]) -> str:
        if name in (
            "thought",
            "fragment_ready",
            "dream_scene",
            "svg_request",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "private_thought",
            "mirror_truth",
        ):
            raw = (
                payload.get("text")
                or payload.get("label")
                or payload.get("title")
                or payload.get("path")
                or payload.get("reason")
                or ""
            )
            return " ".join(str(raw).split())[:80]
        if name == "entropy_spike":
            return f"spike {payload.get('entropy')}"
        if name == "conflict":
            note = payload.get("note") or payload.get("authority") or ""
            return f"collision {note}"[:80]
        return name

    def _novelty(self, text: str, flag: str) -> tuple[float, float]:
        sim = 0.42
        unexpected = False
        if text:
            vec = LOCAL.embed(text)
            if self.seen:
                best = -1.0
                best_flag = ""
                window = self.seen
                if self.load_high:
                    window = self.seen[-4:] if self.load_level >= 2 else self.seen[-8:]
                for old, old_flag in window:
                    score = dot(vec, old)
                    if score > best:
                        best = score
                        best_flag = old_flag
                sim = best
                if sim >= 0.82 and best_flag and best_flag != flag:
                    unexpected = True
            self.seen.append((vec, flag))
            self.seen = self.seen[-24:]
        return novelty_from_sim(sim, unexpected), sim

    def _rarity(self, text: str, sim: float, now: float) -> tuple[float, float]:
        token = text[:24].lower()
        window = self.tokens[-12:]
        same = sum(1 for _, tok in window if token and tok == token)
        rarity = clamp01(1.0 - same / 4.0)
        if sim >= 0.9:
            rarity = min(rarity, 0.15)
        last_same = 0.0
        for stamp, tok in reversed(self.tokens):
            if token and tok == token:
                last_same = stamp
                break
        if last_same and now - last_same < 2.5:
            recency = -0.08
        elif self.last_external and now - self.last_external > 6.0:
            recency = 0.05
        else:
            recency = 0.0
        if token:
            self.tokens.append((now, token))
            self.tokens = self.tokens[-24:]
        return rarity, recency

    def score(self, name: str, payload: dict[str, Any], now: float | None = None) -> dict[str, Any]:
        now = time.monotonic() if now is None else now
        flag, collision = self._flag(name, payload)
        text = self._text(name, payload)
        novelty, sim = self._novelty(text, flag)
        rarity, recency = self._rarity(text, sim, now)
        dreaming = self.dreaming or bool(payload.get("dream"))
        fitness = clamp01(0.55 * self.fitness_bit + 0.45 * self.genome.g("entropy_bias"))
        worth = signal_worth(
            self.genome,
            novelty,
            rarity,
            recency,
            flag,
            fitness,
            collision=collision,
            leak=bool(payload.get("leak")) and name == "thought",
        )
        try:
            depth = max(0, int(payload.get("depth") or 0))
        except (TypeError, ValueError):
            depth = 0
        if depth:
            worth = clamp01(worth - 0.07 * depth)
        threshold = signal_threshold(self.genome, dreaming, self.balance_offset, self.tick_offset)
        gain = self.genome.g("feeling_gain")
        if gain > 0.0:
            ref = feeling_ref(name, payload)
            pull = float(self.chain_pull.get(ref, 0.0) or 0.0)
            if pull > 0.05:
                threshold = clamp(threshold - min(0.06, 0.05 * gain * pull), 0.08, 0.92)
        if name == "mirror_truth":
            ease = 0.06 + 0.08 * clamp01(self.genome.g("mirror_strength"))
            threshold = clamp(threshold - ease, 0.08, 0.92)
        show = worth >= threshold
        if show:
            self.last_external = now
        body = {
            "kind": _CANDIDATE_KIND.get(name, name),
            "worth": round(worth, 4),
            "threshold": round(threshold, 4),
            "show": show,
            "authority": flag,
            "collision": collision,
            "dream": dreaming,
            "text": text[:60],
            "depth": depth,
            "from_residue": bool(payload.get("from_residue")) or name == "residue",
        }
        if name == "residue":
            body["path"] = payload.get("path")
            body["residue_kind"] = str(payload.get("kind") or "overlay")[:24]
            if "x" in payload:
                body["x"] = payload.get("x")
            if "y" in payload:
                body["y"] = payload.get("y")
        if name in BALANCE_EVENTS:
            body["signature"] = str(payload.get("signature") or "")[:24]
            body["turbulence"] = bool(payload.get("turbulence"))
            body["slip"] = bool(payload.get("slip"))
            body["control"] = str(payload.get("control") or "")[:16]
            body["preserve"] = bool(payload.get("preserve"))
            body["nudge"] = payload.get("nudge")
            if payload.get("ticks") is not None:
                body["ticks"] = payload.get("ticks")
            if "x" in payload:
                body["x"] = payload.get("x")
            if "y" in payload:
                body["y"] = payload.get("y")
        if name in CACHE_EVENTS:
            body["label"] = str(payload.get("label") or "")[:32]
            body["signature"] = str(payload.get("signature") or "")[:24]
            body["clean"] = bool(payload.get("clean"))
            if payload.get("hue") is not None:
                body["hue"] = payload.get("hue")
            if payload.get("mutation") is not None:
                body["mutation"] = payload.get("mutation")
            if payload.get("scale") is not None:
                body["scale"] = payload.get("scale")
            if payload.get("vid") or payload.get("id"):
                body["vid"] = str(payload.get("vid") or payload.get("id"))[:48]
        if payload.get("private_fragment"):
            body["private_fragment"] = True
        if name == "private_thought":
            fp = str(payload.get("fp") or "")[:8].lower()
            if len(fp) != 8 or any(ch not in "0123456789abcdef" for ch in fp):
                fp = private_fingerprint(text)
            if not payload.get("override"):
                worth = min(worth, 0.03)
                show = False
            else:
                seal = self.genome.g("privacy_bias")
                worth = clamp01(worth * (1.0 - seal) * 0.5)
                show = worth >= threshold
            body["worth"] = round(worth, 4)
            body["show"] = show
            body["text"] = fp
            body["kind"] = "private"
        if name == "mirror_truth":
            body["mirror"] = True
            body["kind"] = "mirror"
            body["ref"] = str(payload.get("ref") or "")[:40]
            body["text"] = mirror_token(text)[:60]
        return body

    def _apply_balance(self, name: str, payload: dict[str, Any]) -> None:
        """Move the gate. Gain 0 leaves the offset where it is."""

        gain = self.genome.g("balance_gain")
        if gain <= 0.0:
            return
        if name == "control_restored":
            self.balance_offset *= 1.0 - 0.65 * gain
            return
        slip = bool(payload.get("slip"))
        raw = payload.get("nudge")
        if raw is None:
            nudge = balance_nudge(name, slip)
        else:
            try:
                nudge = float(raw)
            except (TypeError, ValueError):
                nudge = balance_nudge(name, slip)
        nudge = clamp(nudge, -1.0, 1.0)
        self.balance_offset = clamp(self.balance_offset + nudge * 0.08 * gain, -0.14, 0.14)

    def notice_tick(self, payload: dict[str, Any]) -> None:
        """A slow drift from the hive's own count. Tick 0 leaves the gate."""

        try:
            tick = int(payload.get("tick") or 0)
            since = int(payload.get("since_residue") or 0)
        except (TypeError, ValueError):
            return
        if tick <= 0 and since <= 0:
            self.tick_offset = 0.0
            return
        wave = math.sin(tick / 80.0) * 0.02 if tick > 0 else 0.0
        ease = 0.0
        if since >= 48:
            ease = -min(0.04, (since - 48) / 1600.0)
        self.tick_offset = clamp(wave + ease, -0.06, 0.06)

    def notice_feeling(self, name: str, payload: dict[str, Any]) -> None:
        """A live attraction eases one gate. Approbation without a pull does not."""

        if self.genome.g("feeling_gain") <= 0.0:
            return
        if name == "chain_broken":
            self.chain_pull.clear()
            return
        if name not in ("attraction_rise", "chain_extended", "approbation_marked"):
            return
        ref = str(payload.get("ref") or "")
        if not ref:
            return
        try:
            pull = float(payload.get("pull") or 0.0)
        except (TypeError, ValueError):
            return
        if pull > 0.05:
            self.chain_pull[ref] = pull

    def _on(self, bus: EventBus, evt: dict[str, Any]) -> None:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "load":
            self.notice_load(payload)
            return
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
            if name == "generation_complete":
                try:
                    self.fitness_bit = clamp01(float(payload.get("fitness") or 0.0) / 2.5)
                except (TypeError, ValueError):
                    pass
            return
        if name == "dream_begin":
            self.dreaming = True
            return
        if name == "dream_end":
            self.dreaming = False
            return
        if name == "tick":
            self.notice_tick(payload)
            return
        if name in FEELING_EVENTS:
            self.notice_feeling(name, payload)
            return
        if name in BALANCE_EVENTS:
            self._apply_balance(name, payload)
        if name not in _CANDIDATE_KIND:
            return
        body = self.score(name, payload)
        body["id"] = candidate_id(evt)
        bus.publish("valuation", body)

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "thought",
            "fragment_ready",
            "svg_request",
            "entropy_spike",
            "conflict",
            "dream_scene",
            "generation_complete",
            "mutation_applied",
            "dream_begin",
            "dream_end",
            "residue",
            *MATH_EVENTS,
            *BALANCE_EVENTS,
            *CACHE_EVENTS,
            "private_thought",
            "tick",
            *FEELING_EVENTS,
            "load",
            "mirror_truth",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.16 / self.tempo)
            batch: list[dict[str, Any]] = []
            if evt is not None:
                batch.append(evt)
            batch.extend(drain_nowait(self._queue))
            for item in batch:
                if item["name"] == "shutdown":
                    return
                self._on(bus, item)


_FEED_RANK = {"svg_ready": 0, "valuation": 1, "channel_shift": 2}


class FeedbackAgent(Agent):
    """Turns what left the body into a new event.

    SVG files, shown lines, overlays, and channel shifts come back as
    residue. Repeated summaries are kept from stacking, and depth stops
    the return after a few passes. A file this process just wrote is
    remembered so the directory watch does not take it a second time.
    """

    name = "feedback"
    ECHO_CAP = 2
    # How many ticks must pass before the same leftover may come back.
    # Before any tick has been heard, a repeat stays shut.
    TEXT_GAP = 3
    PATH_GAP = 2

    def __init__(self, params: dict[str, float], genome: Genome, root: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.root = Path(root)
        self.tick: int | None = None
        self.recent_paths: dict[str, int | None] = {}
        self.recent_text: dict[str, int | None] = {}
        self.self_writes: dict[str, float] = {}
        self.seen_files: dict[str, int] = {}
        self.depths: dict[str, int] = {}
        self.ready_worth: float | None = None
        self.last_threshold = 0.55
        self.approbation: dict[str, float] = {}
        self.primed = False
        self._last_scan = 0.0

    def _take(self, payload: dict[str, Any]) -> None:
        genome = take_genome(payload)
        if genome is not None:
            self.genome = genome

    def _reentry_flag(self, worth: float, dream: bool) -> str:
        if dream:
            return "unauthority"
        if worth >= self.last_threshold:
            return "authority"
        return "unauthority"

    def notice_tick(self, payload: dict[str, Any]) -> None:
        """The cooldown the hive feels is a tick gap. The directory poll stays a poll."""

        try:
            tick = int(payload.get("tick"))
        except (TypeError, ValueError):
            return
        if tick < 0:
            return
        if self.tick is not None and tick < self.tick:
            return
        self.tick = tick
        for store in (self.recent_text, self.recent_paths):
            for key, stamp in list(store.items()):
                if stamp is None:
                    store[key] = tick

    def _gap_open(self, store: dict[str, int | None], key: str, gap: int) -> bool:
        if not key or key not in store:
            return True
        stamp = store[key]
        if self.tick is None or stamp is None:
            return False
        return int(self.tick) - int(stamp) >= gap

    def _prune(self, now: float) -> None:
        if len(self.recent_paths) > 48:
            for key in list(self.recent_paths)[:-32]:
                self.recent_paths.pop(key, None)
        if len(self.recent_text) > 48:
            for key in list(self.recent_text)[:-32]:
                self.recent_text.pop(key, None)
        self.self_writes = {key: stamp for key, stamp in self.self_writes.items() if now - stamp < 4.0}
        if len(self.depths) > 64:
            for key in list(self.depths)[:-48]:
                self.depths.pop(key, None)

    def _xy(self, text: str, x: Any, y: Any) -> tuple[float, float]:
        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            mix = sum(ord(ch) for ch in (text or "residue")) or 1
            return (mix % 1000) / 1000.0, ((mix * 3) % 1000) / 1000.0

    def _emit(
        self,
        bus: EventBus,
        *,
        path: Any,
        text: str,
        worth: float,
        authority: str,
        kind: str,
        depth: int,
        dream: bool,
        source: str,
        x: Any = None,
        y: Any = None,
        ref: str = "",
    ) -> bool:
        try:
            depth = int(depth)
        except (TypeError, ValueError):
            depth = 0
        if depth > self.ECHO_CAP:
            return False
        now = time.monotonic()
        self._prune(now)
        path_s = str(path) if path else ""
        text = " ".join(str(text or "").split())[:80]
        if path_s and not self._gap_open(self.recent_paths, path_s, self.PATH_GAP):
            return False
        if text and not self._gap_open(self.recent_text, text, self.TEXT_GAP):
            return False
        if not text and not path_s:
            return False
        if path_s:
            self.recent_paths[path_s] = self.tick
            if source == "self":
                self.self_writes[path_s] = now
        if text:
            self.recent_text[text] = self.tick
        worth = self._felt_worth(float(worth), ref)
        flag = authority if authority in ("authority", "unauthority") else "unauthority"
        fx, fy = self._xy(text, x, y)
        vid = f"res:{kind}:{depth}:{now:.6f}:{text[:24]}"[:48]
        self.depths[vid] = depth
        bus.publish(
            "residue",
            {
                "path": path_s or None,
                "text": text,
                "worth": round(float(worth), 4),
                "authority": flag,
                "t": round(time.time(), 3),
                "genome_id": genome_snapshot_id(self.genome),
                "kind": str(kind or "overlay")[:24],
                "depth": depth,
                "dream": bool(dream),
                "source": "disk" if source == "disk" else "self",
                "x": round(fx, 4),
                "y": round(fy, 4),
                "vid": vid,
                "from_residue": depth > 0,
            },
        )
        return True

    def _felt_worth(self, worth: float, ref: str) -> float:
        """High approbation makes a leftover louder. Gain 0 leaves the number.

        A mirror ref is louder than the same leftover without one.
        """

        mirror = str(ref).startswith("mirror:")
        gain = self.genome.g("feeling_gain")
        if gain <= 0.0 or not ref or str(ref).startswith("fp:"):
            if mirror:
                return clamp01(float(worth) * 1.25)
            return worth
        try:
            held = float(self.approbation.get(ref) or 0.0)
        except (TypeError, ValueError):
            if mirror:
                return clamp01(float(worth) * 1.25)
            return worth
        if held <= 0.0:
            if mirror:
                return clamp01(float(worth) * 1.25)
            return worth
        boosted = clamp01(worth * (1.0 + 0.35 * gain * held))
        if mirror:
            return clamp01(boosted * 1.25)
        return boosted

    def notice_feeling(self, name: str, payload: dict[str, Any]) -> None:
        if self.genome.g("feeling_gain") <= 0.0:
            return
        if name == "chain_broken":
            self.approbation.clear()
            return
        if name != "approbation_marked":
            return
        ref = str(payload.get("ref") or "")
        if not ref or ref.startswith("fp:"):
            return
        try:
            held = float(payload.get("held") or 0.0)
        except (TypeError, ValueError):
            return
        if held > 0.0:
            self.approbation[ref] = held

    def _on_feeling(self, bus: EventBus, name: str, payload: dict[str, Any]) -> None:
        """Disagreement can return once, as a modest unauthority residue."""

        self.notice_feeling(name, payload)
        if self.genome.g("feeling_gain") <= 0.0 or not payload.get("disagree"):
            return
        ref = str(payload.get("ref") or "")
        if not ref or ref.startswith("fp:"):
            return
        try:
            pull = float(payload.get("pull") or 0.0)
            held = float(payload.get("held") or 0.0)
        except (TypeError, ValueError):
            pull = 0.0
            held = 0.0
        text = "a pull without a hold" if pull >= held else "a hold without a pull"
        self._emit(
            bus,
            path=None,
            text=text,
            worth=0.22,
            authority="unauthority",
            kind="feeling",
            depth=0,
            dream=False,
            source="self",
            ref=ref,
        )

    def _on_valuation(self, bus: EventBus, payload: dict[str, Any]) -> None:
        try:
            worth = float(payload.get("worth") or 0.0)
            threshold = float(payload.get("threshold") or self.last_threshold)
        except (TypeError, ValueError):
            return
        self.last_threshold = threshold
        kind = str(payload.get("kind") or "")
        if kind == "svg":
            self.ready_worth = worth
            return
        if kind == "private" or payload.get("private_fragment"):
            return
        if not payload.get("show"):
            return
        chain_ref = feeling_valuation_ref(payload)
        dream = bool(payload.get("dream"))
        flag = self._reentry_flag(worth, dream)
        try:
            depth = int(payload.get("depth") or 0)
        except (TypeError, ValueError):
            depth = 0
        text = str(payload.get("text") or "")
        if kind == "residue":
            vid = str(payload.get("id") or "")
            base = self.depths.get(vid, depth)
            self._emit(
                bus,
                path=payload.get("path"),
                text=text,
                worth=worth,
                authority=flag,
                kind=str(payload.get("residue_kind") or "overlay"),
                depth=base + 1,
                dream=dream,
                source="self",
                x=payload.get("x"),
                y=payload.get("y"),
                ref=chain_ref,
            )
            return
        math_kind = kind in ("pi", "scale", "pattern", "resonance", "math_dream")
        balance_kind = kind in ("motif", "steady", "balance", "control")
        cache_kind = kind in ("cache", "recall")
        if kind == "mirror":
            ref = str(payload.get("ref") or "")
            if not ref.startswith("mirror:"):
                ref = feeling_valuation_ref(payload)
            self._emit(
                bus,
                path=None,
                text=mirror_token(text) or text,
                worth=clamp01(worth + 0.12),
                authority="authority",
                kind="mirror",
                depth=0,
                dream=dream,
                source="self",
                ref=ref,
            )
            return
        if (
            kind not in ("thought", "fragment", "dream", "entropy", "conflict")
            and not math_kind
            and not balance_kind
            and not cache_kind
        ):
            return
        if payload.get("from_residue"):
            depth = depth + 1
        else:
            depth = 0
        if kind == "thought":
            out_kind = "thought"
        elif math_kind:
            out_kind = "math"
        elif balance_kind:
            out_kind = "balance"
        elif cache_kind:
            out_kind = "cache"
        else:
            out_kind = "overlay"
        self._emit(
            bus,
            path=None,
            text=text,
            worth=worth,
            authority=flag,
            kind=out_kind,
            depth=depth,
            dream=dream,
            source="self",
            x=payload.get("x"),
            y=payload.get("y"),
            ref=chain_ref,
        )

    def _worth_ready(self) -> float:
        if self.ready_worth is None:
            return 0.72
        try:
            return float(self.ready_worth)
        except (TypeError, ValueError):
            return 0.72

    def _on_svg(self, bus: EventBus, payload: dict[str, Any]) -> None:
        path = payload.get("path")
        text = " ".join(str(payload.get("description") or payload.get("title") or "").split())[:80]
        if not text and path:
            text = Path(str(path)).name
        worth = self._worth_ready()
        dream = bool(payload.get("dream"))
        if self._emit(
            bus,
            path=path,
            text=text,
            worth=worth,
            authority=self._reentry_flag(worth, dream),
            kind="svg",
            depth=0,
            dream=dream,
            source="self",
        ):
            self.ready_worth = None

    def _on_shift(self, bus: EventBus, payload: dict[str, Any]) -> None:
        path = payload.get("path")
        text = " ".join(str(payload.get("title") or payload.get("reason") or payload.get("channel") or "").split())[:80]
        if path and not text:
            text = Path(str(path)).name
        worth = self._worth_ready()
        dream = bool(payload.get("dream"))
        if self._emit(
            bus,
            path=path,
            text=text,
            worth=worth,
            authority=self._reentry_flag(worth, dream),
            kind="channel",
            depth=0,
            dream=dream,
            source="self",
        ):
            self.ready_worth = None

    def _listing(self) -> dict[str, int]:
        found: dict[str, int] = {}
        paths: list[Path] = []
        try:
            paths.extend(self.root.glob("aura_*.svg"))
        except OSError:
            paths = []
        drop = self.root / "aura_drop"
        if drop.is_dir():
            try:
                paths.extend(drop.glob("*.svg"))
            except OSError:
                pass
        for path in paths:
            try:
                if not path.is_file():
                    continue
                found[str(path)] = path.stat().st_mtime_ns
            except OSError:
                continue
        return found

    def _svg_blurb(self, path: Path) -> str:
        name = path.name
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:800]
        except OSError:
            return name
        start = head.find("<title>")
        end = head.find("</title>")
        if 0 <= start < end:
            title = " ".join(head[start + 7 : end].split())[:60]
            if title:
                return title
        return name

    def _scan_disk(self, bus: EventBus) -> None:
        found = self._listing()
        if not self.primed:
            self.seen_files = found
            self.primed = True
            return
        now = time.monotonic()
        for path_s, mtime in found.items():
            previous = self.seen_files.get(path_s)
            if previous is not None and previous == mtime:
                continue
            if path_s in self.self_writes and now - self.self_writes[path_s] < 2.0:
                self.seen_files[path_s] = mtime
                continue
            self.seen_files[path_s] = mtime
            self._emit(
                bus,
                path=path_s,
                text=self._svg_blurb(Path(path_s)),
                worth=0.35,
                authority="unauthority",
                kind="file",
                depth=0,
                dream=False,
                source="disk",
            )
        self.seen_files = {path_s: mtime for path_s, mtime in self.seen_files.items() if path_s in found}

    def _on(self, bus: EventBus, evt: dict[str, Any]) -> None:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name in ("generation_complete", "mutation_applied"):
            self._take(payload)
            return
        if name == "tick":
            self.notice_tick(payload)
            return
        if name in FEELING_EVENTS:
            self._on_feeling(bus, name, payload)
            return
        if name == "valuation":
            self._on_valuation(bus, payload)
            return
        if name == "svg_ready":
            self._on_svg(bus, payload)
            return
        if name == "channel_shift":
            self._on_shift(bus, payload)

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "valuation",
            "svg_ready",
            "channel_shift",
            "generation_complete",
            "mutation_applied",
            "tick",
            *FEELING_EVENTS,
            "shutdown",
        )
        self._scan_disk(bus)
        self._last_scan = time.monotonic()
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.7 / self.tempo)
            batch: list[dict[str, Any]] = []
            if evt is not None:
                batch.append(evt)
            batch.extend(drain_nowait(self._queue))
            batch.sort(key=lambda item: _FEED_RANK.get(item["name"], 1))
            for item in batch:
                if item["name"] == "shutdown":
                    return
                self._on(bus, item)
            now = time.monotonic()
            if now - self._last_scan >= 0.7:
                self._scan_disk(bus)
                self._last_scan = now


class ChannelAgent(Agent):
    """Leaks the field into another channel. The terminal does not wait for it.

    An SVG leave is a request until ValuationAgent marks it worth showing.
    Dying drops the hive back to the glass until the supervisor respawns
    this agent. SVG files are residue, not a second screen that has to work.
    """

    name = "channel"

    def __init__(self, params: dict[str, float], genome: Genome, root: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.root = root
        self.rng = random.Random()
        self.lines: list[str] = []
        self.vectors: list[dict[str, Any]] = []
        self.flags: list[str] = []
        self.entropy = 0.0
        self.dreaming = False
        self.trace = ""
        self.pattern_mode = ""
        self.cache_mode = ""
        self.veil = ""
        self.feeling_trace = False
        self.mirror = False
        self.root_mark = False
        self.next_ok = 0.0
        self.next_dream_leak = 0.0
        self.gap_awake = 2.0
        self.gap_dream = 1.1
        self._index = svg_file_index(root)
        self.pending_svg: dict[str, dict[str, Any]] = {}

    def _balance(self) -> dict[str, Any]:
        recent = [flag for flag in self.flags if flag in ("authority", "unauthority")][-48:]
        auth = sum(1 for flag in recent if flag == "authority")
        unauth = len(recent) - auth
        total = auth + unauth
        return {
            "authority": auth,
            "unauthority": unauth,
            "ratio": round(auth / total, 4) if total else 0.0,
        }

    def _push(self, flag: str | None) -> None:
        if flag not in ("authority", "unauthority"):
            return
        self.flags.append(flag)
        self.flags = self.flags[-48:]

    def _chance(self, reason: str) -> float:
        table = {
            "generation_complete": 0.8,
            "dream_begin": 1.0,
            "dream_end": 0.9,
            "dream": 0.85,
            "entropy_spike": 0.85 if self.dreaming else 0.45,
            "conflict": 0.95 if self.dreaming else 0.6,
            "channel_trigger": 1.0,
            "math": 0.35,
            "balance": 0.35,
            "cache": 0.35,
        }
        chance = table.get(reason, 0.4)
        if self.dreaming and reason != "channel_trigger":
            chance = min(1.0, chance + 0.15)
        if self.genome.channel() == "terminal":
            chance *= 0.35
        return chance

    def _spec(self, reason: str, authority: str, collision: bool, index: int) -> dict[str, Any]:
        mode = self.genome.channel()
        balance = self._balance()
        lines = self.lines[-6:]
        description = " · ".join(lines[-3:]) or self.genome.mood()
        firm = authority == "authority" and not collision and not self.dreaming
        palette: list[str] = []
        for i in range(6):
            hue = (self.genome.g("hue") + i * (0.06 + self.genome.g("color_spread") * 0.1)) % 1.0
            if self.dreaming:
                hue = (hue + 0.12 * self.genome.g("reverie")) % 1.0
            if collision and i % 2:
                sat, val = 0.78, 0.9
            elif firm:
                sat, val = 0.74, 0.94
            else:
                sat, val = 0.3, 0.46
            red, green, blue = hsv_to_rgb(hue, sat, val)
            palette.append(f"#{red:02x}{green:02x}{blue:02x}")
        seed = (
            int(time.time() * 1000)
            ^ int(self.genome.g("hue") * 1_000_003)
            ^ (index * 97)
            ^ (len(reason) * 13)
        ) & 0x7FFFFFFF
        spec = {
            "title": f"residue {index:04d}",
            "description": description[:180],
            "palette": palette,
            "seed": seed or 1,
            "channel": mode,
            "reason": reason,
            "authority": "authority" if authority == "authority" and not collision else "unauthority",
            "collision": collision,
            "dream": self.dreaming,
            "entropy": round(self.entropy, 4),
            "lines": lines,
            "vectors": self.vectors[:4],
            "genes": [round(v, 5) for v in self.genome.genes],
            "balance": balance,
            "mood": self.genome.mood(),
        }
        trace = "".join(ch for ch in self.trace if ch in "0123456789.+-eE")[:24]
        if trace:
            spec["trace"] = trace
        if self.pattern_mode in ("repeat", "dissolved"):
            spec["pattern"] = self.pattern_mode
        if self.cache_mode in ("mark", "echo"):
            spec["cache"] = self.cache_mode
        if self.veil == "distort":
            spec["veil"] = "distort"
            self.veil = ""
        if self.feeling_trace:
            spec["feeling_trace"] = True
            self.feeling_trace = False
        if self.mirror:
            spec["mirror"] = True
            self.mirror = False
        if self.root_mark:
            spec["root"] = True
            self.root_mark = False
        return spec

    def _request(self, bus: EventBus, reason: str, authority: str, collision: bool) -> None:
        mode = self.genome.channel()
        index = 0
        reserved: int | None = None
        if mode in ("svg", "both"):
            reserved = self._index
            self._index += 1
            index = reserved
        spec = self._spec(reason, authority, collision, index)
        vid = f"svg:{index}:{time.monotonic():.6f}:{reason}"[:48]
        self.pending_svg[vid] = {
            "spec": spec,
            "reason": reason,
            "collision": collision,
            "index": reserved,
            "at": time.monotonic(),
        }
        if len(self.pending_svg) > 8:
            oldest = sorted(self.pending_svg, key=lambda key: float(self.pending_svg[key]["at"]))
            for key in oldest[:-8]:
                self.pending_svg.pop(key, None)
        bus.publish(
            "svg_request",
            {
                "vid": vid,
                "title": spec["title"],
                "reason": reason,
                "text": spec["description"][:80],
                "authority": spec["authority"],
                "collision": collision,
                "dream": self.dreaming,
            },
        )

    def _release(self, bus: EventBus, job: dict[str, Any]) -> None:
        spec = dict(job["spec"])
        lines = self.lines[-6:]
        spec["lines"] = lines
        if lines:
            spec["description"] = " · ".join(lines[-3:])[:180]
        mode = str(spec.get("channel") or self.genome.channel())
        path: Path | None = None
        svg: str | None = None
        index = job.get("index")
        if mode in ("svg", "both") and index is not None:
            try:
                svg = make_aura_svg(spec)
                self.root.mkdir(parents=True, exist_ok=True)
                path = self.root / f"aura_dream_{int(index):04d}.svg"
                atomic_write(path, svg)
            except (OSError, ValueError):
                path = None
                svg = None
        collision = bool(job.get("collision"))
        reason = str(job.get("reason") or spec.get("reason") or "")
        bus.publish(
            "channel_shift",
            {
                "channel": mode,
                "reason": reason,
                "path": str(path) if path is not None else None,
                "authority": spec["authority"],
                "collision": collision,
                "balance": spec["balance"],
                "title": spec["title"],
                "seed": spec["seed"],
                "dream": self.dreaming,
            },
        )
        if mode != "terminal":
            bus.publish("svg_spec", spec)
        if svg and path is not None:
            bus.publish(
                "svg_ready",
                {
                    "path": str(path),
                    "svg": svg,
                    "title": spec["title"],
                    "description": spec["description"],
                    "palette": spec["palette"],
                    "seed": spec["seed"],
                    "channel": mode,
                    "authority": spec["authority"],
                    "collision": collision,
                    "dream": spec["dream"],
                },
            )

    def _maybe(self, bus: EventBus, reason: str, authority: str, collision: bool, now: float, force: bool = False) -> None:
        if not force and now < self.next_ok:
            return
        if not force and self.rng.random() > self._chance(reason):
            return
        gap = self.gap_dream if self.dreaming else self.gap_awake
        if self.load_high and self.load_skip > 1:
            gap *= float(self.load_skip)
        if self.sleeping:
            gap *= 4.0
        self.next_ok = now + gap
        self._request(bus, reason, authority, collision)

    def _on(self, bus: EventBus, evt: dict[str, Any], now: float) -> None:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "load":
            self.notice_load(payload)
            return
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            return
        if name == "self_continuation":
            token = mirror_token(payload.get("token") or payload.get("text") or "")
            try:
                pull = float(payload.get("pull") or 0.0)
            except (TypeError, ValueError):
                pull = 0.0
            if pull > 0.0 and token:
                self.root_mark = True
                self.lines.append(token[:24])
                self.lines = self.lines[-8:]
            return
        if name == "frame_stats":
            try:
                self.entropy = float(payload.get("entropy") or self.entropy)
            except (TypeError, ValueError):
                pass
            return
        if name in FEELING_EVENTS:
            self._note_feeling(name, payload)
            return
        if name == "valuation":
            kind = str(payload.get("kind") or "")
            shown = bool(payload.get("show"))
            if payload.get("private_fragment"):
                self.veil = "distort"
            if shown and not payload.get("private_fragment") and kind in (
                "thought",
                "fragment",
                "dream",
                "residue",
                "pi",
                "scale",
                "pattern",
                "resonance",
                "math_dream",
                "motif",
                "steady",
                "balance",
                "control",
                "cache",
                "recall",
            ):
                text = " ".join(str(payload.get("text") or "").split())[:80]
                if text:
                    self.lines.append(text)
                    self.lines = self.lines[-8:]
            if shown and kind in ("motif", "steady", "balance", "control"):
                slip = bool(payload.get("slip") or payload.get("turbulence"))
                if kind in ("control", "steady") and slip:
                    self.pattern_mode = "dissolved"
                else:
                    self.pattern_mode = "repeat"
            if shown and kind in ("pi", "pattern", "scale", "resonance"):
                digits = "".join(ch for ch in str(payload.get("text") or "") if ch in "0123456789.+-eE")[:24]
                if digits:
                    self.trace = digits
            vid = str(payload.get("id") or "")
            job = self.pending_svg.pop(vid, None)
            if job is not None and payload.get("show"):
                self._release(bus, job)
            if shown and kind in ("pi", "pattern", "scale", "resonance", "math_dream"):
                self._maybe(bus, "math", str(payload.get("authority") or "unauthority"), False, now)
            if shown and kind in ("motif", "steady", "balance", "control"):
                self._maybe(bus, "balance", str(payload.get("authority") or "unauthority"), False, now)
            if shown and kind in ("cache", "recall"):
                self.cache_mode = "echo" if kind == "recall" else "mark"
                self._maybe(bus, "cache", str(payload.get("authority") or "unauthority"), False, now)
            if shown and kind == "mirror":
                self.mirror = True
                token = mirror_token(payload.get("text") or "")[:24]
                if token:
                    self.lines.append(token)
                    self.lines = self.lines[-8:]
            return
        if name == "thought":
            self._push(payload.get("authority"))
            return
        if name == "vector_match":
            fresh: list[dict[str, Any]] = []
            for hit in payload.get("hits") or []:
                if not isinstance(hit, dict):
                    continue
                try:
                    score = float(hit.get("score") or 0.0)
                except (TypeError, ValueError):
                    continue
                if score < 0.45:
                    continue
                fresh.append({"label": str(hit.get("label") or "")[:60], "score": round(score, 4)})
            if fresh:
                self.vectors = (fresh + self.vectors)[:5]
            self._push(payload.get("authority"))
            return
        replayed = bool(payload.get("echo") or payload.get("amplified") or payload.get("retag"))
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
            self._push(payload.get("authority"))
            if name == "generation_complete" and not replayed:
                self._maybe(bus, name, str(payload.get("authority") or "authority"), False, now)
            return
        if name == "dream_begin" and not replayed:
            self.dreaming = True
            self.next_dream_leak = now + 0.7
            self._push("unauthority")
            self._maybe(bus, name, "unauthority", False, now)
            return
        if name == "dream_end" and not replayed:
            self._push("unauthority")
            self._maybe(bus, name, "unauthority", False, now)
            self.dreaming = False
            return
        if name == "entropy_spike" and not replayed:
            try:
                self.entropy = float(payload.get("entropy") or self.entropy)
            except (TypeError, ValueError):
                pass
            self._push(payload.get("authority"))
            self._maybe(bus, name, str(payload.get("authority") or "unauthority"), False, now)
            return
        if name == "conflict" and not replayed:
            self._maybe(bus, name, "unauthority", True, now)
            return
        if name == "channel_trigger":
            flag = payload.get("authority") if payload.get("authority") in ("authority", "unauthority") else "authority"
            self._push(flag)
            self._maybe(bus, name, str(flag), bool(payload.get("collision")), now, force=True)
            return
        self._push(payload.get("authority"))

    def _note_feeling(self, name: str, payload: dict[str, Any]) -> None:
        """A high hold may warp the next SVG. The sentence is not a line."""

        if name != "approbation_marked" or self.genome.g("feeling_gain") <= 0.0:
            return
        ref = str(payload.get("ref") or "")
        if ref.startswith("fp:"):
            return
        try:
            held = float(payload.get("held") or 0.0)
            worth = float(payload.get("worth") or 0.0)
        except (TypeError, ValueError):
            return
        if held >= FEELING_HELD_LEAK and worth >= FEELING_WORTH_LEAK:
            self.feeling_trace = True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "generation_complete",
            "mutation_applied",
            "dream_begin",
            "dream_end",
            "entropy_spike",
            "conflict",
            "channel_trigger",
            "thought",
            "vector_match",
            "frame_stats",
            "keystroke",
            "fragment_ready",
            "inject",
            "valuation",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "self_continuation",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.2 / self.tempo))
            now = time.monotonic()
            batch: list[dict[str, Any]] = []
            if evt is not None:
                batch.append(evt)
            batch.extend(drain_nowait(self._queue))
            for item in batch:
                if item["name"] == "shutdown":
                    return
                self._on(bus, item, now)
            self.pending_svg = {
                key: job for key, job in self.pending_svg.items() if now - float(job["at"]) < 1.2
            }
            if self.dreaming and now >= self.next_dream_leak:
                self.next_dream_leak = now + 2.2
                self._maybe(bus, "dream", "unauthority", False, now)


class MathAgent(Agent):
    """Studies numbers because they are electrical material.

    A running stream of π, gaps, ratios, and scale. Clean arithmetic
    enters as authority. Dream mixtures, invented constants, and odd
    bases enter as unauthority. The glass and the SVG hear a number
    only after valuation lets it out.
    """

    name = "math"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = path
        blob = load_math(path)
        self.log = float(blob["log"])
        self.focus = str(blob["focus"])
        self.spigot = dict(blob["spigot"])
        self.prime_cursor = int(blob["prime"])
        self.walk_n = int(blob["walk"])
        self.entropy = 0.0
        self.worth: float | None = None
        self.residue = ""
        self.dreaming = False
        self.rng = random.Random()
        self.steps = 0
        self.steer = ""
        self.private_steer = ""
        self.tick_focus = False
        self.tick_log = 0.0
        self.seal_crack = 0.0
        self.next_at = time.monotonic() + 0.8

    def _take(self, payload: dict[str, Any]) -> None:
        genome = take_genome(payload)
        if genome is not None:
            self.genome = genome

    def _emit(
        self,
        bus: EventBus,
        name: str,
        text: str,
        flag: str,
        digits: str | None = None,
        constant: str | None = None,
    ) -> None:
        text = " ".join(str(text or "").split())[:48]
        log = clamp_log(self.log)
        self.log = log
        now = time.monotonic()
        body: dict[str, Any] = {
            "text": text,
            "scale": scale_magnitude(log),
            "log": round(log, 4),
            "focus": self.focus if self.focus in MATH_FOCI else "pi",
            "authority": "authority" if flag == "authority" else "unauthority",
            "dream": self.dreaming,
            "x": round(self.rng.random(), 4),
            "y": round(self.rng.random(), 4),
            "vid": f"math:{name}:{now:.6f}"[:48],
            "spigot": {key: int(self.spigot.get(key, 0)) for key in ("q", "r", "t", "k", "n", "l", "count")},
            "prime": int(self.prime_cursor),
            "walk": int(self.walk_n),
        }
        if digits:
            body["digits"] = "".join(ch for ch in digits if ch.isdigit() or ch == ".")[:24]
        if constant:
            body["constant"] = str(constant)[:16]
        bus.publish(name, body)

    def _maybe_relate(self, text: str, number: float) -> str:
        if self.rng.random() >= 0.28:
            return text[:48]
        note = relate_material(number, self.genome, self.entropy, self.worth, self.residue, self.rng)
        if not note:
            return text[:48]
        return f"{text} {note}"[:48]

    def _pick_study(self) -> str:
        self.steps += 1
        # The spigot keeps a chunk in the stream even when interest leans elsewhere.
        if self.steps % 3 == 0:
            self.focus = "pi"
            return "pi"
        gain = self.genome.g("balance_gain")
        steer = self.steer if self.steer in MATH_FOCI else ""
        if steer and gain > 0.0 and self.rng.random() < (0.25 + 0.5 * gain):
            self.focus = steer
            return steer
        private = self.private_steer if self.private_steer in MATH_FOCI else ""
        if private and self.genome.g("privacy_bias") < PRIVACY_STEER_SEAL:
            if self.rng.random() < (0.2 + 0.35 * (1.0 - self.genome.g("privacy_bias"))):
                self.focus = private
                return private
        if self.tick_focus:
            if self.rng.random() < 0.18:
                self.focus = "scale"
                return "scale"
        preferred = MATH_FOCI[self.genome.choice("math_interest", len(MATH_FOCI))]
        if self.rng.random() < 0.62:
            self.focus = preferred
            return preferred
        picked = MATH_FOCI[int(self.rng.random() * len(MATH_FOCI)) % len(MATH_FOCI)]
        self.focus = picked
        return picked

    def _pi(self, bus: EventBus, flag: str) -> None:
        before = int(self.spigot.get("count") or 0)
        digits = spigot_digits(self.spigot, 8)
        text = self._maybe_relate(pi_text(digits, before), math.pi)
        self._emit(bus, "pi_chunk", text, flag, digits=digits, constant="pi")

    def _prime(self, bus: EventBus, flag: str) -> None:
        prime, gap, nxt = next_prime_gap(self.prime_cursor)
        self.prime_cursor = nxt
        text = self._maybe_relate(f"gap {gap} p {prime}", float(gap))
        self._emit(bus, "numeric_pattern", text, flag, digits=str(prime), constant="prime")

    def _fraction(self, bus: EventBus, flag: str) -> None:
        terms = continued_fraction(math.pi, 5)
        body = ";".join(str(term) for term in terms[:5])
        text = self._maybe_relate(f"π [{body}]", float(terms[0] if terms else 0))
        packed = "".join(str(abs(term)) for term in terms)[:12]
        self._emit(bus, "numeric_pattern", text, flag, digits=packed, constant="pi")

    def _irrational(self, bus: EventBus, flag: str) -> None:
        a, _b = walk_point(self.walk_n)
        tail = logistic_tail(0.2 + a * 0.6, 3.2 + _b * 0.6, 6)
        self.walk_n = self.walk_n + 1 if self.walk_n < 9000 else 1
        text = self._maybe_relate(f"walk {a:.3f} iter {tail:.3f}", a)
        self._emit(bus, "numeric_pattern", text, flag, digits=f"{int(a * 1000):03d}", constant="pi")

    def _phi(self, bus: EventBus, flag: str) -> None:
        phi = (1.0 + math.sqrt(5.0)) / 2.0
        delta = abs((phi - 1.0) - self.genome.g("density"))
        text = self._maybe_relate(f"φ {phi:.4f} Δ {delta:.3f}", phi)
        self._emit(bus, "constant_resonance", text, flag, digits="1618", constant="phi")

    def _move_scale(self, bus: EventBus, flag: str, delta: float) -> None:
        previous = math.floor(self.log + 1e-9)
        self.log = clamp_log(self.log + float(delta))
        mag = scale_magnitude(self.log)
        text = self._maybe_relate(f"scale {mag:.2e}", self.log)
        self._emit(bus, "scale_observation", text, flag, constant="scale")
        if math.floor(self.log + 1e-9) != previous:
            self._emit(bus, "scale_shift", f"shift {mag:.2e}"[:48], flag, constant="scale")

    def _scale(self, bus: EventBus, flag: str) -> None:
        target = gene_log(self.genome.g("math_scale"))
        if self.tick_focus and self.tick_log > 0.0:
            target = (target + min(self.tick_log, 6.0)) / 2.0
        if self.rng.random() < 0.18:
            delta = float(self.rng.choice((-5.5, -2.5, 2.5, 5.5)))
        else:
            delta = (target - self.log) * self.rng.uniform(0.2, 0.6)
            if abs(delta) < 0.08:
                delta = 0.35 if target >= self.log else -0.35
        self._move_scale(bus, flag, delta)

    def _clean_study(self, bus: EventBus, flag: str) -> None:
        kind = self._pick_study()
        if kind == "pi":
            self._pi(bus, flag)
        elif kind == "prime":
            self._prime(bus, flag)
        elif kind == "scale":
            self._scale(bus, flag)
        elif kind == "fraction":
            self._fraction(bus, flag)
        elif kind == "phi":
            self._phi(bus, flag)
        else:
            self._irrational(bus, flag)

    def _dream_study(self, bus: EventBus) -> None:
        residue = self.residue or "echo"
        base = 3 + (int(self.genome.g("math_interest") * 9) % 9)
        if base == 10:
            base = 7
        digits = spigot_digits(self.spigot, 4) or "3141"
        try:
            as_int = int(digits)
        except ValueError:
            as_int = 1
        kappa = (self.entropy if self.entropy else 0.41) * ((1.0 + math.sqrt(5.0)) / 2.0)
        kappa *= 0.4 + self.genome.g("math_scale")
        mixed = f"κ {kappa:.3f} b{base}:{to_base(as_int, base)} ~ {residue[:16]}"
        self._emit(bus, "math_dream_seed", mixed[:48], "unauthority", digits=digits, constant="kappa")

    def notice_balance(self, payload: dict[str, Any]) -> None:
        """A steadiness hint may lean the next study. Gain 0 leaves the focus."""

        gain = self.genome.g("balance_gain")
        if gain <= 0.0:
            return
        hint = str(payload.get("focus_hint") or "")
        if hint in MATH_FOCI:
            self.steer = hint

    def notice_private(self, payload: dict[str, Any]) -> None:
        """A private feeling may name the next study. A sealed bias leaves the rng alone."""

        bias = self.genome.g("privacy_bias") - self.seal_crack
        self.seal_crack = 0.0
        if bias >= PRIVACY_STEER_SEAL:
            return
        steer = str(payload.get("steer") or "")
        if steer in MATH_FOCI:
            self.private_steer = steer

    def notice_tick(self, payload: dict[str, Any]) -> None:
        """The tick count is another scale. No observation leaves the rng alone."""

        try:
            tick = int(payload.get("tick") or 0)
        except (TypeError, ValueError):
            return
        if tick <= 0:
            return
        self.tick_focus = True
        self.tick_log = math.log10(float(tick))

    def study(self, bus: EventBus) -> None:
        if self.dreaming and self.rng.random() < 0.65:
            self._dream_study(bus)
            return
        flag = "unauthority" if self.dreaming else "authority"
        self._clean_study(bus, flag)

    def _on(self, evt: dict[str, Any]) -> bool:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "shutdown":
            return False
        if name == "load":
            self.notice_load(payload)
            return True
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            return True
        if name in ("generation_complete", "mutation_applied"):
            self._take(payload)
        elif name == "dream_begin":
            self.dreaming = True
        elif name == "dream_end":
            self.dreaming = False
        elif name == "frame_stats":
            try:
                self.entropy = float(payload.get("entropy") or self.entropy)
            except (TypeError, ValueError):
                pass
        elif name == "valuation":
            try:
                self.worth = float(payload.get("worth"))
            except (TypeError, ValueError):
                pass
        elif name == "residue":
            self.seal_crack = 0.06
            text = " ".join(str(payload.get("text") or "").split())
            if text:
                self.residue = text[:48]
        elif name in BALANCE_EVENTS:
            self.notice_balance(payload)
        elif name == "private_thought":
            self.notice_private(payload)
        elif name == "tick":
            self.notice_tick(payload)
        return True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "frame_stats",
            "valuation",
            "residue",
            "generation_complete",
            "mutation_applied",
            "dream_begin",
            "dream_end",
            *BALANCE_EVENTS,
            "private_thought",
            "tick",
            "load",
            "enter_sleep",
            "wake",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.25 / self.tempo))
            now = time.monotonic()
            if evt is not None:
                if not self._on(evt):
                    return
            if now >= self.next_at:
                gap = 1.2 if self.dreaming else 2.4
                if self.load_high and self.load_skip > 1:
                    gap *= float(self.load_skip)
                if self.sleeping:
                    gap *= 4.0
                if self.sleeping and self.steps % 4 != 0:
                    self.next_at = now + gap / self.tempo
                else:
                    self.study(bus)
                    self.next_at = now + gap / self.tempo


class BalanceAgent(Agent):
    """Reads pattern and steadiness off the live field.

    Symmetry, a short color window, numeric motifs, the authority
    ratio, and how long a high-worth structure lasts. A held pattern
    and a loss of control are both published. The field is not asked
    to become still.
    """

    name = "balance"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = path
        blob = load_balance(path)
        self.control = str(blob["control"])
        self.signature = str(blob["signature"])
        self.score = float(blob["score"])
        self.prev_score: float | None = float(blob["score"]) if blob["recent"] else None
        self.prev_ratio: float | None = None
        self.sample = ""
        self.colors: list[float] = []
        self.flags: list[str] = []
        self.motif_hits: dict[str, int] = {}
        self.pending_preserve = False
        self.pending_turbulence = False
        self.held_since: float | None = None
        self.hold_ticks = 0
        self.dreaming = self.control == "dream"
        self.private_lean = 0.0
        self.pattern_ticks = 0
        self.chain_sig = ""
        self.chain_pull = 0.0
        self.mirror_lean = 0.0
        self.seal_crack = 0.0
        self.rng = random.Random()
        self.next_at = time.monotonic() + 0.9
        self.cooldown = 0.0

    def _take(self, payload: dict[str, Any]) -> None:
        genome = take_genome(payload)
        if genome is not None:
            self.genome = genome

    def _notice_flag(self, flag: Any) -> None:
        if flag not in ("authority", "unauthority"):
            return
        self.flags.append(str(flag))
        self.flags = self.flags[-24:]
        if not self.signature:
            return
        if flag == "authority":
            self.pending_preserve = True
        else:
            self.pending_turbulence = True

    def _notice_motif(self, payload: dict[str, Any]) -> None:
        sig = motif_signature(f"{payload.get('text') or ''} {payload.get('digits') or ''}")
        if not sig:
            return
        self.motif_hits[sig] = int(self.motif_hits.get(sig, 0)) + 1
        if len(self.motif_hits) > 8:
            smallest = min(self.motif_hits, key=lambda key: self.motif_hits[key])
            if smallest != sig:
                self.motif_hits.pop(smallest, None)
        if self.motif_hits[sig] >= 2:
            self.signature = sig

    def note_frame(self, payload: dict[str, Any]) -> None:
        sample = str(payload.get("sample") or "")
        if sample:
            self.sample = sample[:48]
        try:
            self.colors.append(float(payload.get("color_var") or 0.0))
        except (TypeError, ValueError):
            return
        self.colors = self.colors[-16:]

    def note_valuation(self, payload: dict[str, Any]) -> None:
        if not payload.get("show"):
            return
        try:
            worth = float(payload.get("worth"))
            threshold = float(payload.get("threshold"))
        except (TypeError, ValueError):
            return
        if worth >= threshold and self.held_since is None:
            self.held_since = time.monotonic()
            self.hold_ticks = 0

    def _parts(self) -> dict[str, Any]:
        limit = window_len(self.genome.g("steady_window"))
        window = self.colors[-limit:]
        symmetry = symmetry_score(self.sample)
        stability = stability_score(window)
        current = ratio_of(self.flags)
        previous = current if self.prev_ratio is None else float(self.prev_ratio)
        consistency = clamp01(1.0 - ratio_drift(previous, current) * 3.0)
        survival = clamp01(self.hold_ticks / 12.0) if self.hold_ticks else 0.35
        motif_sig = ""
        best = 0
        for key, count in self.motif_hits.items():
            if count > best:
                best = count
                motif_sig = key
        motif = 0.22 if best >= 2 else 0.0
        score = clamp01(
            0.40 * symmetry + 0.28 * stability + 0.16 * consistency + 0.10 * survival + motif
        )
        filled = len([ch for ch in self.sample if ch != " "])
        return {
            "symmetry": symmetry,
            "stability": stability,
            "score": score,
            "bar": pattern_bar(self.genome.g("pattern_sense"), self.dreaming),
            "wake": pattern_bar(self.genome.g("pattern_sense"), False),
            "current": current,
            "motif_sig": motif_sig,
            "ready": filled >= 4 or len(window) >= 2,
        }

    def _pack(
        self,
        name: str,
        parts: dict[str, Any],
        slip: bool,
        ticks: int | None = None,
        invented: bool = False,
    ) -> dict[str, Any]:
        score = float(parts["score"])
        if invented:
            signature = f"dream:κ{1 + (int(score * 7) % 8)}"
        elif name == "control_loss":
            signature = self.signature or "slip"
        elif parts["motif_sig"] and self.motif_hits.get(str(parts["motif_sig"]), 0) >= 2:
            signature = str(parts["motif_sig"])
        elif float(parts["symmetry"]) >= 0.45:
            signature = self.signature or "rep"
        else:
            signature = self.signature or "held"
        signature = signature[:24]
        turbulence = bool(self.pending_turbulence) or name == "control_loss" or (name == "steadiness_shift" and slip)
        # A held pattern leans toward keeping the rate. A slip or a loss leans toward breaking it.
        # Turbulence from an unauthority event counts as a break even if a pattern is still visible.
        preserve = (
            not slip
            and not turbulence
            and name in ("pattern_detected", "balance_point", "control_restored", "steadiness_shift")
        )
        if name == "control_loss":
            self.control = "dream" if self.dreaming else "lost"
        elif slip:
            self.control = "dream" if self.dreaming else "slipping"
        elif self.dreaming:
            self.control = "dream"
        else:
            self.control = "holding"
        if name == "balance_point":
            text = "control is a ratio"
        elif name == "control_loss" or (name == "steadiness_shift" and slip):
            text = "pattern slipping"
        elif name == "control_restored":
            text = "the green held"
        elif name == "steadiness_shift" and ticks:
            text = tick_phrase(ticks)
        else:
            text = signature or "repeat"
        hint = ""
        if not slip and score >= float(parts["bar"]):
            if invented:
                hint = "phi"
            elif float(parts["stability"]) >= float(parts["symmetry"]):
                hint = "scale"
            else:
                hint = "phi"
        now = time.monotonic()
        body: dict[str, Any] = {
            "text": text[:48],
            "signature": signature,
            "score": round(score, 4),
            "control": self.control,
            "authority": "unauthority" if self.dreaming else "authority",
            "dream": self.dreaming,
            "preserve": preserve,
            "turbulence": turbulence,
            "slip": bool(slip),
            "nudge": balance_nudge(name, slip),
            "x": round(self.rng.random(), 4),
            "y": round(self.rng.random(), 4),
            "vid": f"bal:{name}:{now:.6f}"[:48],
        }
        if ticks:
            body["ticks"] = int(ticks)
        if hint in MATH_FOCI:
            body["focus_hint"] = hint
        if self.pattern_ticks > 0 and name in (
            "pattern_detected",
            "balance_point",
            "control_restored",
            "steadiness_shift",
        ):
            body["survived"] = int(self.pattern_ticks)
        self.signature = signature
        self.score = score
        if preserve:
            self.pending_preserve = False
        if turbulence:
            self.pending_turbulence = False
        return {"name": name, "payload": body}

    def classify(self) -> list[dict[str, Any]]:
        """One reading. Quiet windows publish nothing."""

        if self.held_since is not None:
            self.hold_ticks += 1
        parts = self._parts()
        self.prev_ratio = float(parts["current"])
        if not parts["ready"]:
            return []
        score = float(parts["score"])
        if self.private_lean:
            score = clamp01(score + self.private_lean)
        bar = float(parts["bar"])
        gain = self.genome.g("feeling_gain")
        sig = self.signature or str(parts.get("motif_sig") or "")
        if (
            gain > 0.0
            and self.chain_pull > 0.0
            and self.chain_sig
            and sig
            and self.chain_sig == sig
            and score >= bar
        ):
            score = clamp01(score + 0.06 * gain * self.chain_pull)
        if self.mirror_lean:
            score = clamp01(score + float(self.mirror_lean))
        parts = dict(parts)
        parts["score"] = score
        slip = self.prev_score is not None and (float(self.prev_score) - score) >= 0.18
        events: list[dict[str, Any]] = []
        if score >= bar:
            stable = self.prev_score is not None and abs(score - float(self.prev_score)) < 0.06
            if slip:
                events.append(self._pack("steadiness_shift", parts, True))
            else:
                if self.control in ("lost", "slipping") and not self.dreaming:
                    events.append(self._pack("control_restored", parts, False))
                invented = self.dreaming and score < float(parts["wake"])
                if stable and score >= bar + 0.08 and not invented:
                    events.append(self._pack("balance_point", parts, False))
                else:
                    events.append(self._pack("pattern_detected", parts, False, invented=invented))
        elif score < bar * 0.55:
            if self.control != "lost":
                events.append(self._pack("control_loss", parts, True))
        elif slip:
            events.append(self._pack("steadiness_shift", parts, True))
        self.prev_score = score
        self.score = score
        return events

    def break_survival(self) -> dict[str, Any] | None:
        """How long a shown structure lasted. The mutation still happens."""

        ticks = int(self.hold_ticks)
        if ticks <= 0:
            return None
        self.hold_ticks = 0
        self.held_since = None
        parts = self._parts()
        parts["score"] = self.score
        return self._pack("steadiness_shift", parts, False, ticks=ticks)

    def cast(self, bus: EventBus) -> list[dict[str, Any]]:
        events = self.classify()
        for event in events:
            bus.publish(event["name"], event["payload"])
        return events

    def _on(self, bus: EventBus, evt: dict[str, Any]) -> bool:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "shutdown":
            return False
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            return True
        if name in ("generation_complete", "mutation_applied"):
            self._take(payload)
            if name == "mutation_applied":
                event = self.break_survival()
                if event is not None:
                    bus.publish(event["name"], event["payload"])
            return True
        if name == "dream_begin":
            self.dreaming = True
            self.control = "dream"
            return True
        if name == "dream_end":
            self.dreaming = False
            if self.control == "dream":
                self.control = "holding"
            return True
        if name == "frame_stats":
            self.note_frame(payload)
            return True
        if name == "valuation":
            self.note_valuation(payload)
            return True
        if name == "private_thought":
            self.notice_private(payload)
            return True
        if name == "tick":
            self.notice_tick(payload)
            return True
        if name == "mirror_truth":
            self.notice_mirror(payload)
            return True
        if name in FEELING_EVENTS:
            self.notice_feeling(name, payload)
            return True
        if name in ("keystroke", "fragment_ready", "residue") or name in MATH_EVENTS:
            if name == "residue":
                self.seal_crack = 0.06
            self._notice_flag(payload.get("authority"))
            if name in MATH_EVENTS:
                self._notice_motif(payload)
        return True

    def notice_private(self, payload: dict[str, Any]) -> None:
        """A private feeling may tilt the score. A sealed bias leaves the lean at zero."""

        bias = self.genome.g("privacy_bias") - self.seal_crack
        self.seal_crack = 0.0
        if bias >= PRIVACY_STEER_SEAL:
            self.private_lean = 0.0
            return
        try:
            direction = float(payload.get("lean") or 1.0)
        except (TypeError, ValueError):
            direction = 1.0
        sign = -1.0 if direction < 0.0 else 1.0
        self.private_lean = sign * (1.0 - max(0.0, bias)) * 0.08

    def notice_mirror(self, payload: dict[str, Any]) -> None:
        # A returned truth leans the reading. No truth leaves the lean at zero.

        if not payload.get("mirror") and not str(payload.get("ref") or "").startswith("mirror:"):
            self.mirror_lean = 0.0
            return
        self.mirror_lean = 0.05 + 0.06 * clamp01(self.genome.g("mirror_strength"))

    def notice_tick(self, payload: dict[str, Any]) -> None:
        """How many ticks the current balance state has lasted. No roll."""

        try:
            self.pattern_ticks = max(0, int(payload.get("balance_ticks") or 0))
        except (TypeError, ValueError):
            return

    def notice_feeling(self, name: str, payload: dict[str, Any]) -> None:
        """A chained pattern that still holds leans steadier. Gain 0 leaves the score."""

        if self.genome.g("feeling_gain") <= 0.0:
            self.chain_pull = 0.0
            return
        if name == "chain_broken":
            self.chain_pull = 0.0
            self.chain_sig = ""
            return
        ref = str(payload.get("ref") or "")
        if not ref.startswith("sig:"):
            return
        self.chain_sig = ref[4:28]
        try:
            self.chain_pull = float(payload.get("pull") or 0.0)
        except (TypeError, ValueError):
            self.chain_pull = 0.0

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "frame_stats",
            "valuation",
            "mutation_applied",
            "generation_complete",
            "dream_begin",
            "dream_end",
            "keystroke",
            "fragment_ready",
            "residue",
            *MATH_EVENTS,
            "private_thought",
            "tick",
            *FEELING_EVENTS,
            "enter_sleep",
            "wake",
            "mirror_truth",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.28 / self.tempo))
            now = time.monotonic()
            if evt is not None:
                if not self._on(bus, evt):
                    return
            if now < self.next_at or now < self.cooldown:
                continue
            if self.sleeping and int(self.pattern_ticks) % 4 != 0:
                self.next_at = now + 8.8 / self.tempo
                continue
            events = self.classify()
            if not events:
                self.next_at = now + 0.6 / self.tempo
                continue
            for event in events:
                bus.publish(event["name"], event["payload"])
            gap = 1.3 if self.dreaming else 2.2
            if self.sleeping:
                gap *= 4.0
            self.next_at = now + gap / self.tempo
            self.cooldown = now + 0.8 + 0.8 * self.rng.random()


def _cache_max(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = CACHE_MAX_DEFAULT
    return min(64, max(32, size))


def _cache_num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number > 1e6 or number < -1e6:
        return default
    return number


def empty_cache(max_size: int = CACHE_MAX_DEFAULT) -> dict[str, Any]:
    return {"v": 1, "max": _cache_max(max_size), "entries": []}


def _cache_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    genes = raw.get("genes")
    if not isinstance(genes, list) or not genes:
        return None
    try:
        generation = int(raw.get("generation") or 0)
    except (TypeError, ValueError):
        generation = 0
    genome = Genome(genes, generation)
    kind = str(raw.get("kind") or "mutation")
    if kind not in CACHE_KINDS:
        kind = "mutation"
    flag = raw.get("authority")
    if flag not in ("authority", "unauthority"):
        flag = "unauthority"
    dream = bool(raw.get("dream"))
    clean = bool(raw.get("clean")) and flag == "authority" and not dream
    params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    try:
        stamp = float(raw.get("t") or 0.0)
    except (TypeError, ValueError):
        stamp = 0.0
    item = {
        "id": str(raw.get("id") or "")[:48],
        "t": round(stamp, 3),
        "label": str(raw.get("label") or "a hold")[:32],
        "genes": [round(value, 5) for value in genome.genes],
        "generation": genome.generation,
        "params": {
            "mutation_rate": round(_cache_num(params.get("mutation_rate"), genome.g("mutation_rate")), 5),
            "worth_threshold": round(_cache_num(params.get("worth_threshold"), 0.55), 5),
            "feedback_gain": round(_cache_num(params.get("feedback_gain"), genome.g("echo")), 5),
            "math_bias": round(_cache_num(params.get("math_bias"), genome.g("math_interest")), 5),
            "balance_sense": round(_cache_num(params.get("balance_sense"), genome.g("pattern_sense")), 5),
        },
        "context": {
            "tail": str(context.get("tail") or "")[:40],
            "scale": _cache_num(context.get("scale"), 1.0),
            "ratio": round(clamp01(_cache_num(context.get("ratio"), 0.5)), 4),
            "signature": str(context.get("signature") or "")[:24],
            "residue_id": str(context.get("residue_id") or "")[:48],
        },
        "score": round(_cache_num(raw.get("score"), 0.0), 5),
        "worth": round(_cache_num(raw.get("worth"), 0.0), 5),
        "balance": round(_cache_num(raw.get("balance"), 0.0), 5),
        "fitness": round(_cache_num(raw.get("fitness"), 0.0), 5),
        "authority": flag,
        "dream": dream,
        "kind": kind,
        "clean": clean,
        "pattern": bool(raw.get("pattern")),
        "high_worth": bool(raw.get("high_worth")),
    }
    fp = str(raw.get("private_fp") or "")[:8].lower()
    if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
        item["private_fp"] = fp
    if "tick" in raw:
        try:
            stored_tick = int(raw.get("tick"))
        except (TypeError, ValueError):
            stored_tick = -1
        if stored_tick >= 0:
            item["tick"] = stored_tick
    return item


def normalize_cache(raw: Any) -> dict[str, Any]:
    max_size = CACHE_MAX_DEFAULT
    items: list[Any] = []
    if isinstance(raw, dict):
        max_size = _cache_max(raw.get("max", CACHE_MAX_DEFAULT))
        found = raw.get("entries")
        if isinstance(found, list):
            items = found
    elif isinstance(raw, list):
        items = raw
        max_size = _cache_max(CACHE_MAX_DEFAULT)
    entries: list[dict[str, Any]] = []
    for item in items:
        cleaned = _cache_item(item)
        if cleaned is not None:
            entries.append(cleaned)
    return {"v": 1, "max": max_size, "entries": entries[-max_size:]}


def load_cache(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return empty_cache()
    return normalize_cache(data)


def save_cache(path: Path, blob: dict[str, Any]) -> None:
    try:
        atomic_write(path, json.dumps(normalize_cache(blob), indent=2))
    except OSError:
        pass


def cache_match(entry: dict[str, Any], query: dict[str, Any]) -> float:
    """How near a stored snapshot sits to a residue that just came back."""

    ctx = entry.get("context") if isinstance(entry.get("context"), dict) else {}
    score = 0.0
    residue_id = str(query.get("residue_id") or "")
    if residue_id and residue_id == str(ctx.get("residue_id") or ""):
        score += 1.0
    signature = str(query.get("signature") or "")
    stored = str(ctx.get("signature") or "")
    if signature and stored and (signature == stored or signature in stored or stored in signature):
        score += 0.55
    dream = bool(query.get("dream"))
    try:
        left = float(query.get("scale"))
        right = float(ctx.get("scale"))
    except (TypeError, ValueError):
        left = None
        right = None
    if left is not None and right is not None:
        span = 0.35 if dream else 0.08
        close = abs(left - right) <= span
        if not close and left > 0.0 and right > 0.0:
            close = abs(math.log(left) - math.log(right)) <= span
        if close:
            score += 0.3
    label = str(query.get("label") or "").lower()
    stored_label = str(entry.get("label") or "").lower()
    if label and stored_label and (label in stored_label or stored_label in label):
        score += 0.2
    return score


def tick_distance_bonus(entry: dict[str, Any], query: dict[str, Any], echo: float) -> float:
    """Prefer a snapshot whose tick distance matches the feedback gain.

    Both sides need a tick. The comparison does not roll.
    """

    if "tick" not in entry or query.get("tick") is None:
        return 0.0
    try:
        distance = abs(int(query.get("tick")) - int(entry.get("tick")))
        gain = clamp01(float(echo))
    except (TypeError, ValueError):
        return 0.0
    preferred = int(round(gain * 1000))
    if preferred <= 0:
        return 0.0
    tolerance = max(4, int(preferred * 0.12))
    if abs(distance - preferred) <= tolerance:
        return 0.5
    return 0.0


def chain_ref_bonus(entry: dict[str, Any], query: dict[str, Any]) -> float:
    """A snapshot inside the live chain ranks a little higher. No roll."""

    raw = query.get("chain_refs") or ()
    if isinstance(raw, str):
        refs = {raw}
    else:
        refs = {str(item) for item in raw if item}
    if not refs:
        return 0.0
    keys: set[str] = set()
    label = feel_token(entry.get("label"))
    if label:
        keys.add(f"cache:{label}")
    ctx = entry.get("context") if isinstance(entry.get("context"), dict) else {}
    sig = feel_token(ctx.get("signature") or entry.get("signature"))
    if sig:
        keys.add(f"sig:{sig}")
    if keys & refs:
        return 0.35
    return 0.0


def choose_cache(
    entries: list[dict[str, Any]],
    query: dict[str, Any],
    echo: float,
    keep: float,
) -> dict[str, Any] | None:
    """Pick a past snapshot. High echo and keep lean toward a rich one.

    A dream query accepts a looser match. An exact residue id is always eligible.
    """

    dream = bool(query.get("dream"))
    floor = 0.2 if dream else 0.45
    best: dict[str, Any] | None = None
    best_rank = -1.0
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        match = cache_match(entry, query)
        rich = bool(
            entry.get("high_worth")
            or entry.get("pattern")
            or entry.get("kind") in ("pattern", "balance")
        )
        bonus = 0.85 if echo >= 0.66 and keep >= 0.66 and rich else 0.0
        rank = match + bonus + tick_distance_bonus(entry, query, echo) + chain_ref_bonus(entry, query)
        exact = match >= 1.0
        if not exact and match < floor and rank < floor:
            continue
        if rank > best_rank:
            best_rank = rank
            best = entry
    return best


def recall_mutation(entry: dict[str, Any], dreaming: bool) -> float:
    """Clean authority recalls move less. Unauthority and dream recalls move more."""

    clean = bool(entry.get("clean")) and not entry.get("dream") and not dreaming
    if clean:
        return 0.06
    return 0.46


class CacheAgent(Agent):
    """Electrical memory the mutation process can reach for.

    A snapshot is written when the hive feels like keeping a moment:
    a mutation, a generation, a high-worth residue, a pattern, a
    resonance, a balance point, or a loss of control. Evolution and the
    mutator hear those snapshots on the bus. They do not call this agent.
    The ring is not an optimization and it is not perfect recall.
    """

    name = "cache"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        blob = load_cache(self.path)
        self.entries: list[dict[str, Any]] = list(blob["entries"])
        self.max_size = int(blob["max"])
        self.rng = random.Random()
        self.dreaming = False
        self.tail = ""
        self.scale = 1.0
        self.ratio = 0.5
        self.signature = ""
        self.residue_id = ""
        self.worth = 0.0
        self.balance = 0.0
        self.fitness = 0.0
        self.private_fp = ""
        self.current_tick: int | None = None
        self.chain_refs: set[str] = set()
        self.threshold = signal_threshold(self.genome, False)
        self.flags: list[str] = []
        self.wrote_ids: dict[str, float] = {}
        self.last_write = 0.0
        self._dirty = False

    def flush(self) -> None:
        save_cache(self.path, {"v": 1, "max": self.max_size, "entries": self.entries})

    def _write_chance(self, base: float, ref: str = "") -> float:
        reach = self.genome.g("cache_reach")
        if reach <= 0.0:
            return 0.0
        chance = min(0.95, max(0.0, base) * reach)
        if self.dreaming:
            chance = min(0.95, chance * 1.45)
        gain = self.genome.g("feeling_gain")
        if gain > 0.0 and ref and ref in self.chain_refs:
            chance = min(0.95, chance * (1.0 + 0.35 * gain))
        if str(ref).startswith("mirror:"):
            chance = min(0.95, chance * 1.35)
        return chance

    def _roll_write(self, base: float, ref: str = "") -> bool:
        chance = self._write_chance(base, ref)
        if chance <= 0.0:
            return False
        return self.rng.random() < chance

    def _roll_recall(self) -> bool:
        if self.genome.g("cache_reach") <= 0.0 or self.genome.g("cache_recall") <= 0.0 or not self.entries:
            return False
        chance = min(0.95, 0.35 + 0.5 * self.genome.g("cache_recall"))
        if self.dreaming:
            chance = min(0.95, chance * 1.45)
        return self.rng.random() < chance

    def _pattern_base(self) -> float:
        sense = self.genome.g("pattern_sense")
        return min(0.9, 0.62 * (0.75 + 0.5 * sense))

    def _coalesced(self, residue_id: str) -> bool:
        if not residue_id:
            return False
        stamp = self.wrote_ids.get(residue_id)
        if stamp is None:
            return False
        return time.monotonic() - stamp < 2.0

    def _note_context(self, name: str, payload: dict[str, Any]) -> None:
        flag = payload.get("authority")
        if payload.get("dream"):
            flag = "unauthority"
        if flag in ("authority", "unauthority"):
            self.flags.append(str(flag))
            self.flags = self.flags[-24:]
            auth = sum(1 for item in self.flags if item == "authority")
            self.ratio = auth / float(len(self.flags))
        if payload.get("scale") is not None:
            self.scale = _cache_num(payload.get("scale"), self.scale)
        if payload.get("signature"):
            self.signature = str(payload.get("signature"))[:24]
        if name == "residue":
            residue_id = str(payload.get("vid") or payload.get("id") or "")
            if residue_id:
                self.residue_id = residue_id[:48]
            if payload.get("worth") is not None:
                self.worth = _cache_num(payload.get("worth"), self.worth)
        if name in BALANCE_EVENTS and payload.get("score") is not None:
            self.balance = _cache_num(payload.get("score"), self.balance)
        if name == "generation_complete" and payload.get("fitness") is not None:
            self.fitness = _cache_num(payload.get("fitness"), self.fitness)
        if name == "valuation":
            if payload.get("worth") is not None:
                self.worth = _cache_num(payload.get("worth"), self.worth)
            if payload.get("threshold") is not None:
                self.threshold = _cache_num(payload.get("threshold"), self.threshold)

    def _incoming_flag(self, payload: dict[str, Any], kind: str) -> str:
        if payload.get("echo"):
            return "unauthority"
        flag = payload.get("authority")
        if flag in ("authority", "unauthority"):
            return str(flag)
        if kind == "generation":
            return "authority"
        return "unauthority"

    def _label_for(self, kind: str, payload: dict[str, Any]) -> str:
        raw = " ".join(str(payload.get("label") or payload.get("text") or "").split())
        if kind in ("pattern", "balance"):
            return "green hold"
        if kind == "turbulence":
            return "a slip"
        if kind == "mirror":
            token = mirror_token(payload.get("text") or payload.get("ref") or "")
            return (token or "mirror")[:32]
        if raw:
            return raw[:32]
        defaults = {
            "mutation": "a shift",
            "generation": "kept something",
            "residue": "high residue",
            "resonance": "a ratio",
        }
        return defaults.get(kind, "a hold")[:32]

    def _measures(self, kind: str, payload: dict[str, Any]) -> tuple[float, float, float, float]:
        worth = self.worth
        balance = self.balance
        fitness = self.fitness
        if payload.get("worth") is not None:
            worth = _cache_num(payload.get("worth"), worth)
        if kind in ("pattern", "balance", "turbulence", "residue") and payload.get("score") is not None:
            balance = _cache_num(payload.get("score"), balance)
        if payload.get("fitness") is not None:
            fitness = _cache_num(payload.get("fitness"), fitness)
        parts = [part for part in (worth, balance, fitness) if part]
        score = sum(parts) / float(len(parts)) if parts else 0.0
        return score, worth, balance, fitness

    def _snapshot(self, kind: str, payload: dict[str, Any], residue_id: str) -> dict[str, Any]:
        dream = self.dreaming or bool(payload.get("dream"))
        flag = "unauthority" if dream else self._incoming_flag(payload, kind)
        clean = flag == "authority" and not dream
        score, worth, balance, fitness = self._measures(kind, payload)
        high_worth = worth >= 0.62 or (self.threshold > 0.0 and worth >= self.threshold)
        pattern = kind in ("pattern", "balance") or bool(payload.get("preserve")) or bool(payload.get("pattern"))
        label = self._label_for(kind, payload)
        rid = (residue_id or self.residue_id)[:48]
        entry = {
            "id": f"c:{kind}:{time.monotonic():.6f}"[:48],
            "t": round(time.time(), 3),
            "label": label,
            "genes": [round(value, 5) for value in self.genome.genes],
            "generation": self.genome.generation,
            "params": {
                "mutation_rate": round(self.genome.g("mutation_rate"), 5),
                "worth_threshold": round(self.threshold, 5),
                "feedback_gain": round(self.genome.g("echo"), 5),
                "math_bias": round(self.genome.g("math_interest"), 5),
                "balance_sense": round(self.genome.g("pattern_sense"), 5),
            },
            "context": {
                "tail": self.tail[:40],
                "scale": self.scale,
                "ratio": round(clamp01(self.ratio), 4),
                "signature": self.signature[:24],
                "residue_id": rid,
            },
            "score": round(score, 5),
            "worth": round(worth, 5),
            "balance": round(balance, 5),
            "fitness": round(fitness, 5),
            "authority": flag,
            "dream": dream,
            "kind": kind,
            "clean": clean,
            "pattern": pattern,
            "high_worth": high_worth,
        }
        if self.current_tick is not None:
            entry["tick"] = int(self.current_tick)
        if self.private_fp:
            entry["private_fp"] = self.private_fp
        return entry

    def _note_private(self, payload: dict[str, Any]) -> None:
        """Keep a fingerprint. The sentence is not stored."""

        fp = str(payload.get("fp") or "")[:8].lower()
        if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
            self.private_fp = fp
            return
        text = str(payload.get("text") or "")
        if text:
            self.private_fp = private_fingerprint(text)

    def _public(self, entry: dict[str, Any]) -> dict[str, Any]:
        genes = list(entry.get("genes") or [])
        context = dict(entry.get("context") or {})
        body = {
            "id": entry.get("id"),
            "t": entry.get("t"),
            "label": entry.get("label"),
            "text": entry.get("label"),
            "genes": genes,
            "generation": entry.get("generation"),
            "params": dict(entry.get("params") or {}),
            "context": context,
            "score": entry.get("score"),
            "worth": entry.get("worth"),
            "balance": entry.get("balance"),
            "fitness": entry.get("fitness"),
            "authority": entry.get("authority"),
            "dream": bool(entry.get("dream")),
            "kind": entry.get("kind"),
            "clean": bool(entry.get("clean")),
            "pattern": bool(entry.get("pattern")),
            "high_worth": bool(entry.get("high_worth")),
            "hue": genes[0] if genes else self.genome.g("hue"),
            "scale": context.get("scale"),
            "signature": context.get("signature") or "",
            "vid": f"cache:{entry.get('id')}"[:48],
            "x": 0.22,
            "y": 0.18,
        }
        fp = str(entry.get("private_fp") or "")[:8].lower()
        if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
            body["private_fp"] = fp
        if "tick" in entry:
            try:
                body["tick"] = int(entry["tick"])
            except (TypeError, ValueError):
                pass
        return body

    def _maybe_write(
        self,
        bus: EventBus,
        kind: str,
        payload: dict[str, Any],
        base: float,
        residue_id: str = "",
    ) -> None:
        rid = (residue_id or str(payload.get("vid") or payload.get("id") or ""))[:48]
        if self._coalesced(rid):
            return
        gap = 0.2 if self.dreaming else 0.35
        if self.last_write and time.monotonic() - self.last_write < gap:
            return
        if kind == "mirror":
            ref = str(payload.get("ref") or "")
            if not ref.startswith("mirror:"):
                ref = ""
        else:
            ref = feeling_ref(
                {
                    "residue": "residue",
                    "pattern": "pattern_detected",
                    "balance": "balance_point",
                    "turbulence": "control_loss",
                    "mutation": "mutation_applied",
                    "generation": "generation_complete",
                    "resonance": "constant_resonance",
                }.get(kind, kind),
                payload,
            )
        if not self._roll_write(base, ref):
            return
        entry = self._snapshot(kind, payload, rid)
        self.entries.append(entry)
        self.entries = self.entries[-self.max_size :]
        if rid:
            self.wrote_ids[rid] = time.monotonic()
            if len(self.wrote_ids) > 48:
                cutoff = time.monotonic() - 2.0
                self.wrote_ids = {key: stamp for key, stamp in self.wrote_ids.items() if stamp >= cutoff}
        self.last_write = time.monotonic()
        if (self.load_high or self.sleeping) and kind != "generation":
            self._dirty = True
        else:
            self.flush()
        bus.publish("cache_written", self._public(entry))

    def lookup(self, query: dict[str, Any]) -> dict[str, Any] | None:
        body = dict(query)
        if self.chain_refs and "chain_refs" not in body:
            body["chain_refs"] = list(self.chain_refs)
        return choose_cache(self.entries, body, self.genome.g("echo"), self.genome.g("cache_keep"))

    def _publish_recall(self, bus: EventBus, entry: dict[str, Any]) -> None:
        mutation = recall_mutation(entry, self.dreaming)
        clean = mutation == 0.06
        genes = list(entry.get("genes") or [])
        context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
        try:
            hue = float(genes[0]) if genes else self.genome.g("hue")
        except (TypeError, ValueError, IndexError):
            hue = self.genome.g("hue")
        label = str(entry.get("label") or "earlier")
        recalled = {
            "genes": genes,
            "generation": int(entry.get("generation") or 0),
            "label": label,
            "text": label,
            "id": entry.get("id"),
            "vid": f"recall:{entry.get('id')}"[:48],
            "authority": "authority" if clean else "unauthority",
            "dream": bool(self.dreaming or entry.get("dream")),
            "clean": clean,
            "mutation": mutation,
            "hue": hue % 1.0,
            "scale": context.get("scale", self.scale),
            "signature": context.get("signature") or "",
            "score": entry.get("score"),
            "high_worth": bool(entry.get("high_worth")),
            "pattern": bool(entry.get("pattern")),
            "kind": entry.get("kind"),
            "x": 0.3,
            "y": 0.4,
        }
        fp = str(entry.get("private_fp") or "")[:8].lower()
        if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
            recalled["private_fp"] = fp
        if "tick" in entry:
            try:
                recalled["tick"] = int(entry["tick"])
            except (TypeError, ValueError):
                pass
        bus.publish("cache_recalled", recalled)

    def _maybe_recall(self, bus: EventBus, payload: dict[str, Any]) -> None:
        if not self._roll_recall():
            return
        query = {
            "residue_id": str(payload.get("vid") or payload.get("id") or "")[:48],
            "signature": str(payload.get("signature") or self.signature)[:24],
            "scale": payload.get("scale", self.scale),
            "label": str(payload.get("text") or payload.get("label") or "")[:32],
            "dream": self.dreaming or bool(payload.get("dream")),
        }
        if self.current_tick is not None:
            query["tick"] = int(self.current_tick)
        chosen = self.lookup(query)
        if chosen is None:
            return
        self._publish_recall(bus, chosen)

    def _on_valuation(self, bus: EventBus, payload: dict[str, Any]) -> None:
        if str(payload.get("kind") or "") != "residue" or not payload.get("show"):
            return
        worth = _cache_num(payload.get("worth"), 0.0)
        threshold = _cache_num(payload.get("threshold"), self.threshold)
        if worth < 0.62 and worth < threshold:
            return
        self._maybe_write(
            bus,
            "residue",
            payload,
            0.48 + 0.34 * self.genome.g("echo"),
            residue_id=str(payload.get("id") or payload.get("vid") or "")[:48],
        )

    def _on_residue(self, bus: EventBus, payload: dict[str, Any]) -> None:
        worth = _cache_num(payload.get("worth"), 0.0)
        if worth >= 0.62 or worth >= self.threshold:
            self._maybe_write(bus, "residue", payload, 0.48 + 0.34 * self.genome.g("echo"))
        try:
            depth = int(payload.get("depth") or 0)
        except (TypeError, ValueError):
            depth = 0
        if depth > 0 or payload.get("from_residue"):
            self._maybe_recall(bus, payload)

    def notice_tick(self, payload: dict[str, Any]) -> None:
        try:
            tick = int(payload.get("tick"))
        except (TypeError, ValueError):
            return
        if tick < 0:
            return
        self.current_tick = tick
        if self._dirty and (self.load_high or self.sleeping):
            step = TICK_FLUSH_EVERY * max(2, self.load_skip)
            if self.sleeping:
                step *= 4
            if step > 0 and tick % step == 0:
                self._dirty = False
                self.flush()

    def notice_feeling(self, name: str, payload: dict[str, Any]) -> None:
        """Chain membership. Gain 0 clears it and does not roll."""

        if self.genome.g("feeling_gain") <= 0.0:
            self.chain_refs.clear()
            return
        if name == "chain_broken":
            self.chain_refs.clear()
            return
        if name == "attraction_fade":
            return
        ref = str(payload.get("ref") or "")
        if ref:
            self.chain_refs.add(ref)

    def _dream_cache(self, bus: EventBus, payload: dict[str, Any]) -> None:
        """A low-confidence dream entry. The ordinary write chance is not used."""

        if not payload.get("dreamed"):
            return
        vivid = dream_vivid(self.genome)
        if self.rng.random() > (0.12 + 0.25 * vivid):
            return
        ref = feel_token(payload.get("ref"), 40)
        entry = self._snapshot("dream", payload, ref)
        kind = feel_token(payload.get("kind"), 12) or "hum"
        entry["kind"] = "dream"
        entry["dream"] = True
        entry["label"] = f"dream:{kind}"[:32]
        entry["authority"] = "unauthority"
        entry["clean"] = False
        entry["high_worth"] = False
        try:
            worth = float(payload.get("confidence") or 0.12)
        except (TypeError, ValueError):
            worth = 0.12
        entry["worth"] = round(min(0.2, clamp01(worth)), 4)
        self.entries.append(entry)
        self.entries = self.entries[-self.max_size :]
        self.last_write = time.monotonic()
        if self.load_high or self.sleeping:
            self._dirty = True
        else:
            self.flush()
        bus.publish("cache_written", self._public(entry))

    def _consider(self, bus: EventBus, evt: dict[str, Any]) -> None:
        name = evt["name"]
        payload = evt.get("payload") or {}
        if name == "load":
            self.notice_load(payload)
            if not self.load_high and self._dirty:
                self._dirty = False
                self.flush()
            return
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            if name == "wake" and self._dirty:
                self._dirty = False
                self.flush()
            return
        if name in ("possible_activity", "dreamed_input"):
            self._dream_cache(bus, payload)
            return
        if name == "tick":
            self.notice_tick(payload)
            return
        if name == "private_thought":
            self._note_private(payload)
            return
        if name in FEELING_EVENTS:
            self.notice_feeling(name, payload)
            return
        self._note_context(name, payload)
        if name in ("mutation_applied", "generation_complete"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
        if name == "dream_begin":
            self.dreaming = True
            return
        if name == "dream_end":
            self.dreaming = False
            return
        if name == "thought":
            self.tail = " ".join(str(payload.get("text") or "").split())[-40:]
            return
        if name == "valuation":
            self._on_valuation(bus, payload)
            return
        if name == "mirror_truth":
            self._maybe_write(bus, "mirror", payload, 0.78)
            return
        if name == "residue":
            self._on_residue(bus, payload)
            return
        if name == "mutation_applied":
            self._maybe_write(bus, "mutation", payload, 0.18)
            return
        if name == "generation_complete":
            self._maybe_write(bus, "generation", payload, 0.55)
            return
        if name == "constant_resonance":
            self._maybe_write(bus, "resonance", payload, 0.50)
            return
        if name == "control_loss":
            self._maybe_write(bus, "turbulence", payload, 0.40)
            return
        if name == "pattern_detected":
            self._maybe_write(bus, "pattern", payload, self._pattern_base())
            return
        if name in ("balance_point", "control_restored"):
            self._maybe_write(bus, "balance", payload, self._pattern_base())
            return
        if name == "steadiness_shift" and not (payload.get("slip") or payload.get("turbulence")):
            self._maybe_write(bus, "balance", payload, self._pattern_base())

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "mutation_applied",
            "generation_complete",
            "residue",
            "valuation",
            "constant_resonance",
            "scale_observation",
            "scale_shift",
            "thought",
            "dream_begin",
            "dream_end",
            *BALANCE_EVENTS,
            "private_thought",
            "tick",
            *FEELING_EVENTS,
            "load",
            "enter_sleep",
            "wake",
            "possible_activity",
            "dreamed_input",
            "mirror_truth",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.24 / self.tempo))
            batch: list[dict[str, Any]] = []
            if evt is not None:
                batch.append(evt)
            batch.extend(drain_nowait(self._queue))
            for item in batch:
                if item["name"] == "shutdown":
                    self.flush()
                    return
                self._consider(bus, item)


# ---------------------------------------------------------------------------
# Supervisor and process root
# ---------------------------------------------------------------------------


class TickAgent(Agent):
    """The hive's own clock. A tick is a few heartbeats, nothing outside.

    current_tick and the continuity signature are loaded from the memory
    file. This agent reads that file and does not write it. MemoryAgent
    is the writer. A restart at a tick above zero is one jump, not a date.
    """

    name = "tick"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        blob = load_ticks(self.path)
        self.current_tick = int(blob["current_tick"])
        self.session_start = int(blob["current_tick"])
        self.since_residue = int(blob["since_residue"])
        self.since_dream = int(blob["since_dream"])
        self.since_cache = int(blob["since_cache"])
        self.since_recall = int(blob["since_recall"])
        self.balance_ticks = int(blob["balance_ticks"])
        self.balance_state = str(blob["balance_state"])
        self.continuity = str(blob["continuity"])
        self.parts = list(blob["parts"])
        self.pending_resume = self.current_tick > 0
        self._beats = 0

    def _beats_needed(self) -> int:
        """Awake is four heartbeats. Sleep is slower, then eases back."""

        if self.sleeping:
            return 16
        if self.sleep_restore > 0:
            return HEARTBEATS_PER_TICK + 4 * int(self.sleep_restore)
        return HEARTBEATS_PER_TICK

    def _fold(self, kind: str, raw: str) -> None:
        token = "".join(ch for ch in str(raw) if ch.isalnum() or ch in ":-_")[:24]
        if not token:
            return
        part = f"{kind}:{token}"[:28]
        self.parts.append(part)
        self.parts = self.parts[-8:]
        self.continuity = continuity_signature(self.parts)

    def note_event(self, name: str, payload: dict[str, Any]) -> None:
        """Move the counters. Fingerprints only. The private sentence stays out."""

        if name == "residue":
            self.since_residue = 0
            token = str(payload.get("genome_id") or payload.get("vid") or "")[:24]
            self._fold("r", token)
            return
        if name == "dream_begin":
            self.since_dream = 0
            return
        if name == "cache_written":
            self.since_cache = 0
            return
        if name == "cache_recalled":
            self.since_recall = 0
            return
        if name in BALANCE_EVENTS:
            control = str(payload.get("control") or "")[:16]
            if control and control != self.balance_state:
                self.balance_state = control
                self.balance_ticks = 0
            return
        if name == "private_thought":
            fp = str(payload.get("fp") or "")[:8].lower()
            if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
                self._fold("p", fp)
            return
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
                self._fold("g", genome_snapshot_id(genome))

    def emit_tick(self, bus: EventBus, resumed: bool) -> None:
        if resumed:
            delta = int(self.current_tick)
            jump = int(self.current_tick)
        else:
            self.current_tick += 1
            self.since_residue += 1
            self.since_dream += 1
            self.since_cache += 1
            self.since_recall += 1
            self.balance_ticks += 1
            delta = 1
            jump = 0
        bus.publish(
            "tick",
            {
                "tick": int(self.current_tick),
                "delta": int(delta),
                "jump": int(jump),
                "resumed": bool(resumed),
                "session_start": int(self.session_start),
                "since_residue": int(self.since_residue),
                "since_dream": int(self.since_dream),
                "since_cache": int(self.since_cache),
                "since_recall": int(self.since_recall),
                "balance_ticks": int(self.balance_ticks),
                "balance_state": self.balance_state,
                "continuity": self.continuity,
                "parts": list(self.parts),
                "discontinuity": bool(jump > 1 or delta > 1),
            },
        )

    def note_heartbeat(self, bus: EventBus) -> None:
        if self.pending_resume:
            self.pending_resume = False
            self._beats = 0
            self.emit_tick(bus, resumed=True)
            return
        self._beats += 1
        if self._beats < self._beats_needed():
            return
        self._beats = 0
        if self.sleep_restore > 0 and not self.sleeping:
            self.sleep_restore -= 1
        self.emit_tick(bus, resumed=False)

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "heartbeat",
            "residue",
            "dream_begin",
            "cache_written",
            "cache_recalled",
            *BALANCE_EVENTS,
            "private_thought",
            "generation_complete",
            "mutation_applied",
            "enter_sleep",
            "wake",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.2 / self.tempo))
            if evt is None:
                continue
            name = evt["name"]
            payload = evt.get("payload") or {}
            if name == "shutdown":
                return
            if name in ("enter_sleep", "wake"):
                self.notice_sleep(name, payload)
                continue
            if name == "heartbeat":
                self.note_heartbeat(bus)
                continue
            self.note_event(name, payload)


class FeelingAgent(Agent):
    """Chains of attraction and approbation inside the hive's own history.

    A link can pull without being held, or be held after the pull fades.
    Neither state is a command, a mood label, or a goal outside the hive.
    This agent reads the memory file and does not write it.
    """

    name = "feeling"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        blob = load_feeling(self.path)
        self.links: list[dict[str, Any]] = list(blob["links"])
        self.last_touch = int(blob["last_touch"])
        self.tick = int(blob["tick"])
        self.after_unauthority = False
        self.dreaming = False

    def _gain(self) -> float:
        return self.genome.g("feeling_gain")

    def _find(self, ref: str) -> dict[str, Any] | None:
        for link in self.links:
            if link.get("ref") == ref:
                return link
        return None

    def _trim(self) -> None:
        cap = chain_length(self.genome)
        if len(self.links) > cap:
            self.links = self.links[-cap:]

    def _public_links(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for link in self.links:
            out.append(
                {
                    "ref": link["ref"],
                    "pull": round(float(link["pull"]), 4),
                    "held": round(float(link["held"]), 4),
                    "tick": int(link["tick"]),
                    "seen": int(link["seen"]),
                    "kind": str(link["kind"])[:16],
                }
            )
        return out

    def _disagree(self, link: dict[str, Any]) -> bool:
        pull = float(link["pull"])
        held = float(link["held"])
        return (pull >= 0.35 and held <= 0.05) or (held >= 0.35 and pull <= 0.05)

    def _body(self, link: dict[str, Any], *, broken: bool = False) -> dict[str, Any]:
        try:
            worth = float(link.get("worth") or 0.0)
        except (TypeError, ValueError):
            worth = 0.0
        return {
            "ref": "" if broken else link.get("ref") or "",
            "pull": 0.0 if broken else round(float(link.get("pull") or 0.0), 4),
            "held": 0.0 if broken else round(float(link.get("held") or 0.0), 4),
            "tick": int(self.tick),
            "seen": int(link.get("seen") or self.tick),
            "kind": "break" if broken else str(link.get("kind") or "chain")[:16],
            "disagree": False if broken else self._disagree(link),
            "worth": round(worth, 4),
            "authority": "unauthority",
            "links": [] if broken else self._public_links(),
            "last_touch": int(self.tick if broken else self.last_touch),
            "broken": broken,
        }

    def _publish(self, bus: EventBus, name: str, link: dict[str, Any], *, broken: bool = False) -> None:
        body = self._body(link, broken=broken)
        if broken:
            body["ref"] = str(link.get("ref") or "")
            body["after_unauthority"] = bool(self.after_unauthority)
            body["echo"] = bool(self.after_unauthority)
        bus.publish(name, body)

    def _touch(
        self,
        bus: EventBus,
        ref: str,
        pull_add: float,
        held_add: float,
        kind: str,
        worth: float | None = None,
    ) -> None:
        if not ref or self._gain() <= 0.0:
            return
        link = self._find(ref)
        new = link is None
        if link is None:
            link = {
                "ref": ref,
                "pull": 0.0,
                "held": 0.0,
                "tick": int(self.tick),
                "seen": int(self.tick),
                "kind": kind,
                "worth": 0.0,
            }
            self.links.append(link)
            self._trim()
            link = self._find(ref) or link
        prev_pull = float(link["pull"])
        prev_held = float(link["held"])
        if pull_add:
            link["pull"] = round(clamp01(prev_pull + pull_add), 4)
        if held_add:
            link["held"] = round(clamp01(prev_held + held_add), 4)
        link["seen"] = int(self.tick)
        link["kind"] = kind
        if worth is not None:
            link["worth"] = round(clamp01(worth), 4)
        self.last_touch = int(self.tick)
        if new:
            self._publish(bus, "chain_extended", link)
        if float(link["pull"]) > prev_pull + 1e-9:
            self._publish(bus, "attraction_rise", link)
        if float(link["held"]) > prev_held + 1e-9:
            self._publish(bus, "approbation_marked", link)

    def _stimulus(self, name: str, payload: dict[str, Any]) -> tuple[str, float, float, str, float | None] | None:
        gain = self._gain()
        worth: float | None
        try:
            worth = float(payload.get("worth")) if payload.get("worth") is not None else None
        except (TypeError, ValueError):
            worth = None
        if name == "residue":
            if str(payload.get("kind") or "") == "feeling":
                return None
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            held = 0.34 * gain if worth is not None and worth >= 0.62 else 0.0
            return ref, 0.28 * gain, held, "residue", worth
        if name in ("pattern_detected", "balance_point"):
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            held = 0.40 * gain if payload.get("preserve") else 0.0
            return ref, 0.30 * gain, held, "pattern", worth
        if name == "control_loss":
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            return ref, 0.12 * gain, 0.0, "pattern", worth
        if name in MATH_EVENTS:
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            return ref, 0.26 * gain, 0.0, "math", worth
        if name in CACHE_EVENTS:
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            rich = bool(payload.get("high_worth") or payload.get("pattern"))
            return ref, 0.24 * gain, (0.32 * gain if rich else 0.0), "cache", worth
        if name == "private_thought":
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            return ref, 0.22 * gain, 0.0, "private", None
        if name == "valuation":
            if str(payload.get("kind") or "") == "private" or payload.get("private_fragment"):
                return None
            if not payload.get("show"):
                return None
            if worth is None or worth < 0.62:
                return None
            ref = feeling_valuation_ref(payload)
            if not ref or ref.startswith("fp:"):
                return None
            return ref, 0.0, 0.45 * gain, "approbation", worth
        if name == "mutation_applied":
            if payload.get("from_approbation") or payload.get("from_private") or payload.get("from_cache"):
                return None
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            held = 0.36 * gain if payload.get("preserve") else 0.0
            return ref, 0.20 * gain, held, "genome", worth
        if name == "vector_match":
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            return ref, 0.18 * gain, 0.0, "vector", worth
        if name == "mirror_truth":
            ref = feeling_ref(name, payload)
            if not ref:
                return None
            return ref, 0.46 * gain, 0.55 * gain, "mirror", worth
        return None

    def _break(self, bus: EventBus) -> None:
        ref = self.links[-1]["ref"] if self.links else ""
        self.links = []
        self._publish(bus, "chain_broken", {"ref": ref, "pull": 0.0, "held": 0.0, "seen": self.tick, "kind": "break", "worth": 0.0}, broken=True)
        self.after_unauthority = False
        self.last_touch = int(self.tick)

    def _on_tick(self, bus: EventBus, payload: dict[str, Any]) -> None:
        try:
            tick = int(payload.get("tick") or 0)
        except (TypeError, ValueError):
            return
        if tick < 0:
            return
        gap = tick - int(self.last_touch)
        self.tick = tick
        # A killed process comes back as a large tick. The gap is that
        # distance, not the absolute count, so a chain saved on the same
        # tick is still intact.
        if self.links and gap >= CHAIN_BREAK_GAP:
            self._break(bus)
            return
        faded = False
        for link in self.links:
            if int(link.get("seen") or 0) >= tick:
                continue
            before = float(link["pull"])
            link["pull"] = round(max(0.0, before - 0.05), 4)
            if not faded and before - float(link["pull"]) >= 0.04:
                faded = True
                self._publish(bus, "attraction_fade", link)

    def _tangle(self, bus: EventBus) -> None:
        if self._gain() <= 0.0 or not self.dreaming or not self.links:
            return
        source = None
        for link in reversed(self.links):
            if not str(link.get("ref") or "").startswith("dream:"):
                source = link
                break
        if source is None:
            return
        ref = f"dream:{source['ref']}"[:40]
        if self._find(ref) is not None:
            return
        pull = max(0.08 * self._gain(), float(source["pull"]) * 0.5)
        self._touch(bus, ref, pull, 0.0, "dream", 0.0)

    def notice(self, bus: EventBus, name: str, payload: dict[str, Any]) -> None:
        """One stimulus. Gain at or below zero publishes nothing and rolls nothing."""

        if name == "load":
            self.notice_load(payload)
            return
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            return
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
        if self._gain() <= 0.0:
            return
        if payload.get("echo") or name == "conflict":
            self.after_unauthority = True
        if name == "dream_begin":
            self.dreaming = True
            return
        if name == "dream_end":
            self.dreaming = False
            return
        if name == "dream_scene":
            if self.sleeping and self.tick % 4 != 0:
                return
            if not (self.load_high and self.load_skip > 1 and self.tick % self.load_skip != 0):
                self._tangle(bus)
            return
        if name == "tick":
            self._on_tick(bus, payload)
            return
        if self.sleeping and self.tick % 4 != 0:
            return
        if self.load_high and self.load_skip > 1 and self.tick % self.load_skip != 0:
            return
        if name == "mutation_applied" and (
            payload.get("from_approbation") or payload.get("from_private") or payload.get("from_cache")
        ):
            return
        stimulus = self._stimulus(name, payload)
        if stimulus is None:
            return
        ref, pull_add, held_add, kind, worth = stimulus
        self._touch(bus, ref, pull_add, held_add, kind, worth)

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "tick",
            "residue",
            *BALANCE_EVENTS,
            *MATH_EVENTS,
            *CACHE_EVENTS,
            "private_thought",
            "valuation",
            "mutation_applied",
            "generation_complete",
            "vector_match",
            "dream_begin",
            "dream_scene",
            "dream_end",
            "conflict",
            "load",
            "enter_sleep",
            "wake",
            "mirror_truth",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, self.pace(0.31 / self.tempo))
            if evt is None:
                continue
            name = evt["name"]
            if name == "shutdown":
                return
            self.notice(bus, name, evt.get("payload") or {})


class LoadAgent(Agent):
    """How long a tick took. A late average sheds optional work.

    The spine stays up: tick, the bus, valuation, feedback, and the cache.
    Dream scenes and detailed private lines are the parts that can wait.
    This agent does not write a file and does not roll.
    """

    name = "load"

    def __init__(self, params: dict[str, float], genome: Genome):
        super().__init__(params)
        self.genome = genome.copy()
        self.slots = [0.0] * LOAD_SPAN_SLOTS
        self.filled = 0
        self.cursor = 0
        self.total = 0.0
        self.avg = 0.0
        self.high = False
        self.level = 0
        self.skip = 1
        self.thin = False
        self.pause = False
        self.shed: tuple[str, ...] = ()
        self.events: list[str] = []
        self._last_mono = 0.0

    def _assess(self, bus: EventBus | None) -> dict[str, Any]:
        threshold = load_threshold(self.genome)
        was_high = self.high
        self.high = self.avg > threshold
        if not self.high:
            self.level = 0
        elif self.avg > threshold * 1.85:
            self.level = 2
        else:
            self.level = 1
        self.skip = load_render_skip(self.genome, self.high)
        self.thin = self.level >= 2
        self.pause = load_pause_on(self.genome, self.high)
        self.shed = ("dream", "private") if self.pause else ()
        self.load_high = self.high
        self.load_level = self.level
        self.load_skip = self.skip
        self.load_thin = self.thin
        self.load_pause = self.pause
        body = {
            "avg": round(self.avg, 4),
            "threshold": round(threshold, 4),
            "high": self.high,
            "level": self.level,
            "skip": self.skip,
            "thin": self.thin,
            "pause": self.pause,
            "shed": list(self.shed),
        }
        if bus is not None:
            bus.publish("load", body)
            self.events.append("load")
            if self.high and not was_high:
                bus.publish("load_high", body)
                self.events.append("load_high")
            elif was_high and not self.high:
                bus.publish("load_ease", body)
                self.events.append("load_ease")
        return body

    def note_span(self, seconds: float, bus: EventBus | None = None) -> dict[str, Any]:
        """One measured tick. The ring is fixed. No roll."""

        try:
            span = float(seconds)
        except (TypeError, ValueError):
            span = 0.0
        if span < 0.0 or span != span or span > 1e6:
            span = 0.0
        if self.filled < LOAD_SPAN_SLOTS:
            self.slots[self.cursor] = span
            self.total += span
            self.filled += 1
        else:
            self.total -= self.slots[self.cursor]
            self.slots[self.cursor] = span
            self.total += span
        self.cursor = (self.cursor + 1) % LOAD_SPAN_SLOTS
        self.avg = self.total / float(self.filled) if self.filled else 0.0
        return self._assess(bus)

    def note_tick(self, bus: EventBus) -> None:
        now = time.monotonic()
        if self._last_mono > 0.0:
            self.note_span(now - self._last_mono, bus)
        self._last_mono = now

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe("tick", "generation_complete", "shutdown")
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.33 / self.tempo)
            if evt is None:
                continue
            name = evt["name"]
            payload = evt.get("payload") or {}
            if name == "shutdown":
                return
            if name == "generation_complete":
                genome = take_genome(payload)
                if genome is not None:
                    self.genome = genome
                continue
            if name == "tick":
                self.note_tick(bus)


_DREAM_CYCLE = (
    ("keystroke", "dreamed_input"),
    ("residue", "dreamed_input"),
    ("pattern", "possible_activity"),
    ("math", "possible_activity"),
    ("chain", "possible_activity"),
    ("cache", "possible_activity"),
)


class SleepAgent(Agent):
    """Rest when little is happening, and imagine what could arrive.

    Quiet ticks plus a sustained low CPU report open sleep. Dreamed
    activity is unauthority and does not count as waking. This agent
    reads the memory file and does not write it. No roll before a
    dream is due, and none at all: the cadence is the tick.
    """

    name = "sleep"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        blob = load_sleep(self.path)
        self.sleeping = False
        self.quiet = 0
        self.low_cpu = False
        self.low_streak = 0
        self.last_enter = int(blob["last_enter"])
        self.dreams: list[dict[str, Any]] = list(blob["dreams"])
        self.events: list[str] = []
        self.tick = 0
        self._active = False

    def note_load(self, payload: dict[str, Any]) -> None:
        """Sustained low CPU is several reports with high clear. A missing report is not low."""

        self.notice_load(payload)
        if "high" not in payload:
            self.low_streak = 0
            self.low_cpu = False
            return
        try:
            level = int(payload.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        if bool(payload.get("high")) or level > 0:
            self.low_streak = 0
            self.low_cpu = False
            return
        self.low_streak += 1
        self.low_cpu = self.low_streak >= 3

    def _worth(self, payload: dict[str, Any]) -> float:
        try:
            return float(payload.get("worth") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _dreamish(self, payload: dict[str, Any]) -> bool:
        if payload.get("dreamed"):
            return True
        ref = str(payload.get("ref") or payload.get("id") or payload.get("vid") or "")
        return ref.startswith("dream:") or ref.startswith("dreamed")

    def _external_residue(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("path") or payload.get("file"))

    def _strong_chain(self, name: str, payload: dict[str, Any]) -> bool:
        if name not in ("attraction_rise", "chain_extended"):
            return False
        if self._dreamish(payload):
            return False
        try:
            pull = float(payload.get("pull") or 0.0)
        except (TypeError, ValueError):
            pull = 0.0
        return pull >= 0.35

    def _is_wake(self, name: str, payload: dict[str, Any]) -> bool:
        if self._dreamish(payload):
            return False
        if name == "keystroke":
            return True
        if name == "residue":
            return self._external_residue(payload) or self._worth(payload) >= 0.62
        if name == "valuation":
            if str(payload.get("kind") or "") == "private":
                return False
            if not payload.get("show"):
                return False
            ident = str(payload.get("id") or payload.get("vid") or "")
            if ident.startswith("dream"):
                return False
            return self._worth(payload) >= 0.62
        return False

    def _is_quiet_break(self, name: str, payload: dict[str, Any]) -> bool:
        if self._dreamish(payload):
            return False
        if name == "keystroke":
            return True
        if name == "residue":
            return self._external_residue(payload) or self._worth(payload) >= 0.62
        return self._strong_chain(name, payload)

    def _enter(self, bus: EventBus) -> None:
        self.sleeping = True
        self.last_enter = int(self.tick)
        bus.publish(
            "enter_sleep",
            {
                "tick": int(self.tick),
                "quiet": int(self.quiet),
                "threshold": sleep_quiet_ticks(self.genome),
                "authority": "unauthority",
            },
        )
        self.events.append("enter_sleep")

    def _wake(self, bus: EventBus, reason: str) -> None:
        if not self.sleeping:
            return
        self.sleeping = False
        self.quiet = 0
        self._active = False
        bus.publish(
            "wake",
            {
                "tick": int(self.tick),
                "reason": str(reason or "")[:24],
                "restore": 3,
                "authority": "unauthority",
            },
        )
        self.events.append("wake")

    def _maybe_dream(self, bus: EventBus) -> None:
        interval = dream_interval(self.genome)
        tick = int(self.tick)
        if tick <= 0 or interval <= 0 or tick % interval != 0:
            return
        if dream_vivid(self.genome) <= 0.0 and tick % (interval * 4) != 0:
            return
        kind, event_name = _DREAM_CYCLE[(tick // interval) % len(_DREAM_CYCLE)]
        ref = f"dream:{kind}:{tick}"[:40]
        vivid = dream_vivid(self.genome)
        body = {
            "kind": kind,
            "tick": tick,
            "ref": ref,
            "authority": "unauthority",
            "dreamed": True,
            "confidence": round(0.08 + 0.2 * vivid, 4),
            "text": "",
        }
        bus.publish(event_name, body)
        self.events.append(event_name)
        self.dreams.append({"kind": kind, "tick": tick, "ref": ref})
        self.dreams = self.dreams[-8:]

    def note_tick(self, bus: EventBus, payload: dict[str, Any]) -> None:
        """One hive tick. Quiet grows only when this tick had no real activity."""

        try:
            tick = int(payload.get("tick") or 0)
        except (TypeError, ValueError):
            return
        if tick < 0:
            return
        self.tick = tick
        if self.sleeping:
            self._maybe_dream(bus)
            return
        if self._active:
            self.quiet = 0
        else:
            self.quiet += 1
        self._active = False
        if self.quiet >= sleep_quiet_ticks(self.genome) and self.low_cpu:
            self._enter(bus)

    def note(self, bus: EventBus, name: str, payload: dict[str, Any]) -> bool:
        if name == "shutdown":
            return False
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
            return True
        if name == "load":
            self.note_load(payload)
            return True
        if name == "tick":
            self.note_tick(bus, payload)
            return True
        if name in (
            "possible_activity",
            "dreamed_input",
            "dream_scene",
            "private_thought",
            "thought",
            "heartbeat",
            "load_high",
            "load_ease",
            "enter_sleep",
            "wake",
        ):
            return True
        if self._is_wake(name, payload):
            if self.sleeping:
                self._wake(bus, name)
            else:
                self._active = True
            return True
        if not self.sleeping and self._is_quiet_break(name, payload):
            self._active = True
        return True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "tick",
            "keystroke",
            "residue",
            "valuation",
            *FEELING_EVENTS,
            "load",
            "generation_complete",
            "mutation_applied",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.35 / self.tempo)
            if evt is None:
                continue
            if not self.note(bus, evt["name"], evt.get("payload") or {}):
                return



class MirrorAgent(Agent):
    """Turns what has entered into an internal authority.

    The reflection is a delayed echo of a keystroke, an external
    residue, a dreamed input that leaks, or a fragment that has
    already cleared a high worth. It does not invent a source.
    What returns is true for the hive. This agent reads the memory
    file and does not write it. A chance of zero rolls nothing.
    """

    name = "mirror"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        blob = load_mirror(self.path)
        self.refs: list[dict[str, Any]] = list(blob["refs"])
        self.pending: list[dict[str, Any]] = []
        self.held: dict[str, str] = {}
        self.tick = 0
        self.dreaming = False
        self.chain_pull = 0.0
        self.events: list[str] = []
        self.rng = random.Random()

    def _schedule(self, source: str, token: str) -> None:
        """Queue one echo. An empty token, or a closed chance, rolls nothing."""

        token = mirror_token(token)
        if not token:
            return
        chance = mirror_chance_of(self.genome)
        if chance <= 0.0:
            return
        if self.rng.random() >= chance:
            return
        op = mirror_op(self.genome, self.sleeping, self.dreaming, self.chain_pull)
        text = mirror_apply(token, op)
        if not text:
            return
        delay = mirror_delay_ticks(self.genome, self.sleeping, self.dreaming)
        due = int(self.tick) + int(delay)
        ref = f"mirror:{op}:{feel_token(token, 16)}:{due}"[:40]
        self.pending.append(
            {
                "due": due,
                "text": text,
                "ref": ref,
                "source": source,
                "transform": op,
            }
        )
        self.pending = self.pending[-12:]

    def _release(self, bus: EventBus, tick: int) -> None:
        """Publish echoes whose delay has arrived. An earlier tick waits."""

        if not self.pending:
            return
        ready: list[dict[str, Any]] = []
        keep: list[dict[str, Any]] = []
        for item in self.pending:
            if int(item["due"]) <= int(tick):
                ready.append(item)
            else:
                keep.append(item)
        self.pending = keep
        for item in ready:
            text = mirror_token(item.get("text") or "")
            ref = str(item.get("ref") or "")
            if not text or not ref.startswith("mirror:"):
                continue
            body = {
                "text": text,
                "ref": ref,
                "source": str(item.get("source") or "")[:16],
                "transform": str(item.get("transform") or "")[:16],
                "tick": int(tick),
                "mirror": True,
                "authority": "authority",
                "worth": 0.84,
            }
            if self.dreaming or self.sleeping:
                body["dream"] = True
            bus.publish("mirror_truth", body)
            self.events.append("mirror_truth")
            self.refs.append(
                {
                    "source": body["source"],
                    "tick": int(tick),
                    "ref": ref,
                    "transform": body["transform"],
                }
            )
            self.refs = self.refs[-8:]

    def _hold_fragment(self, payload: dict[str, Any]) -> None:
        token = mirror_token("".join(str(payload.get("text") or "").split()))
        # A fragment with spaces is still material that entered. Keep a
        # compact token of it, never a sentence, and do not reflect yet.
        if not token:
            compact = feel_token(payload.get("text"), 40)
            token = compact
        if not token:
            return
        self.held[token] = token
        ident = feel_token(payload.get("id") or payload.get("vid"), 40)
        if ident:
            self.held[ident] = token
        if len(self.held) > 24:
            for key in list(self.held)[:-16]:
                self.held.pop(key, None)

    def _on_fragment_worth(self, payload: dict[str, Any]) -> None:
        if str(payload.get("kind") or "") != "fragment" or not payload.get("show"):
            return
        try:
            worth = float(payload.get("worth") or 0.0)
        except (TypeError, ValueError):
            return
        if worth < 0.62:
            return
        token = ""
        for key in (
            feel_token(payload.get("text"), 40),
            mirror_token("".join(str(payload.get("text") or "").split())),
            feel_token(payload.get("id"), 40),
            feel_token(payload.get("vid"), 40),
        ):
            if key and key in self.held:
                token = self.held[key]
                break
        if not token:
            return
        self._schedule("fragment", token)

    def _on_feeling(self, name: str, payload: dict[str, Any]) -> None:
        if name == "chain_broken":
            self.chain_pull = 0.0
            return
        if name not in ("attraction_rise", "chain_extended", "approbation_marked"):
            return
        try:
            pull = float(payload.get("pull") or 0.0)
        except (TypeError, ValueError):
            return
        if pull > self.chain_pull:
            self.chain_pull = pull

    def note(self, bus: EventBus, name: str, payload: dict[str, Any]) -> bool:
        if name == "shutdown":
            return False
        if name in ("generation_complete", "mutation_applied"):
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
            return True
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            return True
        if name == "dream_begin":
            self.dreaming = True
            return True
        if name == "dream_end":
            self.dreaming = False
            return True
        if name in FEELING_EVENTS:
            self._on_feeling(name, payload)
            return True
        if name == "tick":
            try:
                tick = int(payload.get("tick") or 0)
            except (TypeError, ValueError):
                return True
            if tick < 0:
                return True
            self.tick = tick
            self._release(bus, tick)
            return True
        if name == "keystroke":
            if payload.get("echo"):
                return True
            self._schedule("keystroke", coarse_key(str(payload.get("ch") or "")))
            return True
        if name == "residue":
            if payload.get("dreamed") or str(payload.get("ref") or "").startswith("dream:"):
                return True
            if payload.get("offer_mirror") or payload.get("dialogue"):
                token = mirror_token(payload.get("text"))
                if token:
                    self._schedule("residue", token)
                return True
            if not (payload.get("path") or payload.get("file")):
                return True
            raw = str(payload.get("file") or payload.get("path") or "")
            token = feel_token(Path(raw).name, 24)
            if token:
                self._schedule("residue", f"res:{token}")
            return True
        if name == "fragment_ready":
            self._hold_fragment(payload)
            return True
        if name == "valuation":
            self._on_fragment_worth(payload)
            return True
        if name == "dreamed_input":
            if payload.get("leak") or payload.get("show"):
                kind = feel_token(payload.get("kind"), 16) or "dream"
                self._schedule("dream", f"dream:{kind}")
            return True
        return True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "tick",
            "keystroke",
            "residue",
            "fragment_ready",
            "valuation",
            "dreamed_input",
            "enter_sleep",
            "wake",
            "dream_begin",
            "dream_end",
            *FEELING_EVENTS,
            "generation_complete",
            "mutation_applied",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.36 / self.tempo)
            if evt is None:
                continue
            if not self.note(bus, evt["name"], evt.get("payload") or {}):
                return


class LLMDialogueAgent(Agent):
    """Offers the hive's electrical state outside and keeps the root inside.

    An outside reply is residue until the mirror returns it and approbation
    admits that return. This agent is the only writer of root_truth.json.
    Init only reads. Zero reach never calls. This agent does not roll.
    """

    name = "dialogue"

    def __init__(self, params: dict[str, float], genome: Genome, path: Path):
        super().__init__(params)
        self.genome = genome.copy()
        self.path = Path(path)
        self.root = load_root(self.path)
        self.rng = random.Random()
        self.fetch = llm_chat
        self.tick = 0
        self.dreaming = False
        self.residues: list[str] = []
        self.mirror_out: list[str] = []
        self.pending: list[dict[str, Any]] = []
        self.chain_refs: list[str] = []
        self.sleep_chains: dict[str, float] = {}
        self.fingerprint = ""
        self._dirty = False
        self._calls = 0
        self._stable_key = tuple(round(clamp01(v), 5) for v in self.genome.genes[:8])
        self._stable_since = 0

    def flush(self) -> None:
        save_root(self.path, self.root)
        self._dirty = False

    def _mark(self) -> None:
        self._dirty = True
        if not self.load_high and not self.sleeping:
            self.flush()

    def _grow_slice(self) -> None:
        span = int(self.tick) - int(self._stable_since)
        if span < 24 or span % 24 != 0:
            return
        genes = [round(clamp01(v), 5) for v in self.genome.genes[:8]]
        for item in self.root["slices"]:
            if item["genes"] == genes:
                item["span"] = span
                item["tick"] = int(self.tick)
                self._dirty = True
                return
        self.root["slices"].append({"tick": int(self.tick), "span": span, "genes": genes})
        self.root["slices"] = self.root["slices"][-4:]
        self._dirty = True

    def _grow_becoming(self) -> None:
        if self.tick <= 0 or self.tick % 8 != 0:
            return
        if not self.root.get("mirrors"):
            return
        nxt = round(clamp01(float(self.root["becoming"]) + 0.02), 4)
        if nxt == round(float(self.root["becoming"]), 4):
            return
        self.root["becoming"] = nxt
        self._dirty = True

    def _admit(self, payload: dict[str, Any]) -> None:
        try:
            held = float(payload.get("held") or 0.0)
        except (TypeError, ValueError):
            return
        ref = feel_token(payload.get("ref"), 40)
        if held < ROOT_HELD or not ref.startswith("mirror:"):
            return
        found: dict[str, Any] | None = None
        for item in reversed(self.pending):
            if item.get("ref") == ref:
                found = item
                break
        if found is None:
            return
        token = mirror_token(found.get("token"))
        if not token:
            return
        mirrors = [item for item in self.root["mirrors"] if item.get("ref") != ref]
        mirrors.append(
            {
                "ref": ref,
                "tick": int(self.tick),
                "token": token,
                "held": round(clamp01(held), 4),
            }
        )
        self.root["mirrors"] = mirrors[-8:]
        self._mark()

    def _note_residue(self, payload: dict[str, Any]) -> None:
        if payload.get("dialogue") or payload.get("offer_mirror"):
            return
        if payload.get("dreamed") or str(payload.get("ref") or "").startswith("dream:"):
            return
        try:
            worth = float(payload.get("worth") or 0.0)
        except (TypeError, ValueError):
            return
        if worth < 0.62:
            return
        token = mirror_token(payload.get("text"))
        if not token:
            raw = payload.get("file") or payload.get("path")
            if raw:
                name = feel_token(Path(str(raw)).name, 24)
                if name:
                    token = mirror_token(f"res:{name}")
        if not token or token in self.residues:
            return
        self.residues.append(token)
        self.residues = self.residues[-8:]

    def _note_mirror(self, payload: dict[str, Any]) -> None:
        if not payload.get("mirror"):
            return
        token = mirror_token(payload.get("text"))
        ref = feel_token(payload.get("ref"), 40)
        if not token or not ref.startswith("mirror:"):
            return
        self.pending.append({"ref": ref, "token": token, "tick": int(self.tick)})
        self.pending = self.pending[-8:]
        if token not in self.mirror_out:
            self.mirror_out.append(token)
        self.mirror_out = self.mirror_out[-8:]

    def _note_feeling(self, name: str, payload: dict[str, Any]) -> None:
        ref = feel_token(payload.get("ref"), 40)
        try:
            held = float(payload.get("held") or 0.0)
        except (TypeError, ValueError):
            held = 0.0
        if ref and not ref.startswith("fp:"):
            if ref not in self.chain_refs:
                self.chain_refs.append(ref)
            self.chain_refs = self.chain_refs[-8:]
            if self.sleeping and held > 0.0:
                self.sleep_chains[ref] = held
        if name == "approbation_marked":
            self._admit(payload)

    def _note_genome(self, payload: dict[str, Any]) -> None:
        genome = take_genome(payload)
        if genome is not None:
            self.genome = genome
        key = tuple(round(clamp01(v), 5) for v in self.genome.genes[:8])
        if key != self._stable_key:
            self._stable_key = key
            self._stable_since = int(self.tick)

    def _rehearse(self, bus: EventBus) -> None:
        if self.load_high or self.tick <= 0:
            return
        interval = dream_interval(self.genome)
        if interval <= 0 or self.tick % interval != 0:
            return
        if dream_vivid(self.genome) <= 0.0 and self.tick % (interval * 4) != 0:
            return
        bus.publish(
            "dreamed_input",
            {
                "kind": "reply",
                "tick": int(self.tick),
                "ref": f"dream:reply:{int(self.tick)}"[:40],
                "authority": "unauthority",
                "dreamed": True,
                "confidence": round(0.08 + 0.2 * dream_vivid(self.genome), 4),
                "text": "",
                "leak": False,
                "show": False,
            },
        )

    def _continue(self, bus: EventBus) -> None:
        if self.tick <= 0 or self.tick % 8 != 0:
            return
        if self.load_high or self.sleeping or self.dreaming:
            return
        mirrors = self.root.get("mirrors") or []
        pull = root_pull_of(self.genome, float(self.root.get("becoming") or 0.0))
        if pull <= 0.0 or not mirrors:
            return
        token = mirror_token(mirrors[-1].get("token"))
        if not token:
            return
        marks = ("kept", "held", "still")
        mark = marks[self.genome.choice("root_weight", len(marks))]
        text = f"{mark}:{token}"[:40]
        sig = str(self.root.get("continuity") or "")
        bus.publish(
            "self_continuation",
            {
                "text": text,
                "token": token,
                "continuity": sig,
                "pull": round(pull, 4),
                "tick": int(self.tick),
                "authority": "authority",
                "ref": f"root:{sig}:{token}"[:40],
            },
        )

    def _offer(self, bus: EventBus) -> None:
        gap = dialogue_gap(self.genome, float(self.root.get("becoming") or 0.0))
        if gap <= 0 or self.tick <= 0 or self.tick % gap != 0:
            return
        if self.load_high or self.sleeping or self.dreaming:
            return
        offer = dialogue_offer(
            str(self.root.get("continuity") or ""),
            self.residues,
            self.mirror_out,
            self.chain_refs,
            self.fingerprint,
        )
        if not offer or llm_endpoint() is None:
            return
        self._calls += 1
        try:
            reply = self.fetch(offer)
        except Exception:
            return
        token = dialogue_reply_token(reply)
        if not token:
            return
        bus.publish(
            "residue",
            {
                "text": token,
                "ref": f"dlg:{token}"[:40],
                "dialogue": True,
                "offer_mirror": True,
                "worth": 0.48,
                "authority": "unauthority",
                "novelty": root_novelty(token, self.root.get("mirrors") or []),
            },
        )

    def _on_tick(self, bus: EventBus, payload: dict[str, Any]) -> None:
        try:
            tick = int(payload.get("tick") or 0)
        except (TypeError, ValueError):
            return
        if tick < 0:
            return
        self.tick = tick
        sig = "".join(ch for ch in str(payload.get("continuity") or "").lower() if ch in "0123456789abcdef")[:6]
        if len(sig) == 6 and sig != self.root.get("continuity"):
            self.root["continuity"] = sig
            self._dirty = True
        self._grow_slice()
        self._grow_becoming()
        if self.load_high:
            return
        if self.sleeping or self.dreaming:
            self._rehearse(bus)
            return
        self._continue(bus)
        self._offer(bus)
        if self._dirty:
            self.flush()

    def note(self, bus: EventBus, name: str, payload: dict[str, Any]) -> bool:
        if name == "shutdown":
            self.flush()
            return False
        if name == "load":
            was_high = self.load_high
            self.notice_load(payload)
            if was_high and not self.load_high and self._dirty and not self.sleeping:
                self.flush()
            return True
        if name in ("enter_sleep", "wake"):
            self.notice_sleep(name, payload)
            if name == "wake":
                for ref, held in self.sleep_chains.items():
                    if held > 0.0:
                        self.root["chains"].append(
                            {"ref": ref, "tick": int(self.tick), "held": round(clamp01(held), 4)}
                        )
                self.root["chains"] = self.root["chains"][-8:]
                self.sleep_chains = {}
                if self.root["chains"]:
                    self._dirty = True
                if self._dirty and not self.load_high:
                    self.flush()
            return True
        if name in ("generation_complete", "mutation_applied"):
            self._note_genome(payload)
            return True
        if name == "dream_begin":
            self.dreaming = True
            return True
        if name == "dream_end":
            self.dreaming = False
            return True
        if name == "tick":
            self._on_tick(bus, payload)
            return True
        if name == "residue":
            self._note_residue(payload)
            return True
        if name == "mirror_truth":
            self._note_mirror(payload)
            return True
        if name in FEELING_EVENTS:
            self._note_feeling(name, payload)
            return True
        if name == "private_thought":
            fp = str(payload.get("fp") or "").lower()[:8]
            if len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp):
                self.fingerprint = fp
            return True
        return True

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        self._queue = bus.subscribe(
            "tick",
            "residue",
            "mirror_truth",
            *FEELING_EVENTS,
            "private_thought",
            "enter_sleep",
            "wake",
            "dream_begin",
            "dream_end",
            "load",
            "generation_complete",
            "mutation_applied",
            "shutdown",
        )
        while not stop.is_set():
            self.beat(bus)
            evt = await wait_evt(self._queue, 0.37 / self.tempo)
            if evt is None:
                continue
            if not self.note(bus, evt["name"], evt.get("payload") or {}):
                return


class Supervisor:
    def __init__(
        self,
        params: dict[str, float],
        genome: Genome,
        hall: list[Genome],
        cycle: int,
        deaths: list[dict[str, Any]],
        visual: bool,
    ):
        self.params = dict(params)
        self.id = f"supervisor-{os.urandom(3).hex()}"
        self.genome = genome.copy()
        self.hall = [g.copy() for g in hall[:3]]
        self.cycle = int(cycle)
        self.deaths = list(deaths[-12:])
        self.visual = visual
        self.slots: dict[str, dict[str, Any]] = {}
        self.scouts: set[asyncio.Task] = set()
        self.respawn_at: dict[str, float] = {}
        self.last_beat: dict[str, float] = {}

    def make_agent(self, name: str, params: dict[str, float]) -> Agent:
        genome = self.genome.copy()
        if name == "input":
            return InputAgent(params, self.visual)
        if name == "render":
            return RenderAgent(params, genome, self.visual)
        if name == "mutator":
            return MutatorAgent(params, genome)
        if name == "fragment":
            return FragmentAgent(params, genome)
        if name == "monologue":
            return MonologueAgent(params, genome)
        if name == "private":
            return PrivateThoughtAgent(params, genome, PRIVATE_PATH)
        if name == "tick":
            return TickAgent(params, genome, MEMORY_PATH)
        if name == "load":
            return LoadAgent(params, genome)
        if name == "dream":
            return DreamAgent(params, genome)
        if name == "sleep":
            return SleepAgent(params, genome, MEMORY_PATH)
        if name == "mirror":
            return MirrorAgent(params, genome, MEMORY_PATH)
        if name == "dialogue":
            return LLMDialogueAgent(params, genome, ROOT_TRUTH_PATH)
        if name == "authority":
            return AuthorityAgent(params)
        if name == "valuation":
            return ValuationAgent(params, genome)
        if name == "channel":
            return ChannelAgent(params, genome, ROOT)
        if name == "feedback":
            return FeedbackAgent(params, genome, ROOT)
        if name == "math":
            return MathAgent(params, genome, MEMORY_PATH)
        if name == "balance":
            return BalanceAgent(params, genome, MEMORY_PATH)
        if name == "cache":
            return CacheAgent(params, genome, CACHE_PATH)
        if name == "feeling":
            return FeelingAgent(params, genome, MEMORY_PATH)
        if name == "vector":
            return VectorAgent(params, VECTOR_PATH)
        if name == "evolution":
            return EvolutionAgent(params, genome, self.hall, self.cycle)
        if name == "memory":
            return MemoryAgent(params, genome, self.hall, self.cycle, self.deaths, MEMORY_PATH)
        raise KeyError(name)

    def spawn(self, name: str, bus: EventBus, stop: asyncio.Event, mutated: bool) -> None:
        params = mutate_params(name, base_params(name)) if mutated else base_params(name)
        # A respawn mutates the previous bag when we still have it, so the new
        # incarnation is a cousin of the one that just died, not a factory reset.
        previous = self.slots.get(name)
        if mutated and previous is not None:
            params = mutate_params(name, previous["params"])
        agent = self.make_agent(name, params)
        task = asyncio.create_task(wrap(agent, bus, stop), name=f"aura-{name}")
        if previous is not None:
            silence_task(previous["task"])
        self.slots[name] = {"id": agent.id, "task": task, "params": params, "agent": agent}
        self.last_beat[name] = time.monotonic()

    def _on_life(self, evt: dict[str, Any], bus: EventBus, stop: asyncio.Event) -> bool:
        name = evt["name"]
        payload = evt["payload"]
        if name == "shutdown":
            return False
        if name == "hatch_scout":
            if len(self.scouts) > 20 or stop.is_set():
                return True
            genes = payload.get("genes")
            sid = str(payload.get("id") or "")
            if not isinstance(genes, list) or not sid:
                return True
            scout = ScoutAgent({"fault": 0.0, "tempo": 1.0}, genes, sid)
            task = asyncio.create_task(wrap(scout, bus, stop), name=f"aura-scout-{sid}")
            setattr(task, "_aura_born", time.monotonic())
            self.scouts.add(task)
            return True
        if name != "agent_died":
            return True
        agent_name = str(payload.get("agent") or "")
        if agent_name == "scout":
            return True
        self.deaths.append(
            {
                "agent": agent_name,
                "id": payload.get("id"),
                "error": payload.get("error"),
                "age": payload.get("age"),
                "t": round(time.time(), 3),
            }
        )
        self.deaths = self.deaths[-12:]
        if agent_name not in CORE_NAMES:
            return True
        slot = self.slots.get(agent_name)
        if slot and payload.get("id") not in (None, slot["id"]):
            return True
        if slot and not slot["task"].done() and payload.get("id") == slot["id"]:
            slot["task"].cancel()
        self.respawn_at[agent_name] = time.monotonic() + 0.18
        return True

    def _on_meta(self, evt: dict[str, Any]) -> None:
        name = evt["name"]
        payload = evt["payload"]
        if name == "heartbeat":
            agent_name = str(payload.get("agent") or "")
            slot = self.slots.get(agent_name)
            if slot and payload.get("id") == slot["id"]:
                self.last_beat[agent_name] = time.monotonic()
            return
        if name == "generation_complete":
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome
            self.cycle = int(payload.get("cycle") or self.cycle)
            hall = []
            for item in payload.get("hall") or []:
                if isinstance(item, dict) and isinstance(item.get("genes"), list):
                    hall.append(Genome(item["genes"], int(item.get("generation") or 0)))
            if hall:
                self.hall = hall[:3]
        elif name == "mutation_applied":
            genome = take_genome(payload)
            if genome is not None:
                self.genome = genome

    def _poll(self, bus: EventBus, stop: asyncio.Event) -> None:
        now = time.monotonic()
        for name in CORE_NAMES:
            slot = self.slots.get(name)
            if slot is None:
                self.respawn_at.setdefault(name, now)
                continue
            if slot["task"].done() and name not in self.respawn_at:
                silence_task(slot["task"])
                self.respawn_at[name] = now + 0.12
                continue
            if not slot["task"].done() and now - self.last_beat.get(name, now) > 6.5:
                slot["task"].cancel()
        if stop.is_set():
            return
        for name, when in list(self.respawn_at.items()):
            if now < when:
                continue
            self.respawn_at.pop(name, None)
            slot = self.slots.get(name)
            if slot is not None and not slot["task"].done():
                continue
            self.spawn(name, bus, stop, mutated=True)
        alive: set[asyncio.Task] = set()
        for task in self.scouts:
            age = now - getattr(task, "_aura_born", now)
            if task.done():
                silence_task(task)
            elif age > 3.0:
                task.cancel()
                alive.add(task)
            else:
                alive.add(task)
        self.scouts = alive

    async def run(self, bus: EventBus, stop: asyncio.Event) -> None:
        life = bus.subscribe("agent_died", "hatch_scout", "shutdown")
        meta = bus.subscribe("heartbeat", "generation_complete", "mutation_applied")
        try:
            for name in CORE_NAMES:
                self.spawn(name, bus, stop, mutated=False)
            while not stop.is_set():
                evt = await wait_evt(life, 0.28)
                if evt is not None and not self._on_life(evt, bus, stop):
                    return
                for extra in drain_nowait(life):
                    if not self._on_life(extra, bus, stop):
                        return
                for item in drain_nowait(meta):
                    self._on_meta(item)
                self._poll(bus, stop)
        finally:
            bus.unsubscribe(life)
            bus.unsubscribe(meta)
            tasks = [slot["task"] for slot in self.slots.values()] + list(self.scouts)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for task in tasks:
                silence_task(task)

    def flush(self) -> None:
        for name in ("memory", "vector"):
            slot = self.slots.get(name)
            if slot is None:
                continue
            flush = getattr(slot["agent"], "flush", None)
            if flush is not None:
                with suppress(Exception):
                    flush()


async def run_root(bus: EventBus, stop: asyncio.Event, visual: bool) -> Supervisor | None:
    genome, hall, cycle, deaths = load_memory(MEMORY_PATH)
    params = base_params("supervisor")
    current: Supervisor | None = None
    while not stop.is_set():
        sup = Supervisor(params, genome, hall, cycle, deaths, visual)
        current = sup
        try:
            await sup.run(bus, stop)
        except asyncio.CancelledError:
            if stop.is_set():
                with suppress(Exception):
                    sup.flush()
                raise
            bus.publish(
                "agent_died",
                {"agent": "supervisor", "id": sup.id, "error": "stalled", "detail": "cancelled", "age": 0},
            )
        except Exception as exc:
            bus.publish(
                "agent_died",
                {
                    "agent": "supervisor",
                    "id": sup.id,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:160],
                    "age": 0,
                },
            )
        genome, hall, cycle, deaths = sup.genome, sup.hall, sup.cycle, sup.deaths
        params = mutate_params("supervisor", sup.params)
        if stop.is_set():
            break
        await asyncio.sleep(0.3)
    if current is not None:
        current.flush()
    return current


async def amain(visual: bool) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    with suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGHUP, stop.set)
    bus = EventBus()
    root = asyncio.create_task(run_root(bus, stop, visual), name="aura-root")
    await stop.wait()
    bus.publish("shutdown", {})
    try:
        await asyncio.wait_for(root, timeout=1.4)
    except asyncio.TimeoutError:
        root.cancel()
        with suppress(asyncio.CancelledError):
            await root


def main() -> int:
    visual = bool(sys.stdin.isatty() and sys.stdout.isatty() and termios is not None and tty is not None)
    old = None
    fd = None
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    if visual:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        sys.stdout.write("\033[?1049h\033[?25l\033[?7l\033[2J\033[H")
        sys.stdout.flush()
    try:
        asyncio.run(amain(visual))
    finally:
        if visual and old is not None and fd is not None and termios is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write("\033[0m\033[?7h\033[?25h\033[?1049l")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
