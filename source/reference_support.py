"""Describe proximity to photograph-model input reference colors.

This is a count of input colors, not a confidence or print-accuracy estimate.
The reporting thresholds do not change the fitted model or its configurable
local correction radius (26 Delta E 76 in the default calibration).
"""
import numpy as np
from color_model import rgb_to_lab


def reference_support(model, rgb):
    """Return photograph-reference proximity for sRGB ``(..., 3)`` values.

    A single RGB triplet is one sample. Neutral/low-chroma samples have D65
    Lab C* <= 16 and are counted separately. Among chromatic samples, the
    nearest enabled source reference determines mutually exclusive groups:
    extrapolated d >= model.radius, near d <= 12 AND d < model.radius, and
    transition d > 12 AND d < model.radius. The extrapolation boundary takes
    precedence even when a custom calibration radius is less than 12.

    ``*_samples`` are integer counts. The three ``*_percent`` fields use
    ``chromatic_samples`` as denominator, round to two decimals, and are None
    when that denominator is zero. No-reference models therefore classify
    every chromatic sample as extrapolated, without labeling neutral samples
    as validated. Callers apply this only to the photograph-model input path.
    """
    values = np.asarray(rgb, dtype=float)
    if values.ndim < 1 or values.shape[-1] != 3:
        raise ValueError('Reference support requires RGB triplets.')
    if not np.isfinite(values).all() or ((values < 0) | (values > 255)).any():
        raise ValueError('Reference support RGB values must be finite and within 0..255.')
    values = values.reshape(-1, 3)
    radius = float(getattr(model, 'radius', 26))
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError('Reference support radius must be finite and positive.')
    chromatic_mask = np.linalg.norm(rgb_to_lab(values)[:, 1:], axis=1) > 16
    chromatic = values[chromatic_mask]
    counts = {'near': 0, 'transition': 0, 'extrapolated': 0}
    # Bound the temporary sample-by-reference distance array for image callers.
    for start in range(0, len(chromatic), 32768):
        batch = chromatic[start:start + 32768]
        distance = np.asarray(model.nearest(batch))
        if hasattr(model, 'anchors') and not model.anchors:
            distance = np.full(len(batch), np.inf)
        local = distance < radius
        counts['near'] += int(((distance <= 12) & local).sum())
        counts['transition'] += int(((distance > 12) & local).sum())
        counts['extrapolated'] += int((~local).sum())
    total = len(values)
    colored = len(chromatic)
    result = {
        'total_samples': total,
        'neutral_samples': total - colored,
        'chromatic_samples': colored,
        'percentage_denominator': 'chromatic_samples',
        'neutral_chroma_max': 16.0,
        'near_delta_e76_max': 12.0,
        'extrapolated_delta_e76_min': radius,
        'near_requires_local_support': True,
        'metric': 'Delta E 76, sRGB-derived D65 Lab',
        'meaning': 'Proximity of input colors to photograph references; not prediction accuracy. Extrapolation starts at the active model radius.',
    }
    for name, count in counts.items():
        result[name + '_samples'] = count
        result[name + '_percent'] = round(count * 100 / colored, 2) if colored else None
    return result
