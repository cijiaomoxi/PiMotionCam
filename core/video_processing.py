"""Opt-in display/recording effects. Detection receives the clean transformed frame."""

from __future__ import annotations
import io
import math
import time
import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw, ImageFont

EFFECTS = (
    "none",
    "negative",
    "solarise",
    "sketch",
    "denoise",
    "emboss",
    "oilpaint",
    "hatch",
    "gpen",
    "pastel",
    "watercolour",
    "film",
    "blur",
    "saturation",
    "colourswap",
    "washedout",
    "posterise",
    "colourpoint",
    "colourbalance",
    "cartoon",
    "deinterlace1",
    "deinterlace2",
)


def image_effect(image, effect):
    if effect == "none":
        return image
    if effect == "negative":
        return ImageOps.invert(image)
    if effect == "solarise":
        return ImageOps.solarize(image, 128)
    if effect == "denoise":
        return image.filter(ImageFilter.MedianFilter(3))
    if effect == "emboss":
        return image.filter(ImageFilter.EMBOSS)
    if effect == "blur":
        return image.filter(ImageFilter.GaussianBlur(2))
    if effect in ("oilpaint", "watercolour"):
        return image.filter(ImageFilter.ModeFilter(5)).filter(ImageFilter.SMOOTH)
    if effect in ("pastel", "posterise", "cartoon"):
        return ImageOps.posterize(
            image.filter(ImageFilter.SMOOTH_MORE), 3 if effect == "posterise" else 4
        )
    if effect in ("sketch", "hatch", "gpen"):
        return ImageOps.invert(
            image.convert("L").filter(ImageFilter.FIND_EDGES)
        ).convert("RGB")
    if effect == "film":
        return ImageEnhance.Color(image).enhance(0.2)
    if effect == "saturation":
        return ImageEnhance.Color(image).enhance(2)
    if effect == "washedout":
        return ImageEnhance.Contrast(
            ImageEnhance.Brightness(image).enhance(1.2)
        ).enhance(0.5)
    if effect == "colourswap":
        r, g, b = image.split()
        return Image.merge("RGB", (b, r, g))
    if effect == "colourpoint":
        a = np.asarray(image).copy()
        gray = np.asarray(image.convert("L"))
        keep = a[:, :, 0].astype("i2") > a[:, :, 1].astype("i2") + 25
        a[~keep] = np.repeat(gray[:, :, None], 3, axis=2)[~keep]
        return Image.fromarray(a)
    if effect == "colourbalance":
        return ImageOps.autocontrast(image, cutoff=1)
    if effect in ("deinterlace1", "deinterlace2"):
        a = np.asarray(image)
        return Image.fromarray(a[int(effect[-1]) - 1 :: 2]).resize(
            image.size, Image.Resampling.BILINEAR
        )
    raise ValueError("Unknown software image effect")


class VideoProcessor:
    def __init__(self, config):
        self.config = config
        self._previous = None
        self._position = np.zeros(2, dtype=np.float64)
        self._smoothed = np.zeros(2, dtype=np.float64)
        self._fonts = {}

    def transform(self, jpeg):
        opts = self.config.get("camera", "processing", default={}) or {}
        crop = opts.get("crop", [0, 0, 1, 1])
        effect = opts.get("effect", "none")
        stabilize = opts.get("stabilize", False)
        if crop == [0, 0, 1, 1] and effect == "none" and not stabilize:
            self._previous = None
            self._position[:] = self._smoothed[:] = 0
            return jpeg
        with Image.open(io.BytesIO(jpeg)) as raw:
            im = raw.convert("RGB")
        size = im.size
        x, y, w, h = [float(v) for v in crop]
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x and 0 < h <= 1 - y):
            raise ValueError("Invalid normalized crop")
        if crop != [0, 0, 1, 1]:
            x0, y0 = int(x * size[0]), int(y * size[1])
            im = im.crop(
                (
                    x0,
                    y0,
                    max(x0 + 1, int((x + w) * size[0])),
                    max(y0 + 1, int((y + h) * size[1])),
                )
            ).resize(size, Image.Resampling.BILINEAR)
        if stabilize:
            small = np.asarray(im.convert("L").resize((160, 90)), dtype=np.float32)
            if self._previous is not None:
                a = np.fft.rfft2(self._previous)
                b = np.fft.rfft2(small)
                cross = a * np.conj(b)
                cross /= np.maximum(np.abs(cross), 1e-8)
                correlation = np.fft.irfft2(cross, s=small.shape)
                yy, xx = np.unravel_index(np.argmax(correlation), correlation.shape)
                dx = xx if xx <= 80 else xx - 160
                dy = yy if yy <= 45 else yy - 90
                # Reject large moves (scene cuts / deliberate camera movement).
                if abs(dx) <= 4 and abs(dy) <= 2:
                    self._position += (dx, dy)
                    self._smoothed += (self._position - self._smoothed) * 0.12
                    correction = np.clip(
                        self._position - self._smoothed, [-4, -2], [4, 2]
                    )
                    im = im.transform(
                        size,
                        Image.Transform.AFFINE,
                        (
                            1,
                            0,
                            -correction[0] * size[0] / 160,
                            0,
                            1,
                            -correction[1] * size[1] / 90,
                        ),
                        Image.Resampling.BILINEAR,
                    )
                else:
                    self._position[:] = self._smoothed[:] = 0
            self._previous = small
            # Trim the padded edge. No black strip enters detection or recording.
            im = im.crop(
                (
                    math.ceil(size[0] * 0.03),
                    math.ceil(size[1] * 0.03),
                    int(size[0] * 0.97),
                    int(size[1] * 0.97),
                )
            ).resize(size, Image.Resampling.BILINEAR)
        im = image_effect(im, effect)
        return self._encode(im)

    def _encode(self, im):
        out = io.BytesIO()
        im.save(
            out,
            "JPEG",
            quality=max(
                1, min(100, int(self.config.get("camera", "jpeg_quality", default=72)))
            ),
        )
        return out.getvalue()

    def annotate(self, jpeg, state):
        opts = self.config.get("web", "burn_in", default={}) or {}
        if not opts.get("enabled"):
            return jpeg
        with Image.open(io.BytesIO(jpeg)) as raw:
            im = raw.convert("RGB")
        draw = ImageDraw.Draw(im)
        size = max(10, min(64, int(opts.get("font_size", 18))))
        if size not in self._fonts:
            font = None
            for path in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/System/Library/Fonts/PingFang.ttc",
            ):
                try:
                    font = ImageFont.truetype(path, size)
                    break
                except OSError:
                    pass
            self._fonts[size] = font or ImageFont.load_default()
        text = time.strftime("%Y-%m-%d %H:%M:%S") if opts.get("timestamp", True) else ""
        custom = str(opts.get("text", ""))[:160]
        lines = [line for line in (text, custom) if line]
        if opts.get("frame_info"):
            det = state.get("detection", {}) or {}
            analysis = det.get("analysis", {})
            lines.append(
                "FPS %s | %s | %s"
                % (
                    state.get("fps", 0),
                    det.get("algorithm") or "-",
                    analysis.get("direction", "-"),
                )
            )
        text = "\n".join(lines)
        font = self._fonts[size]
        bounds = draw.multiline_textbbox((8, 8), text, font=font)
        if opts.get("background", True):
            draw.rectangle((3, 3, bounds[2] + 5, bounds[3] + 5), fill="black")
        draw.multiline_text((8, 8), text, font=font, fill="white")
        if opts.get("vu_meter"):
            length = int(
                im.width * 0.25 * max(0, min(1, float(state.get("audio_level", 0))))
            )
            draw.rectangle(
                (8, im.height - 18, 8 + int(im.width * 0.25), im.height - 8),
                fill="#222222",
            )
            draw.rectangle(
                (8, im.height - 18, 8 + length, im.height - 8), fill="#4ec99b"
            )
        return self._encode(im)
