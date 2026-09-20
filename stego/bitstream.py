"""
bitstream.py
Shared helper for reading an n-bits-per-slot LSB stream back out as bytes.
Used by both image_stego.py and audio_stego.py so the exact same bit-packing
logic is used on encode and decode.
"""
import numpy as np


class BitStreamReader:
    """Reads bytes from a flat array of carrier values (pixel channels or
    audio samples), pulling `bits_per_slot` LSBs out of each element in
    sequence and reassembling them into bytes."""

    def __init__(self, flat: np.ndarray, start_slot: int, bits_per_slot: int):
        self.flat = flat
        self.idx = start_slot
        self.n = bits_per_slot
        self.buffer = []

    def _fill(self, min_bits: int):
        while len(self.buffer) < min_bits:
            if self.idx >= len(self.flat):
                raise ValueError(
                    "Ran out of carrier data while reading the embedded payload — "
                    "the carrier file may be corrupted, truncated, or nothing valid "
                    "is hidden inside it."
                )
            val = int(self.flat[self.idx]) & 0xFF
            for shift in range(self.n - 1, -1, -1):
                self.buffer.append((val >> shift) & 1)
            self.idx += 1

    def read_bytes(self, num_bytes: int) -> bytes:
        if num_bytes == 0:
            return b""
        need_bits = num_bytes * 8
        self._fill(need_bits)
        bits = self.buffer[:need_bits]
        self.buffer = self.buffer[need_bits:]
        arr = np.array(bits, dtype=np.uint8)
        return np.packbits(arr).tobytes()


def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def embed_bits_sequential(flat: np.ndarray, start_slot: int, bits_per_slot: int, payload: bytes) -> int:
    """Embed `payload` bytes into `flat` starting at `start_slot`, `bits_per_slot`
    LSBs per element, writing in place. Returns the next free slot index."""
    n = bits_per_slot
    mask = 0xFF ^ ((1 << n) - 1)
    bits = bytes_to_bits(payload)
    idx = start_slot
    bit_ptr = 0
    total = len(bits)
    while bit_ptr < total:
        chunk = bits[bit_ptr:bit_ptr + n]
        if len(chunk) < n:
            chunk = np.concatenate([chunk, np.zeros(n - len(chunk), dtype=np.uint8)])
        value = 0
        for b in chunk:
            value = (value << 1) | int(b)
        flat[idx] = (int(flat[idx]) & mask) | value
        idx += 1
        bit_ptr += n
    return idx
