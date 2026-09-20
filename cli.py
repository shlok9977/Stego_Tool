#!/usr/bin/env python3
"""
StegoSuite — a feature-rich LSB steganography CLI.

Carriers supported : PNG, BMP (image)  |  WAV (audio)
Payloads supported  : plain text        |  any file
Extras              : AES-256-GCM password protection, adjustable bit depth
                       (1-4 bits/channel), capacity calculator, basic
                       steganalysis (chi-square heuristic), interactive menu.
"""
import argparse
import getpass
import os
import sys

from stego import api, analyze
from stego.image_stego import get_capacity_bytes as img_capacity
from stego.audio_stego import get_capacity_bytes as audio_capacity

BANNER = r"""
 ____  _                    ____        _ _
/ ___|| |_ ___  __ _  ___  / ___| _   _(_) |_ ___
\___ \| __/ _ \/ _` |/ _ \ \___ \| | | | | __/ _ \
 ___) | ||  __/ (_| | (_) | ___) | |_| | | ||  __/
|____/ \__\___|\__, |\___/ |____/ \__,_|_|\__\___|
               |___/          LSB steganography toolkit
"""


def _human(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _get_password(flag_value, prompt_if_missing, confirm=False):
    if flag_value:
        return flag_value
    if not prompt_if_missing:
        return None
    pw = getpass.getpass("Password (leave blank for none): ")
    if not pw:
        return None
    if confirm:
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            print("Passwords don't match.", file=sys.stderr)
            sys.exit(1)
    return pw


def cmd_hide_text(args):
    password = args.password if args.password else (_get_password(None, args.ask_password, confirm=True))
    data = args.text.encode("utf-8")
    try:
        report = api.hide(
            args.carrier, args.output, data,
            filename="", is_file=False,
            password=password, bits=args.bits,
        )
    except (ValueError, FileNotFoundError, OSError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Hidden {len(data)} bytes of text into '{report['output']}' "
          f"({report['bits_used']} bit/ch, encrypted={report['encrypted']})")


def cmd_hide_file(args):
    if not os.path.isfile(args.file):
        print(f"File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    password = args.password if args.password else (_get_password(None, args.ask_password, confirm=True))
    with open(args.file, "rb") as f:
        data = f.read()
    filename = os.path.basename(args.file)
    try:
        report = api.hide(
            args.carrier, args.output, data,
            filename=filename, is_file=True,
            password=password, bits=args.bits,
        )
    except (ValueError, FileNotFoundError, OSError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Hidden file '{filename}' ({_human(len(data))}) into '{report['output']}' "
          f"({report['bits_used']} bit/ch, encrypted={report['encrypted']})")


def cmd_extract(args):
    password = args.password if args.password else (_get_password(None, args.ask_password, confirm=False))
    try:
        result = api.reveal(args.stego, password=password)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    if result["is_file"]:
        out_path = args.output or result["filename"] or "extracted_output"
        with open(out_path, "wb") as f:
            f.write(result["data"])
        print(f"✅ Extracted file -> '{out_path}' ({_human(len(result['data']))})")
    else:
        text = result["data"].decode("utf-8", errors="replace")
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"✅ Extracted text -> '{args.output}'")
        else:
            print("✅ Extracted text message:\n")
            print(text)


def cmd_capacity(args):
    if not os.path.isfile(args.carrier):
        print(f"❌ File not found: {args.carrier}", file=sys.stderr)
        sys.exit(1)
    ext = os.path.splitext(args.carrier)[1].lower()
    fn = img_capacity if ext in (".png", ".bmp") else audio_capacity
    try:
        print(f"Capacity for '{args.carrier}':")
        for b in range(1, 5):
            cap = fn(args.carrier, b)
            note = "  (recommended: least detectable)" if b == 1 else ""
            print(f"  {b} bit/ch -> {_human(cap)}{note}")
    except (ValueError, OSError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


def cmd_analyze(args):
    if not os.path.isfile(args.image):
        print(f"❌ File not found: {args.image}", file=sys.stderr)
        sys.exit(1)
    try:
        result = analyze.chi_square_lsb_score(args.image)
    except (ValueError, OSError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Chi-square statistic : {result['chi_square']}")
    print(f"Risk level           : {result['risk'].upper()}")
    print(f"Verdict              : {result['verdict']}")
    print(f"Note                 : {result['note']}")


def cmd_menu(_args):
    print(BANNER)
    while True:
        print("\n1) Hide text in carrier")
        print("2) Hide a file in carrier")
        print("3) Extract from stego carrier")
        print("4) Check carrier capacity")
        print("5) Analyze image for hidden LSB data")
        print("6) Quit")
        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            carrier = input("Carrier path (png/bmp/wav): ").strip()
            text = input("Text to hide: ")
            output = input("Output path: ").strip()
            bits = int(input("Bits per channel/sample [1-4, default 1]: ") or "1")
            pw = getpass.getpass("Password (blank = none): ") or None
            try:
                report = api.hide(carrier, output, text.encode("utf-8"),
                                   filename="", is_file=False, password=pw, bits=bits)
                print(f"✅ Done -> {report}")
            except Exception as e:
                print(f"❌ {e}")

        elif choice == "2":
            carrier = input("Carrier path (png/bmp/wav): ").strip()
            file_path = input("File to hide: ").strip()
            output = input("Output path: ").strip()
            bits = int(input("Bits per channel/sample [1-4, default 1]: ") or "1")
            pw = getpass.getpass("Password (blank = none): ") or None
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                report = api.hide(carrier, output, data, filename=os.path.basename(file_path),
                                   is_file=True, password=pw, bits=bits)
                print(f"✅ Done -> {report}")
            except Exception as e:
                print(f"❌ {e}")

        elif choice == "3":
            stego = input("Stego carrier path: ").strip()
            pw = getpass.getpass("Password (blank if none): ") or None
            out = input("Save extracted output as [blank = auto]: ").strip() or None
            try:
                result = api.reveal(stego, password=pw)
                if result["is_file"]:
                    out_path = out or result["filename"] or "extracted_output"
                    with open(out_path, "wb") as f:
                        f.write(result["data"])
                    print(f"✅ Extracted file -> {out_path}")
                else:
                    text = result["data"].decode("utf-8", errors="replace")
                    print(f"✅ Extracted text:\n{text}")
            except Exception as e:
                print(f"❌ {e}")

        elif choice == "4":
            carrier = input("Carrier path: ").strip()
            ext = os.path.splitext(carrier)[1].lower()
            fn = img_capacity if ext in (".png", ".bmp") else audio_capacity
            try:
                for b in range(1, 5):
                    print(f"  {b} bit -> {_human(fn(carrier, b))}")
            except Exception as e:
                print(f"❌ {e}")

        elif choice == "5":
            image = input("Image path: ").strip()
            try:
                result = analyze.chi_square_lsb_score(image)
                print(result)
            except Exception as e:
                print(f"❌ {e}")

        elif choice == "6":
            print("Bye!")
            break
        else:
            print("Invalid choice.")


def build_parser():
    p = argparse.ArgumentParser(
        prog="stegosuite",
        description="Feature-rich LSB steganography toolkit (image + audio, encryption, capacity, analysis).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=BANNER,
    )
    sub = p.add_subparsers(dest="command")

    common_hide = dict(add_help=False)

    ht = sub.add_parser("hide-text", help="Hide a text message inside a carrier file")
    ht.add_argument("carrier", help="Carrier file (png/bmp/wav)")
    ht.add_argument("output", help="Output stego file (same extension as carrier)")
    ht.add_argument("-t", "--text", required=True, help="The text message to hide")
    ht.add_argument("-b", "--bits", type=int, default=1, choices=[1, 2, 3, 4],
                     help="Bits per channel/sample (default 1, higher=more capacity/detectable)")
    ht.add_argument("-p", "--password", help="Password to encrypt the payload (AES-256-GCM)")
    ht.add_argument("--ask-password", action="store_true", help="Prompt for a password interactively")
    ht.set_defaults(func=cmd_hide_text)

    hf = sub.add_parser("hide-file", help="Hide an arbitrary file inside a carrier file")
    hf.add_argument("carrier", help="Carrier file (png/bmp/wav)")
    hf.add_argument("output", help="Output stego file (same extension as carrier)")
    hf.add_argument("-f", "--file", required=True, help="Path of the file to hide")
    hf.add_argument("-b", "--bits", type=int, default=1, choices=[1, 2, 3, 4], help="Bits per channel/sample")
    hf.add_argument("-p", "--password", help="Password to encrypt the payload (AES-256-GCM)")
    hf.add_argument("--ask-password", action="store_true", help="Prompt for a password interactively")
    hf.set_defaults(func=cmd_hide_file)

    ex = sub.add_parser("extract", help="Extract a hidden payload from a stego file")
    ex.add_argument("stego", help="Stego carrier file to extract from")
    ex.add_argument("-o", "--output", help="Where to save extracted output (file path)")
    ex.add_argument("-p", "--password", help="Password, if the payload is encrypted")
    ex.add_argument("--ask-password", action="store_true", help="Prompt for a password interactively")
    ex.set_defaults(func=cmd_extract)

    cap = sub.add_parser("capacity", help="Show how many bytes can be hidden in a carrier")
    cap.add_argument("carrier", help="Carrier file (png/bmp/wav)")
    cap.set_defaults(func=cmd_capacity)

    an = sub.add_parser("analyze", help="Run a basic LSB steganalysis heuristic on an image")
    an.add_argument("image", help="Image file to analyze")
    an.set_defaults(func=cmd_analyze)

    mn = sub.add_parser("menu", help="Launch an interactive text menu")
    mn.set_defaults(func=cmd_menu)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        cmd_menu(args)
        return
    args.func(args)


if __name__ == "__main__":
    main()
