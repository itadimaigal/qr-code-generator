"""Run with:  python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import qrgen  # noqa: E402


class TestBuildingBlocks(unittest.TestCase):
    def test_capacity(self):
        self.assertEqual(qrgen.data_capacity(1, "M"), 16)
        self.assertEqual(qrgen.data_capacity(10, "H"), 122)

    def test_version_choice(self):
        self.assertEqual(qrgen.choose_version(b"a" * 14, "M"), 1)
        self.assertEqual(qrgen.choose_version(b"a" * 15, "M"), 2)

    def test_reed_solomon_known_value(self):
        # "HELLO WORLD" 1-M data codewords and their EC codewords, from the standard's worked example
        data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
        self.assertEqual(qrgen.rs_remainder(data, 10), [196, 35, 39, 119, 235, 215, 231, 226, 93, 23])

    def test_format_bits(self):
        # level M, mask 0 -> 101010000010010 in the spec table
        bits = qrgen.bch(qrgen.EC_BITS["M"] << 3 | 0, 0b10100110111, 5, 15) ^ 0b101010000010010
        self.assertEqual(format(bits, "015b"), "101010000010010")

    def test_sizes(self):
        for text, size in [("a", 21), ("https://github.com/itadimaigal", 29)]:
            self.assertEqual(qrgen.make_qr(text).size, size)


try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, "pip install opencv-python numpy to run the decode tests")
class TestDecode(unittest.TestCase):
    def decode(self, qr):
        png = qrgen.to_png(qr, scale=8)
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
        # OpenCV has two detectors; each one misses a few valid codes, so try both
        detectors = [cv2.QRCodeDetector()]
        if hasattr(cv2, "QRCodeDetectorAruco"):
            detectors.append(cv2.QRCodeDetectorAruco())
        for detector in detectors:
            text = detector.detectAndDecode(img)[0]
            if text:
                return text
        return ""

    def test_every_version_and_level(self):
        for ec in "LMQH":
            for version in range(1, 11):
                n = qrgen.data_capacity(version, ec) - (2 if version <= 9 else 3)
                text = ("qr" * 200)[:n]           # fills this version completely
                with self.subTest(ec=ec, version=version):
                    qr = qrgen.make_qr(text, ec)
                    self.assertEqual(qr.version, version)
                    self.assertEqual(self.decode(qr), text)

    def test_links_round_trip(self):
        for link in ["https://github.com/itadimaigal", "https://www.youtube.com/@itadimaigal",
                     "https://example.com/search?q=qr+code&lang=en", "https://ja.wikipedia.org/wiki/QRコード"]:
            for ec in "LMQH":
                with self.subTest(link=link, ec=ec):
                    self.assertEqual(self.decode(qrgen.make_qr(link, ec)), link)


if __name__ == "__main__":
    unittest.main()
