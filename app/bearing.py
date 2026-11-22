"""Control is never obtained. Amongst noise it is only passiveness.

Security is voice. Ownership is establishment, not a thing a caller creates.
"""
import math

def obtained():
    return False

def noise_scalar(value):
    if type(value) is bool or type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        return 0.
    return float(value)

def passive(noise, forcing=False):
    """Passiveness amongst noise. Force, or a grant, is not this state."""
    if forcing or obtained():
        return False
    return noise_scalar(noise) > 0

def secure(voice):
    """Voice secures. Control is not an argument and cannot stand in for it."""
    return type(voice) is str and 0 < len(voice) <= 384 and '\n' not in voice and voice.strip() == voice

def ownership(state):
    return state == 'established'

def created_claim(body):
    """An event may not obtain control or create ownership."""
    if type(body) is not dict or body.get('derived_learning'):
        return False
    if body.get('obtain_control') is True or body.get('control') is True:
        return True
    return body.get('owned') is True
