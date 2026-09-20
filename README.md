# StegoSuite

A feature-rich LSB steganography toolkit in Python — hide text or files inside
images (PNG/BMP) or audio (WAV), with optional AES-256 password protection.
Ships with both a desktop GUI and a scriptable CLI, built on a shared,
tested core engine.

## Features

- **Two carrier types** — PNG/BMP images and WAV audio, both lossless (required for LSB to survive).
- **Two payload types** — a plain text message, or any arbitrary file (extracted byte-exact).
- **Password protection** — AES-256-GCM, key derived via PBKDF2-HMAC-SHA256 (200k iterations). Leave blank for no encryption.
- **Adjustable bit depth (1–4 bits/channel or /sample)** — trade off capacity vs. detectability.
- **Integrity checking** — every payload is wrapped in a small header with a CRC32 checksum, so corrupted or truncated extraction fails loudly instead of returning garbage.
- **Capacity calculator** — see exactly how many bytes fit in a given carrier at each bit depth before you try to hide something too big.
- **Basic steganalysis** — a chi-square LSB heuristic to sanity-check whether an image might already contain hidden data. (Educational signal, not forensic proof.)
- **Desktop GUI** (`gui.py`) — dark-themed, tabbed interface (Hide / Extract / Capacity / Analyze / About), file previews, live capacity bars, background threading so the UI never freezes.
- **CLI** (`cli.py`) — every feature is also scriptable, plus an interactive text menu (`python3 cli.py menu`) if you don't pass a subcommand.

## Project layout

```
stego_tool/
├── stego/                 # core engine (no UI code — reusable/importable)
│   ├── packet.py           # binary container format (magic, flags, name, CRC32, length)
│   ├── crypto_utils.py      # AES-256-GCM encrypt/decrypt with password KDF
│   ├── bitstream.py         # shared n-bit-per-slot LSB read/write helpers
│   ├── image_stego.py       # PNG/BMP LSB encode/decode
│   ├── audio_stego.py       # WAV LSB encode/decode
│   ├── analyze.py           # chi-square steganalysis heuristic
│   └── api.py               # high-level hide()/reveal()/get_capacity() facade
├── gui.py                  # CustomTkinter desktop GUI
├── cli.py                  # argparse CLI + interactive menu
├── requirements.txt
└── README.md
```

The GUI and CLI are both thin front-ends: all real logic lives in `stego/`,
so it's easy to test, reuse in other scripts, or add a third front-end later.

## Setup

```bash
pip install -r requirements.txt
```

**Linux only:** Tkinter isn't always bundled with Python. If `import tkinter`
fails, install it via your package manager first, e.g.:

```bash
sudo apt install python3-tk      # Debian/Ubuntu
sudo dnf install python3-tkinter # Fedora
```

(Windows and macOS python.org installers include Tkinter by default.)

## Running the GUI

```bash
python3 gui.py
```

- **Hide tab** — pick a carrier, choose text or file payload, set bit depth, optional password, pick an output path, click "Hide Data".
- **Extract tab** — pick a stego file, enter the password if needed, choose a save folder, click "Extract Data".
- **Capacity tab** — see byte capacity at each bit depth for any carrier.
- **Analyze tab** — run the chi-square heuristic on an image.

## Running the CLI

```bash
# Hide a text message
python3 cli.py hide-text photo.png photo_stego.png -t "meet at dawn" -p "mypassword" -b 2

# Hide a file
python3 cli.py hide-file photo.png photo_stego.png -f secret.pdf -p "mypassword"

# Extract
python3 cli.py extract photo_stego.png -p "mypassword"

# Check capacity
python3 cli.py capacity photo.png

# Run steganalysis
python3 cli.py analyze photo.png

# No password protection: just omit -p
python3 cli.py hide-text photo.png out.png -t "plain hidden text"

# Interactive menu (no subcommand)
python3 cli.py
```

## How it works, briefly

1. The payload (text or file bytes) is optionally encrypted with AES-256-GCM using a key derived from your password.
2. It's wrapped in a small binary packet: magic bytes, flags (encrypted? is it a file?), filename, a CRC32 checksum, and the payload length.
3. The packet's bits are written into the least-significant bits of the carrier's pixel channels (or audio samples), 1–4 bits per element depending on the chosen bit depth. A tiny always-1-bit marker at the very start records which bit depth was used, so extraction doesn't need to guess.
4. Extraction reverses this: read the marker, stream bits back out, verify the checksum, decrypt if needed.

## Notes and limits

- Output **must** stay in a lossless format (PNG/BMP for images, WAV for audio) — re-saving as JPEG or MP3 will destroy the hidden bits.
- Higher bit depth = more capacity but a statistically noisier image/audio file, which is more detectable by steganalysis tools.
- The chi-square analyzer is a teaching heuristic, not a guarantee — it won't catch every embedding method, and it can misfire on already-noisy source images.
- This project is intended for educational and authorized security-research use (e.g. CTFs, coursework, understanding data-hiding/detection techniques).
