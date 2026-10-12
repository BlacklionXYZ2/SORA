"""Five-vowel mouth shapes (A, E, I, O, U) estimated from speech audio.

Pure Python, so Core and the audio worker need no extra dependency. Each audio chunk gets a
linear-prediction spectral envelope; its first two peaks (formants F1 and F2) are compared with
typical vowel formants. Renderers map the five weights to their own mouth shapes, as VRM's
aa/ee/ih/oh/ou expressions do. The idea follows wLipSync in Project AIRI; no code is copied.
"""

from __future__ import annotations

import math
import struct

VOWELS = ("a", "e", "i", "o", "u")
# Typical adult (F1, F2) in Hz. Kokoro's default voices are female, so these sit between the
# classic female and male averages, closer to female.
VOWEL_FORMANTS = {
    "a": (850.0, 1450.0),
    "e": (550.0, 2150.0),
    "i": (330.0, 2600.0),
    "o": (550.0, 950.0),
    "u": (360.0, 1000.0),
}
ANALYSIS_RATE = 12_000
LPC_ORDER = 14
WINDOW = 360  # 30 ms at 12 kHz
MAX_BANDWIDTH = 500.0  # Hz; wider resonances are spectral tilt, not formants
SILENCE_RMS = 0.01
SHARPNESS = 0.16  # log-frequency distance at which a vowel's weight falls to about 60%


def vowel_weights(pcm_s16le: bytes, sample_rate: int, channels: int = 1) -> tuple[float, ...]:
    """Return weights for A, E, I, O, U that sum to 1, or all zeros for silence."""

    silent = (0.0,) * len(VOWELS)
    samples = _downsample(_mono(pcm_s16le, channels), sample_rate)
    frame = _loudest_window(samples)
    if frame is None:
        return silent
    formants = _formants(frame)
    if formants is None:
        return silent
    f1, f2 = formants
    scores = []
    for vowel in VOWELS:
        t1, t2 = VOWEL_FORMANTS[vowel]
        distance = math.hypot(math.log(f1 / t1), math.log(f2 / t2))
        scores.append(math.exp(-((distance / SHARPNESS) ** 2) / 2))
    total = sum(scores)
    if total <= 1e-9:
        return silent
    return tuple(score / total for score in scores)


def _mono(pcm: bytes, channels: int) -> list[float]:
    values = [sample / 32768.0 for (sample,) in struct.iter_unpack("<h", pcm)]
    return values[::channels] if channels > 1 else values


def _downsample(samples: list[float], sample_rate: int) -> list[float]:
    factor = max(1, round(sample_rate / ANALYSIS_RATE))
    if factor == 1:
        return samples
    # Averaging is a crude low-pass, which is enough below 3.5 kHz where F1 and F2 live.
    return [
        sum(samples[index : index + factor]) / factor
        for index in range(0, len(samples) - factor + 1, factor)
    ]


def _loudest_window(samples: list[float]) -> list[float] | None:
    if len(samples) < WINDOW:
        return None
    best: list[float] | None = None
    best_energy = 0.0
    for start in range(0, len(samples) - WINDOW + 1, WINDOW // 2):
        window = samples[start : start + WINDOW]
        energy = sum(value * value for value in window)
        if energy > best_energy:
            best, best_energy = window, energy
    if best is None or math.sqrt(best_energy / WINDOW) < SILENCE_RMS:
        return None
    return best


def _formants(frame: list[float]) -> tuple[float, float] | None:
    emphasised = [frame[0]] + [frame[n] - 0.97 * frame[n - 1] for n in range(1, len(frame))]
    size = len(emphasised)
    windowed = [
        value * (0.54 - 0.46 * math.cos(2 * math.pi * n / (size - 1)))
        for n, value in enumerate(emphasised)
    ]
    correlation = [
        sum(windowed[n] * windowed[n + lag] for n in range(size - lag))
        for lag in range(LPC_ORDER + 1)
    ]
    coefficients = _levinson(correlation)
    if coefficients is None:
        return None
    peaks = _resonances(coefficients)
    peaks = [peak for peak in peaks if peak >= 200]
    if len(peaks) < 2:
        return None
    return peaks[0], peaks[1]


def _levinson(correlation: list[float]) -> list[float] | None:
    if correlation[0] <= 0:
        return None
    error = correlation[0] * (1 + 1e-9)
    coefficients = [1.0] + [0.0] * LPC_ORDER
    for order in range(1, LPC_ORDER + 1):
        reflection = -sum(
            coefficients[k] * correlation[order - k] for k in range(order)
        ) / error
        previous = coefficients[:]
        for k in range(1, order):
            coefficients[k] = previous[k] + reflection * previous[order - k]
        coefficients[order] = reflection
        error *= 1 - reflection * reflection
        if error <= 0:
            return None
    return coefficients


def _resonances(coefficients: list[float]) -> list[float]:
    """Formant frequencies from the prediction polynomial's roots, narrowest first filtered."""

    roots = _polynomial_roots(coefficients)
    found = []
    for root in roots:
        if root.imag <= 0:
            continue
        radius = abs(root)
        if not 0 < radius < 1:
            continue
        frequency = math.atan2(root.imag, root.real) * ANALYSIS_RATE / (2 * math.pi)
        bandwidth = -math.log(radius) * ANALYSIS_RATE / math.pi
        if bandwidth <= MAX_BANDWIDTH:
            found.append(frequency)
    return sorted(found)


def _polynomial_roots(coefficients: list[float]) -> list[complex]:
    """Durand-Kerner roots of z^p + a1 z^(p-1) + ... + ap (``coefficients[0]`` is 1)."""

    degree = len(coefficients) - 1
    roots = [complex(0.9, 0) * complex(math.cos(angle), math.sin(angle))
             for angle in (2 * math.pi * (k + 0.25) / degree for k in range(degree))]

    def value(z: complex) -> complex:
        total = complex(0, 0)
        for a in coefficients:
            total = total * z + a
        return total

    for _ in range(80):
        moved = 0.0
        for index, root in enumerate(roots):
            denominator = complex(1, 0)
            for other_index, other in enumerate(roots):
                if other_index != index:
                    denominator *= root - other
            if denominator == 0:
                denominator = complex(1e-12, 0)
            step = value(root) / denominator
            roots[index] = root - step
            moved = max(moved, abs(step))
        if moved < 1e-9:
            break
    return roots
