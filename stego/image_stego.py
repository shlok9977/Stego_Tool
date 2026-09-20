"""
image_stego.py
LSB steganography for images. Works on any Pillow-readable image but you
MUST save output as a lossless format (PNG or BMP) — JPEG will destroy the
hidden bits during compression.
"""
import struct
import numpy as np
from PIL import Image

from . import packet
from .bitstream import BitStreamReader, embed_bits_sequential

MARKER_SLOTS = 8  # 8 channel slots, 1 bit each, always used to store bits_per_channel (1-4)
LOSSY_EXTENSIONS = {".jpg", ".jpeg", ".webp", ".gif"}


def _load_rgb_array(path: str):
    img = Image.open(path).convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    return img, arr


def get_capacity_bytes(image_path: str, bits_per_channel: int = 1) -> int:
    """Max payload bytes (the raw packet, after packet.build_packet) that can
    be hidden in this image at the given bit depth."""
    if not (1 <= bits_per_channel <= 4):
        raise ValueError("bits_per_channel must be between 1 and 4.")
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    total_slots = w * h * 3
    usable_slots = total_slots - MARKER_SLOTS
    usable_bits = usable_slots * bits_per_channel
    return max(usable_bits // 8, 0)


def encode_image(carrier_path: str, output_path: str, payload: bytes, bits_per_channel: int = 1) -> str:
    if not (1 <= bits_per_channel <= 4):
        raise ValueError("bits_per_channel must be between 1 and 4 (higher = more capacity, more detectable).")

    for ext in LOSSY_EXTENSIONS:
        if output_path.lower().endswith(ext):
            raise ValueError(
                f"Output format '{ext}' is lossy and will destroy the hidden data. "
                f"Save as .png or .bmp instead."
            )

    img, arr = _load_rgb_array(carrier_path)
    flat = arr.reshape(-1).copy()

    capacity = get_capacity_bytes(carrier_path, bits_per_channel)
    if len(payload) > capacity:
        raise ValueError(
            f"Payload too large: {len(payload)} bytes needed, but this image only has "
            f"{capacity} bytes of capacity at {bits_per_channel} bit(s)/channel. "
            f"Use a larger image, a higher --bits value, or a smaller payload."
        )

    # Marker: bits_per_channel stored as 1 bit per slot across the first 8 slots
    marker_bits = np.unpackbits(np.array([bits_per_channel], dtype=np.uint8))
    for i in range(MARKER_SLOTS):
        flat[i] = (flat[i] & 0xFE) | int(marker_bits[i])

    embed_bits_sequential(flat, MARKER_SLOTS, bits_per_channel, payload)

    out_arr = flat.reshape(arr.shape)
    Image.fromarray(out_arr, "RGB").save(output_path)
    return output_path


def decode_image(stego_path: str) -> dict:
    img, arr = _load_rgb_array(stego_path)
    flat = arr.reshape(-1)

    marker_bits = np.array([int(flat[i]) & 1 for i in range(MARKER_SLOTS)], dtype=np.uint8)
    bits_per_channel = int(np.packbits(marker_bits)[0])
    if not (1 <= bits_per_channel <= 4):
        raise ValueError(
            "No valid stego marker found in this image — either nothing is hidden here, "
            "or it wasn't encoded with this tool."
        )

    reader = BitStreamReader(flat, MARKER_SLOTS, bits_per_channel)

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
