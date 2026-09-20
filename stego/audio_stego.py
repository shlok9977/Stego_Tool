"""
audio_stego.py
LSB steganography for uncompressed WAV audio (PCM 8/16-bit). Output must
stay WAV — MP3 or any lossy re-encode will destroy the hidden bits.
"""
import struct
import wave
import numpy as np

from . import packet
from .bitstream import BitStreamReader, embed_bits_sequential

MARKER_SLOTS = 8


def _read_wav(path: str):
    with wave.open(path, "rb") as wf:
        params = wf.getparams()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    sampwidth = params.sampwidth
    if sampwidth == 1:
        dtype = np.uint8
    elif sampwidth == 2:
        dtype = np.int16
    else:
        raise ValueError(
            f"Unsupported WAV sample width ({sampwidth * 8}-bit). "
            f"Only 8-bit and 16-bit PCM WAV files are supported."
        )
    samples = np.frombuffer(raw, dtype=dtype).copy()
    return params, samples, dtype


def get_capacity_bytes(wav_path: str, bits_per_sample: int = 1) -> int:
    if not (1 <= bits_per_sample <= 4):
        raise ValueError("bits_per_sample must be between 1 and 4.")
    _, samples, _ = _read_wav(wav_path)
    usable_slots = len(samples) - MARKER_SLOTS
    usable_bits = usable_slots * bits_per_sample
    return max(usable_bits // 8, 0)


def encode_audio(carrier_path: str, output_path: str, payload: bytes, bits_per_sample: int = 1) -> str:
    if not (1 <= bits_per_sample <= 4):
        raise ValueError("bits_per_sample must be between 1 and 4.")
    if not output_path.lower().endswith(".wav"):
        raise ValueError("Output must be a .wav file — any other audio format is lossy and will destroy the data.")

    params, samples, dtype = _read_wav(carrier_path)

    capacity = get_capacity_bytes(carrier_path, bits_per_sample)
    if len(payload) > capacity:
        raise ValueError(
            f"Payload too large: {len(payload)} bytes needed, but this audio file only has "
            f"{capacity} bytes of capacity at {bits_per_sample} bit(s)/sample."
        )

    # Work on unsigned view so bit masking behaves predictably even for int16
    view = samples.view(np.uint16) if dtype == np.int16 else samples

    marker_bits = np.unpackbits(np.array([bits_per_sample], dtype=np.uint8))
    for i in range(MARKER_SLOTS):
        view[i] = (int(view[i]) & 0xFFFE) | int(marker_bits[i])

    embed_bits_sequential(view, MARKER_SLOTS, bits_per_sample, payload)

    out_samples = view.view(dtype) if dtype == np.int16 else view

    with wave.open(output_path, "wb") as wf:
        wf.setparams(params)
        wf.writeframes(out_samples.tobytes())

    return output_path


def decode_audio(stego_path: str) -> dict:
    params, samples, dtype = _read_wav(stego_path)
    view = samples.view(np.uint16) if dtype == np.int16 else samples

    marker_bits = np.array([int(view[i]) & 1 for i in range(MARKER_SLOTS)], dtype=np.uint8)
    bits_per_sample = int(np.packbits(marker_bits)[0])
    if not (1 <= bits_per_sample <= 4):
        raise ValueError(
            "No valid stego marker found in this audio file — either nothing is hidden "
            "here, or it wasn't encoded with this tool."
        )

    reader = BitStreamReader(view, MARKER_SLOTS, bits_per_sample)

    magic = reader.read_bytes(4)
    if magic != packet.MAGIC:
        raise ValueError("No valid stego payload found (magic bytes mismatch).")
    flags_byte = reader.read_bytes(1)
    name_len = struct.unpack(">H", reader.read_bytes(2))[0]
    name = reader.read_bytes(name_len)
    checksum = reader.read_bytes(4)
    data_len = struct.unpack(">Q", reader.read_bytes(8))[0]
    data = reader.read_bytes(data_len)

    full_blob = (
        packet.MAGIC + flags_byte + struct.pack(">H", name_len) + name +
        checksum + struct.pack(">Q", data_len) + data
    )
    return packet.parse_packet(full_blob)
