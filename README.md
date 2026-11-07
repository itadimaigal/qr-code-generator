# QR Code Generator from scratch, in pure Python

This is the companion code for the **itadimaigal · Architect Talks** hands-on video *Build a QR Code Generator from Scratch*, presented by Professor SK.

It turns any web link into a QR code. Every step is written by hand in about 350 lines, with no QR library:

* encoding the bytes;
* Reed-Solomon error correction;
* the fixed patterns;
* the zigzag data placement;
* the masks and the format bits.

It writes PNG, SVG or terminal output. Then it adds a command line tool and a small web page on top.

## Files

| File | What it is |
|---|---|
| `qrgen.py` | The QR encoder, in nine steps. It uses only the standard library. |
| `cli.py` | Command line: `python cli.py <link> -o file.png` |
| `app.py` + `templates/index.html` | A Flask page: paste a link, see the QR code, download the PNG |
| `tests/test_qrgen.py` | Unit tests. With OpenCV installed, it also decodes every version and error-correction level. |
| `examples/` | Real outputs: PNG, SVG, terminal art and a screenshot of the web page |

## Quick start

```bash
python cli.py https://github.com/itadimaigal --show          # print it in the terminal
python cli.py https://github.com/itadimaigal -o github.png   # PNG
python cli.py youtube.com/@itadimaigal -o yt.svg --ec H      # SVG, highest error correction

pip install flask
python app.py                                                # open http://127.0.0.1:5000

pip install opencv-python numpy
python -m unittest discover tests -v
```

Use it from your own code:

```python
import qrgen
qr = qrgen.make_qr("https://github.com/itadimaigal", ec="Q")
print(qr)                      # <QRCode version=3 ec=Q mask=3 size=29x29>
qrgen.save(qr, "github.png", scale=12)
```

## The nine steps in qrgen.py

1. **Capacity tables:** pick the smallest version, from 21×21 up to 57×57, that fits the data.
2. **Data codewords:** the mode, the length, the bytes, a terminator, then pad bytes `0xEC 0x11`.
3. **Reed-Solomon:** arithmetic in GF(256). The EC bytes are the remainder of a polynomial division.
4. **Blocks:** split the data into blocks, add EC to each block, then interleave them.
5. **Fixed patterns:** the finder patterns, timing patterns, alignment patterns and the dark module.
6. **Zigzag:** place the bits two columns at a time, going up and down.
7. **Masks and format:** try all 8 masks, score each with the 4 penalty rules, and write the format bits (BCH code).
8. **`make_qr`:** connect steps 1 to 7 and keep the best mask.
9. **Output:** terminal half-blocks, SVG paths, and a PNG written with `zlib` and `struct`.

## Limits

These limits are on purpose, to keep the code readable:

* **Byte mode only.** Numeric, alphanumeric and kanji modes would make some codes smaller.
* **Versions 1 to 10.** That is up to 271 bytes at level L and 119 bytes at level H. That is plenty for links. Longer text raises a clear error.

For production work, a mature library such as `segno` or `qrcode` covers every version and mode.

## Good habits for QR codes

* **Quiet zone:** keep a white border of 4 modules around the code.
* **Contrast:** use dark modules on a light background. Don't invert the colors.
* **Error correction:** use level M for screens. Use Q or H for print, stickers, or a logo placed over the middle.
* **Test before you print:** scan it with two different phones.
* **Safety:** a QR code is a link you can't read. Only scan codes from sources you trust, and check the URL preview before you open it. Phishing with QR codes is called "quishing".

Made for the itadimaigal YouTube channel. Use, change and share freely.
