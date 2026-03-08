from __future__ import annotations

import math
from typing import Tuple

Rgb = Tuple[int, int, int]
Oklab = Tuple[float, float, float]
Oklch = Tuple[float, float, float]


def _srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(channel: float) -> float:
    if channel <= 0.0031308:
        return channel * 12.92
    return 1.055 * (channel ** (1 / 2.4)) - 0.055


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rgb_to_oklab(rgb: Rgb) -> Oklab:
    r = _srgb_to_linear(rgb[0] / 255.0)
    g = _srgb_to_linear(rgb[1] / 255.0)
    b = _srgb_to_linear(rgb[2] / 255.0)

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = math.copysign(abs(l) ** (1 / 3), l)
    m_ = math.copysign(abs(m) ** (1 / 3), m)
    s_ = math.copysign(abs(s) ** (1 / 3), s)

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(oklab: Oklab) -> Rgb:
    l, a, b = oklab

    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b

    l3 = l_ * l_ * l_
    m3 = m_ * m_ * m_
    s3 = s_ * s_ * s_

    r_linear = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    g_linear = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    b_linear = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3

    r = clamp(_linear_to_srgb(r_linear), 0.0, 1.0)
    g = clamp(_linear_to_srgb(g_linear), 0.0, 1.0)
    b = clamp(_linear_to_srgb(b_linear), 0.0, 1.0)
    return (round(r * 255), round(g * 255), round(b * 255))


def oklab_to_oklch(oklab: Oklab) -> Oklch:
    l, a, b = oklab
    chroma = math.sqrt(a * a + b * b)
    hue = math.degrees(math.atan2(b, a)) % 360.0
    return (l, chroma, hue)


def oklch_to_oklab(oklch: Oklch) -> Oklab:
    l, chroma, hue = oklch
    hue_radians = math.radians(hue)
    a = chroma * math.cos(hue_radians)
    b = chroma * math.sin(hue_radians)
    return (l, a, b)


def rgb_to_oklch(rgb: Rgb) -> Oklch:
    return oklab_to_oklch(rgb_to_oklab(rgb))


def oklch_to_rgb(oklch: Oklch) -> Rgb:
    return oklab_to_rgb(oklch_to_oklab(oklch))


def rgb_to_hex(rgb: Rgb) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def hex_to_rgb(value: str) -> Rgb:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError("hex color must be 6 characters")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
