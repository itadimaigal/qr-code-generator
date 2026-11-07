"""qrgen: a QR code generator written from scratch, in pure Python.

Turns any text or web link into a QR code (byte mode, versions 1-10,
error correction L/M/Q/H) and saves it as PNG, SVG or terminal art.
No third-party packages needed.
"""
import struct
import zlib

# ---- Step 1: capacity tables ------------------------------------------------
# For each version and error-correction level:
# (EC codewords per block, blocks in group 1, data codewords each, blocks in group 2, data codewords each)
EC_TABLE = {
    1:  {"L": (7, 1, 19, 0, 0),    "M": (10, 1, 16, 0, 0),  "Q": (13, 1, 13, 0, 0),  "H": (17, 1, 9, 0, 0)},
    2:  {"L": (10, 1, 34, 0, 0),   "M": (16, 1, 28, 0, 0),  "Q": (22, 1, 22, 0, 0),  "H": (28, 1, 16, 0, 0)},
    3:  {"L": (15, 1, 55, 0, 0),   "M": (26, 1, 44, 0, 0),  "Q": (18, 2, 17, 0, 0),  "H": (22, 2, 13, 0, 0)},
    4:  {"L": (20, 1, 80, 0, 0),   "M": (18, 2, 32, 0, 0),  "Q": (26, 2, 24, 0, 0),  "H": (16, 4, 9, 0, 0)},
    5:  {"L": (26, 1, 108, 0, 0),  "M": (24, 2, 43, 0, 0),  "Q": (18, 2, 15, 2, 16), "H": (22, 2, 11, 2, 12)},
    6:  {"L": (18, 2, 68, 0, 0),   "M": (16, 4, 27, 0, 0),  "Q": (24, 4, 19, 0, 0),  "H": (28, 4, 15, 0, 0)},
    7:  {"L": (20, 2, 78, 0, 0),   "M": (18, 4, 31, 0, 0),  "Q": (18, 2, 14, 4, 15), "H": (26, 4, 13, 1, 14)},
    8:  {"L": (24, 2, 97, 0, 0),   "M": (22, 2, 38, 2, 39), "Q": (22, 4, 18, 2, 19), "H": (26, 4, 14, 2, 15)},
    9:  {"L": (30, 2, 116, 0, 0),  "M": (22, 3, 36, 2, 37), "Q": (20, 4, 16, 4, 17), "H": (24, 4, 12, 4, 13)},
    10: {"L": (18, 2, 68, 2, 69),  "M": (26, 4, 43, 1, 44), "Q": (24, 6, 19, 2, 20), "H": (28, 6, 15, 2, 16)},
}
ALIGNMENT = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
             7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
EC_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}


def data_capacity(version, ec):
    _, b1, d1, b2, d2 = EC_TABLE[version][ec]
    return b1 * d1 + b2 * d2


def choose_version(data, ec):
    """Smallest version whose data codewords fit: 4-bit mode + length + the bytes."""
    for version in range(1, 11):
        length_bits = 8 if version <= 9 else 16
        needed_bits = 4 + length_bits + 8 * len(data)
        if needed_bits <= data_capacity(version, ec) * 8:
            return version
    raise ValueError(f"Too long: {len(data)} bytes does not fit in version 10-{ec}")


# ---- Step 2: turn the text into data codewords --------------------------------
def encode_data(data, version, ec):
    bits = []

    def put(value, length):
        bits.extend((value >> i) & 1 for i in reversed(range(length)))

    put(0b0100, 4)                                  # mode indicator: byte mode
    put(len(data), 8 if version <= 9 else 16)       # character count
    for byte in data:
        put(byte, 8)

    capacity = data_capacity(version, ec) * 8
    put(0, min(4, capacity - len(bits)))            # terminator: up to four zeros
    while len(bits) % 8:                            # pad to a whole byte
        bits.append(0)
    codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    i = 0
    while len(codewords) < capacity // 8:          # fill the rest with the standard pad bytes
        codewords.append((0xEC, 0x11)[i % 2])
        i += 1
    return codewords


# ---- Step 3: Reed-Solomon error correction ----------------------------------
EXP = [0] * 512                                     # GF(256) anti-log table
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D                                 # the QR code polynomial x^8+x^4+x^3+x^2+1
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def rs_generator(degree):
    """(x - a^0)(x - a^1)...(x - a^(degree-1))"""
    poly = [1]
    for i in range(degree):
        poly = [a ^ gf_mul(b, EXP[i]) for a, b in zip(poly + [0], [0] + poly)]
    return poly


def rs_remainder(data, degree):
    """The EC codewords: remainder of data * x^degree divided by the generator."""
    gen = rs_generator(degree)
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(degree):
            rem[i] ^= gf_mul(gen[i + 1], factor)
    return rem


# ---- Step 4: split into blocks and interleave ----------------------------------
def add_error_correction(codewords, version, ec):
    ec_len, b1, d1, b2, d2 = EC_TABLE[version][ec]
    blocks, pos = [], 0
    for size in [d1] * b1 + [d2] * b2:
        blocks.append(codewords[pos:pos + size])
        pos += size
    ec_blocks = [rs_remainder(block, ec_len) for block in blocks]

    result = []
    for i in range(max(len(b) for b in blocks)):    # data: first byte of every block, then the second...
        result += [b[i] for b in blocks if i < len(b)]
    for i in range(ec_len):                         # then the EC bytes, the same way
        result += [b[i] for b in ec_blocks]
    return result


# ---- Step 5: draw the fixed patterns --------------------------------------------
def make_matrix(version):
    size = 17 + 4 * version
    grid = [[None] * size for _ in range(size)]     # None = not yet decided
    reserved = [[False] * size for _ in range(size)]

    def set_module(r, c, dark, reserve=True):
        grid[r][c] = dark
        reserved[r][c] = reserve

    # finder patterns (the three big squares) with their white separators
    for top, left in [(0, 0), (0, size - 7), (size - 7, 0)]:
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = top + r, left + c
                if 0 <= rr < size and 0 <= cc < size:
                    ring = max(abs(r - 3), abs(c - 3))
                    set_module(rr, cc, ring in (0, 1, 3))

    # timing patterns: alternating dark and light between the finders
    for i in range(8, size - 8):
        set_module(6, i, i % 2 == 0)
        set_module(i, 6, i % 2 == 0)

    # alignment patterns (version 2 and up)
    positions = ALIGNMENT[version]
    first, last = 6, size - 7
    for r in positions:
        for c in positions:
            if (r, c) in [(first, first), (first, last), (last, first)]:
                continue                            # these three would overlap a finder
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    set_module(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)

    # reserve space for format and version information, then the dark module
    for i in range(9):
        for r, c in [(8, i), (i, 8)]:
            if not reserved[r][c]:
                set_module(r, c, False)
    for i in range(8):
        set_module(8, size - 1 - i, False)
        set_module(size - 1 - i, 8, False)
    if version >= 7:
        for i in range(6):
            for j in range(3):
                set_module(i, size - 11 + j, False)
                set_module(size - 11 + j, i, False)
    set_module(size - 8, 8, True)
    return grid, reserved


# ---- Step 6: place the data in a zigzag ------------------------------------------
def place_data(grid, reserved, codewords):
    size = len(grid)
    bits = [(byte >> (7 - i)) & 1 for byte in codewords for i in range(8)]
    index = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:                                # skip the vertical timing pattern
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (col, col - 1):
                if not reserved[r][c]:
                    grid[r][c] = bool(bits[index]) if index < len(bits) else False
                    index += 1
        upward = not upward
        col -= 2


# ---- Step 7: masks, penalty score, format and version information ---------------
MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def bch(value, poly, data_bits, total_bits):
    """Append BCH error-correction bits (used for format and version info)."""
    rem = value << (total_bits - data_bits)
    for i in reversed(range(total_bits - data_bits, total_bits)):
        if rem >> i & 1:
            rem ^= poly << (i - (total_bits - data_bits))
    return (value << (total_bits - data_bits)) | rem


def draw_format(grid, ec, mask):
    size = len(grid)
    bits = bch(EC_BITS[ec] << 3 | mask, 0b10100110111, 5, 15) ^ 0b101010000010010
    bit = lambda i: bool(bits >> i & 1)
    for i in range(6):                              # first copy, around the top-left finder
        grid[i][8] = bit(i)
    grid[7][8] = bit(6)
    grid[8][8] = bit(7)
    grid[8][7] = bit(8)
    for i in range(9, 15):
        grid[8][14 - i] = bit(i)
    for i in range(8):                              # second copy, split between the other finders
        grid[8][size - 1 - i] = bit(i)
    for i in range(8, 15):
        grid[size - 15 + i][8] = bit(i)


def draw_version(grid, version):
    if version < 7:
        return
    size = len(grid)
    bits = bch(version, 0b1111100100101, 6, 18)
    for i in range(18):
        dark = bool(bits >> i & 1)
        grid[i // 3][size - 11 + i % 3] = dark
        grid[size - 11 + i % 3][i // 3] = dark


def penalty(grid):
    size = len(grid)
    score = 0
    lines = grid + [list(col) for col in zip(*grid)]
    for line in lines:                              # rule 1: five or more in a row
        run = 1
        for a, b in zip(line, line[1:]):
            if a == b:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    for r in range(size - 1):                       # rule 2: 2x2 blocks of one color
        for c in range(size - 1):
            if grid[r][c] == grid[r][c + 1] == grid[r + 1][c] == grid[r + 1][c + 1]:
                score += 3
    pattern = [True, False, True, True, True, False, True]
    for line in lines:                              # rule 3: looks like a finder pattern
        for i in range(size - 10):
            window = line[i:i + 11]
            if window[:7] == pattern and not any(window[7:]) or window[4:] == pattern and not any(window[:4]):
                score += 40
    dark = sum(map(sum, grid))                      # rule 4: balance of dark and light
    score += abs(dark * 100 // (size * size) - 50) // 5 * 10
    return score


# ---- Step 8: put it all together ------------------------------------------------
class QRCode:
    def __init__(self, modules, version, ec, mask):
        self.modules = modules                      # list of rows, True = dark
        self.version = version
        self.ec = ec
        self.mask = mask
        self.size = len(modules)

    def __repr__(self):
        return f"<QRCode version={self.version} ec={self.ec} mask={self.mask} size={self.size}x{self.size}>"


def make_qr(text, ec="M", mask=None):
    data = text.encode("utf-8")
    version = choose_version(data, ec)
    codewords = add_error_correction(encode_data(data, version, ec), version, ec)
    grid, reserved = make_matrix(version)
    place_data(grid, reserved, codewords)

    best = None
    for m in ([mask] if mask is not None else range(8)):
        candidate = [row[:] for row in grid]
        for r in range(len(grid)):
            for c in range(len(grid)):
                if not reserved[r][c] and MASKS[m](r, c):
                    candidate[r][c] = not candidate[r][c]
        draw_format(candidate, ec, m)
        draw_version(candidate, version)
        score = penalty(candidate)
        if best is None or score < best[0]:
            best = (score, m, candidate)
    return QRCode(best[2], version, ec, best[1])


# ---- Step 9: output: terminal, SVG and PNG --------------------------------------
def to_text(qr, border=2):
    """Two rows per line with half-block characters, so it looks square in a terminal."""
    size = qr.size + 2 * border
    dark = lambda r, c: 0 <= r - border < qr.size and 0 <= c - border < qr.size and qr.modules[r - border][c - border]
    lines = []
    for r in range(0, size, 2):
        line = ""
        for c in range(size):
            top, bottom = dark(r, c), dark(r + 1, c)
            line += {(False, False): "\u2588", (True, True): " ", (True, False): "\u2584", (False, True): "\u2580"}[(top, bottom)]
        lines.append(line)
    return "\n".join(lines)


def to_svg(qr, scale=10, border=4, dark="#000000", light="#ffffff"):
    size = (qr.size + 2 * border) * scale
    path = "".join(f"M{(c + border) * scale},{(r + border) * scale}h{scale}v{scale}h-{scale}z"
                   for r, row in enumerate(qr.modules) for c, on in enumerate(row) if on)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<rect width="100%" height="100%" fill="{light}"/><path d="{path}" fill="{dark}"/></svg>')


def to_png(qr, scale=10, border=4):
    """A black and white PNG written with nothing but zlib and struct."""
    size = (qr.size + 2 * border) * scale
    rows = []
    for y in range(size):
        r = y // scale - border
        row = bytearray([0])                        # filter type 0 for each scanline
        for x in range(size):
            c = x // scale - border
            on = 0 <= r < qr.size and 0 <= c < qr.size and qr.modules[r][c]
            row.append(0 if on else 255)
        rows.append(bytes(row))

    def chunk(kind, payload):
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)   # 8-bit grayscale
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def save(qr, filename, **options):
    if filename.lower().endswith(".svg"):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(to_svg(qr, **options))
    else:
        with open(filename, "wb") as f:
            f.write(to_png(qr, **options))
