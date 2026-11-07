"""Command line: turn any link into a QR code.

    python cli.py https://github.com/itadimaigal -o github.png
    python cli.py https://example.com --show
"""
import argparse
import sys
from urllib.parse import urlparse

import qrgen


def check_link(text):
    """Accept http/https links, and add https:// when the scheme is missing."""
    if "://" not in text:
        text = "https://" + text
    parts = urlparse(text)
    if parts.scheme not in ("http", "https") or "." not in parts.netloc or " " in text:
        raise argparse.ArgumentTypeError(f"not a web link: {text}")
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make a QR code for any web link.")
    parser.add_argument("link", type=check_link, help="the web link, e.g. https://example.com")
    parser.add_argument("-o", "--output", help="file to write: .png or .svg")
    parser.add_argument("--ec", choices=list("LMQH"), default="M", help="error correction level (default M)")
    parser.add_argument("--scale", type=int, default=10, help="pixels per module (default 10)")
    parser.add_argument("--border", type=int, default=4, help="quiet zone in modules (default 4)")
    parser.add_argument("--show", action="store_true", help="print the QR code in the terminal")
    args = parser.parse_args(argv)

    qr = qrgen.make_qr(args.link, ec=args.ec)
    print(f"{args.link}  ->  {qr}")
    if args.show or not args.output:
        print(qrgen.to_text(qr))
    if args.output:
        qrgen.save(qr, args.output, scale=args.scale, border=args.border)
        print(f"saved {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
