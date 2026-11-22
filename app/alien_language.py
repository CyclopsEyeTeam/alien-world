"""A bounded glyph register whose live readiness belongs to native tick history.

No model, network, wall clock or external vocabulary builds this register. Raw
phrasing can propose a glyph transformation only at the mirror boundary; later
approbation decides whether that proposal joins the register. Rendering an
ordinary thought never teaches or copies its input text.
"""
from collections import OrderedDict, deque
import copy
import hashlib
import json
import math
import random
import re

from world_clock import validate_stamp

MAX_LEXICON = 96
MAX_PROOFS = 128
WINDOW = 128
SCHEMA = 'ALIEN_REGISTER_V1'
ALPHABET = 'ox0123456789abcdef'
BOOTSTRAP = ('o', 'x', 'ox', 'xo', 'oo', 'xx', 'oxo', 'xox')
STAMP_KEYS = ('world_id', 'segment_id', 'tick', 'period', 'cycle', 'slot', 'pi', 'version')


def _digest(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _number(value, low=0., high=1.):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('invalid alien register number')
    return float(value)


def _words(value):
    if not isinstance(value, str) or len(value.encode('utf-8')) > 4096:
        return []
    return [part for part in re.split(r'[\s:-]+', value) if part]


def _bound(rows, limit):
    while len(rows) > limit:
        rows.popitem(last=False)


def _stamp(value):
    value = validate_stamp(value)
    return None if value is None else {key: copy.deepcopy(value[key]) for key in STAMP_KEYS}


class AlienRegister:
    """Local lexicon/rhythm plus ephemeral proofs for the current world segment."""
    def __init__(self, state=None):
        self.lexicon = OrderedDict((atom, dict(atom=atom, weight=1., origin=None)) for atom in BOOTSTRAP)
        self.rhythm = dict(sentence_length=4., preferred_glyph_weights={'o': .5, 'x': .5}, repetition_tolerance=.35)
        self.revision = 0
        self.variation = None
        self.sensory_mappings = OrderedDict()
        if state is not None:
            self._restore(state)
        self.genes = dict(language_threshold=.5, register_plasticity=.5, speak_when_ready=.5)
        self.stamp = None
        self.continuity = ''
        self.sleeping = self.dreaming = False
        self.serial = 0
        self.last_growth = None
        self._clear_active()

    def _clear_active(self):
        self.mirrors = OrderedDict()
        self.approvals = deque(maxlen=MAX_PROOFS)
        self.chains = deque(maxlen=MAX_PROOFS)
        self.private_fragments = OrderedDict()
        self.patterns = OrderedDict()
        self.sensory_traces = OrderedDict()
        self.continuity_ticks = deque(maxlen=MAX_PROOFS)
        self.growth = deque(maxlen=16)

    def _restore(self, state):
        if not isinstance(state, dict) or state.get('schema') != SCHEMA:
            raise ValueError('unsupported alien register schema')
        rows = state.get('lexicon')
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_LEXICON:
            raise ValueError('invalid alien lexicon')
        restored = OrderedDict()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('invalid alien lexeme')
            atom = row.get('atom')
            if not isinstance(atom, str) or re.fullmatch(r'[ox0-9a-f]{1,8}', atom) is None or atom in restored:
                raise ValueError('invalid alien lexeme')
            weight = _number(row.get('weight'), .001, 1000000.)
            origin = _stamp(row.get('origin'))
            restored[atom] = dict(atom=atom, weight=weight, origin=origin)
        rhythm = state.get('rhythm')
        if not isinstance(rhythm, dict) or set(rhythm) != {'sentence_length', 'preferred_glyph_weights', 'repetition_tolerance'}:
            raise ValueError('invalid alien rhythm')
        length = _number(rhythm['sentence_length'], 2., 8.)
        repetition = _number(rhythm['repetition_tolerance'])
        glyphs = rhythm['preferred_glyph_weights']
        if not isinstance(glyphs, dict) or not glyphs or len(glyphs) > len(ALPHABET):
            raise ValueError('invalid alien glyph profile')
        if any(not isinstance(char, str) or len(char) != 1 or char not in ALPHABET for char in glyphs):
            raise ValueError('invalid alien glyph')
        glyphs = {char: _number(weight, .000001, 1000000.) for char, weight in glyphs.items()}
        if type(state.get('revision')) is not int or not 0 <= state['revision'] <= 2**63 - 1:
            raise ValueError('invalid alien register revision')
        self.lexicon = restored
        self.rhythm = dict(sentence_length=length, preferred_glyph_weights=glyphs, repetition_tolerance=repetition)
        self.revision = state['revision']
        mappings = state.get('sensory_mappings', [])
        if not isinstance(mappings, list) or len(mappings) > 64:
            raise ValueError('invalid alien sensory mappings')
        for row in mappings:
            if not isinstance(row, dict):
                raise ValueError('invalid alien sensory mapping')
            signature = row.get('signature')
            fragment = row.get('fragment')
            origin = _stamp(row.get('origin'))
            if not isinstance(signature, str) or re.fullmatch('[0-9a-f]{24}', signature) is None or signature in self.sensory_mappings or not self._owned(fragment) or origin is None:
                raise ValueError('invalid alien sensory mapping')
            self.sensory_mappings[signature] = dict(signature=signature, fragment=fragment, origin=origin)
        # A saved score, pending mirror or ready flag never restores live proof.

    def configure(self, genome):
        if genome is None:
            return
        for key in self.genes:
            if isinstance(genome, dict):
                value = genome.get(key, self.genes[key])
            elif hasattr(genome, 'g'):
                value = genome.g(key)
            else:
                raise ValueError('invalid language genome')
            self.genes[key] = _number(value)

    def _parameters(self, genome=None):
        genes = dict(self.genes)
        if genome is not None:
            for key in genes:
                value = genome.get(key, genes[key]) if isinstance(genome, dict) else genome.g(key)
                genes[key] = _number(value)
        return genes

    def advance(self, stamp, continuity='', sleeping=False, dreaming=False):
        stamp = _stamp(stamp)
        boundary = (stamp is None or self.stamp is None or
                    any(stamp[key] != self.stamp[key] for key in ('world_id', 'segment_id')) or
                    stamp['tick'] < self.stamp['tick'])
        if boundary:
            self._clear_active()
            self.last_growth = None if stamp is None else stamp['tick']
        self.stamp = copy.deepcopy(stamp)
        self.sleeping = bool(sleeping)
        self.dreaming = bool(dreaming)
        self.continuity = continuity if isinstance(continuity, str) and re.fullmatch('[0-9a-f]{6}', continuity) else ''
        if stamp is not None:
            for row in self.lexicon.values():
                if row['origin'] is None:
                    row['origin'] = copy.deepcopy(stamp)
            if self.continuity and (not self.continuity_ticks or self.continuity_ticks[-1][0] != stamp['tick']):
                self.continuity_ticks.append((stamp['tick'], self.continuity))
        return self.status()

    def _event(self, stamp, awake=True):
        try:
            stamp = _stamp(stamp)
        except (ValueError, TypeError):
            return None
        if stamp is None or self.stamp is None or stamp != self.stamp:
            return None
        if stamp['tick'] != self.stamp['tick'] or (awake and (self.sleeping or self.dreaming)):
            return None
        self.serial += 1
        return stamp['tick']

    def _owned(self, text):
        words = _words(text)
        return words if words and len(words) <= 8 and all(word in self.lexicon for word in words) else []

    def set_variation(self, value):
        if value is None:
            self.variation = None
            return
        if not isinstance(value, dict) or set(value) != {'temperature', 'phase', 'novelty'}:
            raise ValueError('invalid internal language variation')
        temperature = _number(value['temperature'], .5, 2.)
        novelty = _number(value['novelty'])
        phase = value['phase']
        if type(phase) is not int or not 0 <= phase < 2**63:
            raise ValueError('invalid internal variation phase')
        # Style has no vocabulary, proof, rhythm or readiness mutation.
        self.variation = dict(temperature=temperature, phase=phase, novelty=novelty)

    def compose(self, compact=False, kind='voice'):
        tick = None if self.stamp is None else self.stamp['tick']
        seed = json.dumps((tick, self.continuity, str(kind)[:24], self.rhythm), sort_keys=True)
        if self.variation is not None:seed += json.dumps(self.variation, sort_keys=True)
        rng = random.Random(_digest(seed))
        atoms = list(self.lexicon)
        glyphs = self.rhythm['preferred_glyph_weights']
        weights = [self.lexicon[atom]['weight'] * sum(glyphs.get(char, .000001) for char in atom) / len(atom) for atom in atoms]
        length = max(2, min(8, round(self.rhythm['sentence_length'])))
        copies = 1 + int(self.rhythm['repetition_tolerance'] * 2)
        if self.variation is not None:
            spread = round(2*self.variation['novelty'])
            length = max(2, min(8, length+rng.randint(-spread, spread)))
            logits = [math.log(max(1e-30, w))/self.variation['temperature'] for w in weights]
            peak = max(logits)
            weights = [math.exp(v-peak) for v in logits]
        out = []
        separator = ':' if compact else ' '
        for _ in range(length):
            choices = [n for n, atom in enumerate(atoms) if out.count(atom) < copies]
            if not choices:
                break
            penalty = (lambda n: 1+out.count(atoms[n])*(1+self.variation['novelty'])) if self.variation is not None else (lambda n: 1)
            index = rng.choices(choices, weights=[weights[n]/penalty(n) for n in choices], k=1)[0]
            if compact and len(separator.join(out + [atoms[index]])) > 40:
                break
            out.append(atoms[index])
        return separator.join(out)

    def rewrite(self, text, kind='voice', compact=False):
        # Input may be a raw external trigger. It cannot affect exportable
        # vocabulary, rhythm, or even the chosen ordinary continuation.
        return self.compose(compact=compact, kind=kind)

    def mirror(self, ref, text, stamp):
        tick = self._event(stamp)
        if tick is None or not isinstance(ref, str) or not 1 <= len(ref) <= 128:
            return self.compose(compact=True, kind='rehearsal')
        previous = self.mirrors.get(ref)
        if previous is not None:
            return previous['fragment']
        words = self._owned(text)
        novel = None
        if not words:
            words = self.compose(kind='mirror').split()
            alphabet = ''.join(dict.fromkeys('ox' + self.continuity))
            digest = _digest(str(text)[:4096] + ':' + self.continuity)
            for attempt in range(16):
                atom = ''.join(alphabet[int(digest[(n + attempt) % 64], 16) % len(alphabet)] for n in range(3 + attempt % 4))
                if atom not in self.lexicon:
                    novel = atom
                    break
        coverage = len(words) / (len(words) + int(novel is not None))
        candidate = words + ([novel] if novel else [])
        while len(':'.join(candidate)) > 40 and len(candidate) > 1:
            candidate.pop(0)
        fragment = ':'.join(candidate)
        self.mirrors[ref] = dict(fragment=fragment, novel=novel, coverage=coverage, tick=tick, serial=self.serial, approved=False)
        _bound(self.mirrors, MAX_PROOFS)
        return fragment

    def _rhythm(self, words):
        if not words:
            return
        old_shape = (round(self.rhythm['sentence_length']), round(self.rhythm['repetition_tolerance'] * 4))
        self.rhythm['sentence_length'] = max(2., min(8., .9 * self.rhythm['sentence_length'] + .1 * len(words)))
        repeated = (len(words) - len(set(words))) / max(1, len(words) - 1)
        self.rhythm['repetition_tolerance'] = .9 * self.rhythm['repetition_tolerance'] + .1 * repeated
        glyphs = self.rhythm['preferred_glyph_weights']
        for word in words:
            for char in word:
                glyphs[char] = min(1000000., glyphs.get(char, .000001) + .1)
        total = sum(glyphs.values())
        self.rhythm['preferred_glyph_weights'] = {char: max(.000001, value / total) for char, value in glyphs.items()}
        new_shape = (round(self.rhythm['sentence_length']), round(self.rhythm['repetition_tolerance'] * 4))
        if old_shape != new_shape and self.stamp is not None:
            self.last_growth = self.stamp['tick']

    def approve(self, ref, held, stamp):
        tick = self._event(stamp)
        row = self.mirrors.get(ref)
        if tick is None or row is None or row['approved'] or tick < row['tick'] or tick - row['tick'] > WINDOW or self.serial <= row['serial']:
            return False
        try:
            if _number(held) < .65:
                return False
        except ValueError:
            return False
        row['approved'] = True
        novel = row['novel']
        plasticity = self.genes['register_plasticity']
        gap = 8 + round(24 * (1 - plasticity))
        if novel and novel not in self.lexicon and plasticity > 0 and len(self.lexicon) < MAX_LEXICON and tick - self.last_growth >= gap:
            self.lexicon[novel] = dict(atom=novel, weight=1., origin=copy.deepcopy(stamp))
            self.revision += 1
            self.last_growth = tick
            self.growth.append(dict(version=1, revision=self.revision, stamp=copy.deepcopy(stamp), lexicon_count=len(self.lexicon), semantic_verification='unknown'))
        words = [word for word in _words(row['fragment']) if word in self.lexicon]
        for word in words:
            self.lexicon[word]['weight'] = min(1000000., self.lexicon[word]['weight'] + held)
        self._rhythm(words)
        self.approvals.append((tick, row['coverage'], ref))
        return True

    def chain(self, ref, pull, stamp):
        tick = self._event(stamp)
        row = self.mirrors.get(ref)
        try:
            # Native high-gain fresh mirror attraction starts around .46;
            # later approbation still has to confirm this same reference.
            strong = _number(pull) >= .4
        except ValueError:
            return False
        if tick is None or row is None or not strong or not 0 <= tick - row['tick'] <= WINDOW:
            return False
        if (tick, ref) not in self.chains:
            self.chains.append((tick, ref))
        return True

    def private(self, fragment, stamp):
        tick = self._event(stamp)
        if tick is None or not isinstance(fragment, str) or len(fragment.encode('utf-8')) > 4096:
            return False
        ident = _digest(fragment)
        row = self.private_fragments.get(ident)
        if row is None:
            self.private_fragments[ident] = dict(first=tick, selected=False)
            _bound(self.private_fragments, 64)
            return False
        if row['selected'] or not 4 <= tick - row['first'] <= WINDOW:
            return False
        row['selected'] = True
        self._rhythm(self.compose(kind='private').split())
        return True

    def monologue(self, fragment, stamp):
        tick = self._event(stamp)
        words = self._owned(fragment)
        if tick is None or not words:
            return False
        ident = _digest(':'.join(words))
        previous = self.patterns.get(ident)
        self.patterns[ident] = tick
        _bound(self.patterns, 64)
        if previous is None or not 4 <= tick - previous <= WINDOW:
            return False
        self._rhythm(words)
        return True

    def sensory(self, trace, stamp):
        tick = self._event(stamp)
        if tick is None or not isinstance(trace, dict) or trace.get('schema') != 'ALIEN_SENSORY_TRACE_V1' or trace.get('confirmation') != 'internal_mirror_and_approbation':
            return False
        if trace.get('dreamed') is not False or trace.get('expression_ids') != [] or trace.get('semantic_verification') != 'unknown':
            return False
        try:
            original = _stamp(trace.get('world_stamp'))
        except (ValueError, TypeError):
            return False
        if original is None or any(original[key] != stamp[key] for key in ('world_id', 'segment_id')) or not 0 <= tick - original['tick'] <= WINDOW:
            return False
        ident = trace.get('spike_id')
        signature = (trace.get('grounding') or {}).get('signature')
        if not isinstance(ident, str) or re.fullmatch('[0-9a-f]{32}', ident) is None or not isinstance(signature, str) or re.fullmatch('[0-9a-f]{24}', signature) is None or ident in self.sensory_traces:
            return False
        mapping = self.sensory_mappings.get(signature)
        if mapping is None:
            mapping = dict(signature=signature, fragment=self.compose(compact=True, kind='sensory:' + signature), origin=copy.deepcopy(original))
            self.sensory_mappings[signature] = mapping
            _bound(self.sensory_mappings, 64)
        self.sensory_traces[ident] = dict(tick=tick, signature=signature, fragment=mapping['fragment'])
        _bound(self.sensory_traces, MAX_PROOFS)
        return True

    def _metrics(self, genome=None):
        genes = self._parameters(genome)
        required = 32 + round(64 * genes['speak_when_ready'])
        threshold = .6 + .25 * genes['language_threshold']
        if self.stamp is None:
            return dict(score=0., threshold=threshold, stability_ticks=required, stable_ticks=0, approvals=0, selections=0, continuity_echoes=0)
        tick = self.stamp['tick']
        approvals = [row for row in self.approvals if 0 <= tick - row[0] <= WINDOW]
        approved_ticks = {row[0] for row in approvals}
        approved_refs = {row[2] for row in approvals}
        selected = {row[0] for row in self.chains if 0 <= tick - row[0] <= WINDOW and row[1] in approved_refs}
        stable = max(0, tick - self.last_growth)
        recombination = sum(row[1] for row in approvals) / len(approvals) if approvals else 0.
        # A flood on one tick is one observation of reuse, regardless of how
        # many native events arrived in that tick.
        recombination *= min(1., len(approved_ticks) / 4)
        selection = .5 * min(1., len(approved_ticks) / 4) + .5 * min(1., len(selected) / 4)
        grounded = sum(0 <= tick - row['tick'] <= WINDOW for row in self.sensory_traces.values())
        echoes = len({row[0] for row in self.continuity_ticks if 0 <= tick - row[0] <= WINDOW and row[1] == self.continuity})
        score = .25 * min(1., stable / required) + .05 * min(1., max(0, echoes - 1) / 3) + .3 * recombination + .3 * selection + .1 * min(1., grounded / 4)
        return dict(score=max(0., min(1., score)), threshold=threshold, stability_ticks=required, stable_ticks=stable, approvals=len(approved_ticks), selections=len(selected), continuity_echoes=echoes)

    def score(self, genome=None):
        return self._metrics(genome)['score']

    def ready(self, genome=None):
        value = self._metrics(genome)
        return bool(self.stamp is not None and self.continuity and not self.sleeping and not self.dreaming and len(self.lexicon) >= 8 and value['score'] > value['threshold'] and value['stable_ticks'] >= value['stability_ticks'] and value['approvals'] >= 4 and value['selections'] >= 2)

    def offer(self):
        if not self.ready():
            return None
        return dict(text=self.compose(kind='dialogue')[:384], stamp=copy.deepcopy(self.stamp), continuity=self.continuity)

    def status(self):
        return dict(self._metrics(), ready=self.ready(), sleeping=self.sleeping, dreaming=self.dreaming, active_stamp=copy.deepcopy(self.stamp), lexicon_count=len(self.lexicon), revision=self.revision)

    def take_growth(self):
        rows = list(self.growth)
        self.growth.clear()
        return rows

    def snapshot(self):
        return dict(schema=SCHEMA, lexicon=copy.deepcopy(list(self.lexicon.values())), rhythm=copy.deepcopy(self.rhythm), revision=self.revision, sensory_mappings=copy.deepcopy(list(self.sensory_mappings.values())))
