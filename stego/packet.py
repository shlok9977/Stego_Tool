"""
packet.py
Defines the binary container format that gets hidden inside the carrier
(image or audio). This lets us store arbitrary files/text, know when to
stop reading, verify integrity, and know if it's encrypted.

Layout (all big-endian):
  MAGIC        4 bytes   b"STG1"
  FLAGS        1 byte    bit0: encrypted, bit1: is_file
  NAME_LEN     2 bytes   length of filename (0 if plain text / no name)
  NAME         NAME_LEN bytes  utf-8 filename (empty for text messages)
  CHECKSUM     4 bytes   CRC32 of the (possibly encrypted) DATA
  DATA_LEN     8 bytes   length of DATA in bytes
  DATA         DATA_LEN bytes  the actual payload (text/file bytes, maybe encrypted)
"""
import struct
import zlib

MAGIC = b"STG1"

FLAG_ENCRYPTED = 0b01
FLAG_IS_FILE = 0b10


def build_packet(data: bytes, filename: str = "", encrypted: bool = False, is_file: bool = False) -> bytes:
    flags = 0
    if encrypted:
        flags |= FLAG_ENCRYPTED
    if is_file:
        flags |= FLAG_IS_FILE

    name_bytes = filename.encode("utf-8")
    checksum = zlib.crc32(data) & 0xFFFFFFFF

    header = MAGIC
    header += struct.pack(">B", flags)
    header += struct.pack(">H", len(name_bytes))
    header += name_bytes
    header += struct.pack(">I", checksum)
    header += struct.pack(">Q", len(data))

    return header + data


def parse_packet(blob: bytes):
    """Parse a packet from a byte stream. Returns dict with keys:
    flags, encrypted, is_file, filename, data
    Raises ValueError if malformed / checksum mismatch.
    """
    if len(blob) < 4:
        raise ValueError("No embedded data found (stream too short).")
    if blob[:4] != MAGIC:
        raise ValueError("No valid stego payload found (magic bytes mismatch). "
                          "Wrong carrier file, or nothing is hidden here.")
    offset = 4
    flags = blob[offset]
    offset += 1
    name_len = struct.unpack(">H", blob[offset:offset + 2])[0]
    offset += 2
    filename = blob[offset:offset + name_len].decode("utf-8", errors="replace")
    offset += name_len
    checksum_expected = struct.unpack(">I", blob[offset:offset + 4])[0]
    offset += 4
    data_len = struct.unpack(">Q", blob[offset:offset + 8])[0]
    offset += 8
    data = blob[offset:offset + data_len]

    if len(data) != data_len:
        raise ValueError("Embedded data is truncated — carrier may be corrupted "
                          "or capacity was exceeded during encoding.")

    checksum_actual = zlib.crc32(data) & 0xFFFFFFFF
    if checksum_actual != checksum_expected:
        raise ValueError("Checksum mismatch — data is corrupted or was extracted incorrectly.")

    return {
        "flags": flags,
        "encrypted": bool(flags & FLAG_ENCRYPTED),
        "is_file": bool(flags & FLAG_IS_FILE),
        "filename": filename,
        "data": data,
    }


def header_probe_size(max_name_len: int = 300) -> int:
    """Upper bound of header size, used when we only need to peek before
    knowing the true name length (used by bit-stream readers)."""
    return 4 + 1 + 2 + max_name_len + 4 + 8
