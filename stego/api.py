"""
api.py
High-level, carrier-agnostic functions used by the CLI (and importable
directly if you want to script this). Dispatches to image_stego or
audio_stego based on the carrier file's extension.
"""
import os

from . import packet, crypto_utils, image_stego, audio_stego

IMAGE_EXTS = {".png", ".bmp"}
AUDIO_EXTS = {".wav"}


def _carrier_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    raise ValueError(
        f"Unsupported carrier extension '{ext}'. Use a lossless carrier: "
        f"{sorted(IMAGE_EXTS | AUDIO_EXTS)}"
    )


def get_capacity(carrier_path: str, bits: int = 1) -> int:
    kind = _carrier_kind(carrier_path)
    if kind == "image":
        return image_stego.get_capacity_bytes(carrier_path, bits)
    return audio_stego.get_capacity_bytes(carrier_path, bits)


def hide(carrier_path: str, output_path: str, data: bytes, filename: str = "",
         is_file: bool = False, password: str = None, bits: int = 1) -> dict:
    """Encrypt (optional) + pack + embed `data` into carrier_path, save to output_path.
    Returns a small report dict."""
    encrypted = password is not None and password != ""
    payload = crypto_utils.encrypt(data, password) if encrypted else data

    pkt = packet.build_packet(payload, filename=filename, encrypted=encrypted, is_file=is_file)

    kind = _carrier_kind(carrier_path)
    # output extension must match carrier kind
    out_kind = _carrier_kind(output_path)
    if out_kind != kind:
        raise ValueError(f"Output file extension must match carrier type ({kind}).")

    if kind == "image":
        image_stego.encode_image(carrier_path, output_path, pkt, bits_per_channel=bits)
    else:
        audio_stego.encode_audio(carrier_path, output_path, pkt, bits_per_sample=bits)

    return {
        "output": output_path,
        "carrier_kind": kind,
        "bits_used": bits,
        "raw_bytes_hidden": len(data),
        "packet_bytes": len(pkt),
        "encrypted": encrypted,
    }


def reveal(stego_path: str, password: str = None) -> dict:
    """Extract + (decrypt if needed) the payload from stego_path.
    Returns dict: filename, is_file, data (decrypted plaintext bytes)."""
    kind = _carrier_kind(stego_path)
    if kind == "image":
        parsed = image_stego.decode_image(stego_path)
    else:
        parsed = audio_stego.decode_audio(stego_path)

    data = parsed["data"]
    if parsed["encrypted"]:
        if not password:
            raise ValueError("This payload is password-protected — supply --password to decrypt it.")
        data = crypto_utils.decrypt(data, password)
    elif password:
        # Not encrypted but user supplied a password anyway — just ignore it, don't error.
        pass

    return {
        "filename": parsed["filename"],
        "is_file": parsed["is_file"],
        "encrypted": parsed["encrypted"],
        "data": data,
    }
