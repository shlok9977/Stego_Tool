"""
analyze.py
A lightweight steganalysis heuristic — NOT a proof, just a signal.
Uses a chi-square test on pixel value pairs (classic LSB steganalysis idea):
natural images have a fairly uneven distribution between "pair of values"
(2k, 2k+1); heavy LSB embedding tends to flatten that distribution toward
50/50, which raises the chi-square statistic.
"""
import numpy as np
from PIL import Image


def chi_square_lsb_score(image_path: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    arr = np.array(img, dtype=np.uint8).reshape(-1)

    # Bucket into pairs (0,1), (2,3), ... 128 buckets
    pair_idx = arr // 2
    counts = np.bincount(pair_idx, minlength=128)
    even_counts = np.array([np.sum(arr[pair_idx == k] % 2 == 0) for k in range(128)]) \
        if False else None  # placeholder avoided below for speed

    # Faster vectorized approach: count how many values in each pair bucket are even vs odd
    is_even = (arr % 2 == 0)
    total_in_pair = counts.astype(np.float64)
    even_in_pair = np.bincount(pair_idx[is_even], minlength=128).astype(np.float64)

    # Expected even count under "no embedding" null-ish assumption: half of each pair bucket
    expected = total_in_pair / 2.0
    # Avoid div by zero
    mask = total_in_pair > 0
    chi_sq = np.sum(((even_in_pair[mask] - expected[mask]) ** 2) / np.maximum(expected[mask], 1e-9))

    # Heuristic thresholding (not a rigorous p-value — just a rough signal)
    if chi_sq < 60:
        verdict = "High likelihood of LSB steganography (very flat even/odd distribution)"
        risk = "high"
    elif chi_sq < 140:
        verdict = "Possible LSB steganography — inconclusive, worth a closer look"
        risk = "medium"
    else:
        verdict = "Low likelihood of LSB steganography (distribution looks natural)"
        risk = "low"

    return {
        "chi_square": round(float(chi_sq), 2),
        "verdict": verdict,
        "risk": risk,
        "note": "Heuristic only — not forensic proof. High-bit-depth or non-LSB techniques can evade this.",
    }
