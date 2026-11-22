"""Bounded online competitive/temporal learning, independent of truth authority.

Sixteen typed, normalized measurements drive learned prototype units and a sparse
residual population. Context-conditioned recurrent connections predict later
measurements and bias competitive activation. No model provider or array runtime
is required. Snapshots contain learned parameters, never a live temporal link.
"""
from collections import OrderedDict
import copy
import hashlib
import json
import math
import random

FEATURE_NAMES = ('brightness', 'motion_energy', 'flicker_density', 'colour_dominance',
                 'hue_sin', 'hue_cos', 'saturation', 'persistence', 'attention_x',
                 'attention_y', 'attention_strength', 'dwell', 'change', 'density',
                 'edge', 'contrast')
SCHEMA = 'ALIEN_NEURAL_FIELD'
VERSION = 1
MAX_PROTOTYPES = 64
MAX_TRANSITIONS = 256
MAX_SUCCESSORS = 8
MAX_RECENT_KEYS = 256
IDENTITY_NAMES = ('world_id', 'segment_id', 'runtime', 'eye_runtime', 'source', 'epoch')
CONDITION_NAMES = ('sleeping', 'dreaming', 'load_high', 'load', 'held', 'approbation',
                   'chain_pull', 'clarity', 'sleep', 'chain', 'approbation_state',
                   'load_state')


def _number(value, low=0., high=1.):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('neural parameters must be finite bounded numbers')
    return float(value)


def _integer(value, low=0, high=2**64-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid neural counter')
    return value


def _features(features):
    if not isinstance(features, dict) or set(features)-set(FEATURE_NAMES):
        raise ValueError('neural features must use the versioned feature names')
    known = [features.get(name) is not None for name in FEATURE_NAMES]
    values = [_number(features[name]) if present else 0.
              for name, present in zip(FEATURE_NAMES, known)]
    return values, known


def _context(context):
    context = {} if context is None else context
    if not isinstance(context, dict) or len(context) > 32 or any(not isinstance(k, str) for k in context):
        raise ValueError('invalid neural context')
    try:
        raw = json.dumps(context, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ValueError('neural context must be bounded finite JSON') from None
    if len(raw.encode()) > 4096:
        raise ValueError('neural context exceeds allowance')
    for name in IDENTITY_NAMES[:-1]:
        value = context.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > 128):
            raise ValueError('invalid neural context identity')
    if context.get('epoch') is not None:
        _integer(context['epoch'])
    identity = json.dumps([context.get(k) for k in IDENTITY_NAMES], separators=(',', ':'))
    condition = {'source': context['source'][:64]} if isinstance(context.get('source'), str) else {}
    for name in CONDITION_NAMES:
        value = context.get(name)
        if type(value) is bool:
            condition[name] = value
        elif type(value) in (int, float):
            condition[name] = round(max(0., min(1., value))*4)/4
        elif isinstance(value, str):
            condition[name] = value[:64]
    encoded = json.dumps(condition, sort_keys=True, separators=(',', ':')).encode()
    return identity, hashlib.sha256(encoded).hexdigest()


def _distance(values, known, prototype):
    indices = [i for i in range(16) if known[i] and prototype['known'][i]]
    if not indices:
        return 1.
    return math.sqrt(sum((values[i]-prototype['center'][i])**2 for i in indices)/len(indices))


class NeuralField:
    def __init__(self, state=None, seed=761, units=128):
        if state is not None:
            if not isinstance(state, dict):
                raise ValueError('invalid neural state')
            seed = state.get('seed');units = state.get('units')
        self.seed = _integer(seed, 0, 2**31-1)
        if _integer(units) != 128:
            raise ValueError('this neural schema has exactly 128 units')
        self.units = units
        rng = random.Random(self.seed)
        self.projection = [[rng.uniform(-1, 1) for _ in range(16)] for _ in range(64)]
        self.prototypes = []
        self.transitions = OrderedDict()
        self.recent = OrderedDict()
        self.learned = 0
        self.reset_temporal()
        if state is not None:
            self._restore(state)

    def reset_temporal(self):
        """Forget current experience links while keeping every learned parameter."""
        self.previous = None
        self.links = OrderedDict()
        self.timeline = None

    def _previous_for(self, identity):
        parts = json.loads(identity)
        if self.timeline != parts[:3]:
            return None
        previous = self.links.get(parts[4])
        return previous if previous and previous['identity'] == identity else None

    def _row(self, prototype, condition):
        return self.transitions.get((prototype, condition))

    def _closest(self, values, known):
        candidates = [p for p in self.prototypes if any(a and b for a, b in zip(known, p['known']))]
        return min(candidates, key=lambda p: _distance(values, known, p)) if candidates else None

    def _forecast(self, values, known, condition):
        output = list(values);available = list(known)
        closest = self._closest(values, known)
        row = self._row(closest['id'], condition) if closest else None
        if row:
            for i, count in enumerate(row['counts']):
                if count:
                    output[i] = row['mean'][i];available[i] = True
        return output, available

    def predict(self, features, context=None):
        """Expected next normalized measurements; unknown channels default to zero."""
        values, known = _features(features);_identity, condition = _context(context)
        return self._forecast(values, known, condition)[0]

    def _encode(self, values, known, identity, condition, recurrent=True):
        result = [0.]*128
        if not any(known):
            return result
        prior = self._previous_for(identity) if recurrent else None
        row = self._row(prior['prototype'], prior['condition']) if prior else None
        total = sum(row['targets'].values()) if row else 0
        scores = []
        for prototype in self.prototypes:
            score = max(0., 1-_distance(values, known, prototype))
            if total:
                score += .15*row['targets'].get(prototype['id'], 0)/total
            scores.append((score, prototype['id']))
        for score, ident in sorted(scores, reverse=True)[:4]:
            if score > .05:
                result[ident] = score
        count = math.sqrt(sum(known))
        residual = [(max(0., sum((2*values[i]-1)*weights[i] for i in range(16) if known[i])/count), 64+n)
                    for n, weights in enumerate(self.projection)]
        for score, ident in sorted(residual, reverse=True)[:8]:
            if score:
                result[ident] = score*.45
        # Context is a sparse population, separate from the measurement mask.
        digest = bytes.fromhex(condition)
        for n in range(4):
            ident = 64+digest[n]%64
            result[ident] = max(result[ident], .12)
        norm = math.sqrt(sum(v*v for v in result))
        return [v/norm for v in result] if norm else result

    def encode(self, features, context=None):
        """Inference only: no support, habituation, recency or evidence mutation."""
        values, known = _features(features);identity, condition = _context(context)
        return self._encode(values, known, identity, condition)

    def learn(self, features, context, key, tick, eligible=True):
        values, known = _features(features);identity, condition = _context(context)
        tick = _integer(tick)
        if not isinstance(key, str) or not 1 <= len(key.encode()) <= 512 or type(eligible) is not bool:
            raise ValueError('invalid neural evidence identity')
        digest = hashlib.sha256(key.encode()).hexdigest()
        closest = self._closest(values, known)
        novelty = _distance(values, known, closest) if closest else 1.
        stats = dict(updated=False, created=False, novelty=novelty, habituation=closest['habituation'] if closest else 0.,
                     plasticity=0., support=closest['support'] if closest else 0,
                     prediction_error=None, baseline_error=None,
                     prototype_id=closest['id'] if closest else None,
                     evidence_key_hash=digest, context_hash=condition)
        identity_parts = json.loads(identity)
        if self.timeline != identity_parts[:3]:
            self.reset_temporal();self.timeline = identity_parts[:3]
        if not eligible or not any(known):
            self.links.pop(identity_parts[4], None);return stats
        # The registry supplies globally fenced evidence. This additional bounded
        # exact duplicate window never counts a repeated current capture twice.
        if digest in self.recent:
            return stats
        previous = self._previous_for(identity)
        if previous and tick <= previous['tick']:
            self.links.pop(identity_parts[4], None);previous = None
        if previous:
            forecast, available = self._forecast(previous['values'], previous['known'], previous['condition'])
            indices = [i for i in range(16) if known[i] and available[i]]
            if indices:
                stats['prediction_error'] = sum((forecast[i]-values[i])**2 for i in indices)/len(indices)
                stats['baseline_error'] = sum((previous['values'][i]-values[i])**2 for i in indices)/len(indices)
        created = len(self.prototypes) < MAX_PROTOTYPES and (closest is None or novelty > .20)
        if created:
            closest = dict(id=len(self.prototypes), center=list(values), known=list(known),
                           support=0, last_tick=tick, habituation=0.)
            self.prototypes.append(closest)
        elif closest is None:
            closest = min(self.prototypes, key=lambda p: p['support'])
        old_habituation = closest['habituation']
        plasticity = (.08+.24*novelty)/(1+old_habituation*.08)
        for i, present in enumerate(known):
            if present:
                closest['center'][i] = values[i] if not closest['known'][i] else closest['center'][i]+plasticity*(values[i]-closest['center'][i])
                closest['known'][i] = True
        closest['support'] = min(2**63-1, closest['support']+1)
        closest['last_tick'] = tick
        closest['habituation'] = min(1000., old_habituation*.985+1)
        if previous:
            row_key = (previous['prototype'], previous['condition'])
            row = self.transitions.get(row_key)
            if row is None:
                row = dict(mean=[0.]*16, counts=[0]*16, targets={})
                self.transitions[row_key] = row
            self.transitions.move_to_end(row_key)
            for i, present in enumerate(known):
                if present:
                    row['counts'][i] = min(1000000, row['counts'][i]+1)
                    row['mean'][i] += (values[i]-row['mean'][i])/min(128, row['counts'][i])
            target = closest['id']
            row['targets'][target] = min(1000000, row['targets'].get(target, 0)+1)
            if len(row['targets']) > MAX_SUCCESSORS:
                victim = min((ident for ident in row['targets'] if ident != target), key=lambda ident: row['targets'][ident])
                del row['targets'][victim]
            while len(self.transitions) > MAX_TRANSITIONS:
                self.transitions.popitem(last=False)
        self.recent[digest] = None
        while len(self.recent) > MAX_RECENT_KEYS:
            self.recent.popitem(last=False)
        self.learned = min(2**63-1, self.learned+1)
        self.previous = dict(identity=identity, condition=condition, prototype=closest['id'],
                             values=values, known=known, tick=tick)
        self.links[identity_parts[4]] = self.previous
        self.links.move_to_end(identity_parts[4])
        while len(self.links) > 12:
            self.links.popitem(last=False)
        stats.update(updated=True, created=created, habituation=closest['habituation'],
                     plasticity=plasticity, support=closest['support'], prototype_id=closest['id'])
        return stats

    def nearest(self, vector, k=3):
        if not isinstance(vector, (list, tuple)) or len(vector) != 128:
            raise ValueError('neural retrieval requires 128 activations')
        vector = [_number(v, -1., 1.) for v in vector]
        _integer(k, 1, 16)
        norm = math.sqrt(sum(v*v for v in vector))
        if not norm:
            return []
        _identity, neutral = _context(None)
        hits = []
        for prototype in self.prototypes:
            represented = self._encode(prototype['center'], prototype['known'], '', neutral, recurrent=False)
            score = sum(a*b for a, b in zip(vector, represented))/norm
            hits.append(dict(id=prototype['id'], score=max(-1., min(1., score)),
                             support=prototype['support'], last_tick=prototype['last_tick']))
        return sorted(hits, key=lambda hit: (-hit['score'], hit['id']))[:k]

    def snapshot(self):
        return dict(schema=SCHEMA, version=VERSION, seed=self.seed, units=self.units,
                    feature_names=list(FEATURE_NAMES), prototypes=copy.deepcopy(self.prototypes),
                    transitions=[dict(source=source, context=context, mean=list(row['mean']),
                                      counts=list(row['counts']), targets=[[ident, count] for ident, count in row['targets'].items()])
                                 for (source, context), row in self.transitions.items()],
                    recent=list(self.recent), learned=self.learned)

    def _restore(self, state):
        fields = {'schema', 'version', 'seed', 'units', 'feature_names', 'prototypes', 'transitions', 'recent', 'learned'}
        if set(state) != fields or state['schema'] != SCHEMA or type(state['version']) is not int or state['version'] != VERSION or state['feature_names'] != list(FEATURE_NAMES):
            raise ValueError('unsupported neural state schema')
        prototypes = state['prototypes'];transitions = state['transitions'];recent = state['recent']
        if not isinstance(prototypes, list) or len(prototypes) > MAX_PROTOTYPES or not isinstance(transitions, list) or len(transitions) > MAX_TRANSITIONS or not isinstance(recent, list) or len(recent) > MAX_RECENT_KEYS:
            raise ValueError('neural state exceeds allowance')
        self.learned = _integer(state['learned'], 0, 2**63-1)
        for index, prototype in enumerate(prototypes):
            if not isinstance(prototype, dict) or set(prototype) != {'id', 'center', 'known', 'support', 'last_tick', 'habituation'} or type(prototype['id']) is not int or prototype['id'] != index:
                raise ValueError('invalid neural prototype')
            center = prototype['center'];known = prototype['known']
            if not isinstance(center, list) or len(center) != 16 or not isinstance(known, list) or len(known) != 16 or any(type(v) is not bool for v in known) or not any(known):
                raise ValueError('invalid neural feature mask')
            center = [_number(v) for v in center]
            if any(not present and value != 0 for value, present in zip(center, known)):
                raise ValueError('unknown neural measurements must remain masked')
            self.prototypes.append(dict(id=index, center=center, known=list(known), support=_integer(prototype['support'], 1, 2**63-1),
                                        last_tick=_integer(prototype['last_tick']), habituation=_number(prototype['habituation'], 0, 1000)))
        for item in transitions:
            if not isinstance(item, dict) or set(item) != {'source', 'context', 'mean', 'counts', 'targets'}:
                raise ValueError('invalid neural transition')
            source = _integer(item['source'], 0, len(prototypes)-1);context = item['context']
            if not isinstance(context, str) or len(context) != 64 or any(c not in '0123456789abcdef' for c in context) or (source, context) in self.transitions:
                raise ValueError('invalid neural transition context')
            if not isinstance(item['mean'], list) or len(item['mean']) != 16 or not isinstance(item['counts'], list) or len(item['counts']) != 16 or not isinstance(item['targets'], list) or not 1 <= len(item['targets']) <= MAX_SUCCESSORS:
                raise ValueError('invalid neural connection bounds')
            mean = [_number(v) for v in item['mean']];counts = [_integer(v, 0, 1000000) for v in item['counts']]
            if not any(counts) or any(not count and value != 0 for value, count in zip(mean, counts)):
                raise ValueError('invalid neural conditional means')
            targets = {}
            for edge in item['targets']:
                if not isinstance(edge, list) or len(edge) != 2:
                    raise ValueError('invalid neural connection')
                target = _integer(edge[0], 0, len(prototypes)-1)
                if target in targets:
                    raise ValueError('duplicate neural connection')
                targets[target] = _integer(edge[1], 1, 1000000)
            self.transitions[(source, context)] = dict(mean=mean, counts=counts, targets=targets)
        for digest in recent:
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest) or digest in self.recent:
                raise ValueError('invalid neural evidence window')
            self.recent[digest] = None
        if sum(p['support'] for p in self.prototypes) != self.learned:
            raise ValueError('inconsistent neural support accounting')
