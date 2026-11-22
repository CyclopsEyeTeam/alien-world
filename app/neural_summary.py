"""A typed public numeric summary for the existing metered provider request.

Unknown fields reject the whole optional addition. Owner wording, provider,
model, token limits and scheduling remain the original Config's responsibility.
"""
from dataclasses import replace
import json
import math
from api_config import Config

FIELDS = {'version', 'dominant_chroma', 'spikes_per_tick', 'last_mirrored_region',
          'grounded_samples', 'internally_confirmed', 'sleep', 'source_scope',
          'semantic_verification'}
PREFIX = '\n\nLocal neural measurements; self or mixed source, meaning unknown:\n'


def _number(value, high=1.):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= high:
        raise ValueError('invalid public neural measurement')


def public_neural_prompt(config, summary):
    """Return a replaced Config only when a complete safe addition fits its bounds."""
    if summary is None or not isinstance(config, Config):
        return config
    try:
        if not isinstance(summary, dict) or set(summary) != FIELDS:
            return config
        if type(summary['version']) is not int or summary['version'] != 1 or type(summary['sleep']) is not bool:
            return config
        if summary['source_scope'] != 'self_or_mixed_unknown' or summary['semantic_verification'] != 'unknown':
            return config
        if summary['dominant_chroma'] is not None:_number(summary['dominant_chroma'])
        _number(summary['spikes_per_tick'], 64.)
        for name in ('grounded_samples', 'internally_confirmed'):
            if type(summary[name]) is not int or not 0 <= summary[name] < 2**63:
                return config
        region = summary['last_mirrored_region']
        if region is not None:
            if not isinstance(region, dict) or set(region) != {'x', 'y'}:
                return config
            _number(region['x']);_number(region['y'])
        encoded = json.dumps(summary, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(encoded.encode('utf-8')) > 768:
            return config
        prompt = config.prompt+PREFIX+encoded
        if len(prompt.encode('utf-8')) > 4096:
            return config
        return replace(config, prompt=prompt)
    except (KeyError, ValueError, TypeError, OverflowError, RecursionError):
        return config
