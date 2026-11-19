"""Shared "every N generations" trigger logic used across vibes, artists,
modifier creeps, character auto-cycle, and coordinate auto-randomize."""


def frequency_matches(frequency, generation_number):
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        frequency = 1
    return frequency <= 1 or generation_number % frequency == 0


def should_cycle_on_frequency(frequency, generation_number, set_pending):
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        frequency = 1
    if frequency <= 0:
        return bool(set_pending)
    return generation_number % frequency == 0


def loops_until_next(frequency, generation_number):
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        frequency = 1
    if frequency <= 1:
        return 0
    remainder = generation_number % frequency
    return 0 if remainder == 0 else frequency - remainder
