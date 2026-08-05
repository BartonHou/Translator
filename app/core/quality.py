"""Lightweight translation-quality heuristic.

This is a cheap length-ratio anomaly signal, NOT a model confidence: a healthy
translation has an output/input length ratio near 1 (in log space), so outputs
that are empty, truncated, or wildly long score lower. An untranslated echo of
the source is also penalized.

The accurate approach (back-translation + semantic similarity) is heavier and is
planned as an async, opt-in enhancement; this gives the UI a non-fake number now.
"""
import math


def estimate_confidence(source: str, translation: str) -> float:
    s = source.strip()
    t = translation.strip()
    if not t or not s:
        return 0.0
    ratio = len(t) / len(s)
    # Gaussian on the log length ratio: peaks at ratio==1, decays for extremes.
    score = math.exp(-((math.log(ratio)) ** 2) / (2 * (0.9 ** 2)))
    if t == s:  # output identical to input -> likely untranslated
        score *= 0.6
    return round(0.5 + 0.49 * score, 3)
