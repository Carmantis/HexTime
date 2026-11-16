"""Charts for the PDF reports, drawn with ReportLab's own graphics.

The bars are plain rectangles rather than ReportLab's chart widgets: a "hours
by project" chart is a few labelled bars, and drawing them directly keeps the
layout, fonts and axis under our control. The axis follows the same rule as
the Reports view (frontend/src/lib/chart.ts) so paper and screen tick alike.
"""

import math
from dataclasses import dataclass

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.reports.formatting import format_duration

MINUTE = 60
HOUR = 3600

#: The same steps as HOUR_STEPS in frontend/src/lib/chart.ts.
HOUR_STEPS = (
    15 * MINUTE,
    30 * MINUTE,
    HOUR,
    2 * HOUR,
    4 * HOUR,
    5 * HOUR,
    10 * HOUR,
    20 * HOUR,
    25 * HOUR,
    50 * HOUR,
    100 * HOUR,
    200 * HOUR,
    250 * HOUR,
    500 * HOUR,
)

#: The project swatches (frontend/src/lib/palette.ts), for bars without a
#: colour of their own, such as tasks.
SWATCHES = (
    "#4A90D9",
    "#E74C3C",
    "#2ECC71",
    "#F39C12",
    "#9B59B6",
    "#1ABC9C",
    "#E67E22",
    "#34495E",
)


def hour_axis(max_seconds: float, max_ticks: int) -> tuple[int, int]:
    """(interval, max) for an axis in seconds that ticks on whole steps.

    A port of hourAxis() in the frontend; the tests check the same cases.
    """
    top = max(max_seconds, 1)
    for step in HOUR_STEPS:
        if math.ceil(top / step) <= max_ticks:
            return step, math.ceil(top / step) * step
    largest = HOUR_STEPS[-1]
    step = math.ceil(top / max_ticks / largest) * largest
    return step, math.ceil(top / step) * step


@dataclass(frozen=True)
class Bar:
    label: str
    seconds: int
    color: str | None
    #: Drawn in the muted colour: "no project", "no task".
    muted: bool = False


@dataclass(frozen=True)
class ChartStyle:
    font: str
    text: colors.Color
    muted: colors.Color
    grid: colors.Color
    #: Bars without a colour of their own, and the "none" bar.
    neutral: colors.Color


ELLIPSIS = "\u2026"

ROW_HEIGHT = 18
BAR_HEIGHT = 10
AXIS_HEIGHT = 16
FONT_SIZE = 8
LABEL_GAP = 8
#: Room after the longest bar for its "16 h 30 min" label.
VALUE_ROOM = 60


def _fit(text: str, font: str, width: float) -> str:
    """Shorten a label with an ellipsis until it fits the label column."""
    if stringWidth(text, font, FONT_SIZE) <= width:
        return text
    while text and stringWidth(f"{text}{ELLIPSIS}", font, FONT_SIZE) > width:
        text = text[:-1]
    return f"{text.rstrip()}{ELLIPSIS}"


def bar_chart(bars: list[Bar], *, width: float, locale: str, style: ChartStyle) -> Drawing:
    """Horizontal bars, biggest first, with an hour axis along the bottom."""
    rows = [bar for bar in bars if bar.seconds > 0]
    height = len(rows) * ROW_HEIGHT + AXIS_HEIGHT
    drawing = Drawing(width, height)
    if not rows:
        return drawing

    widest = max(stringWidth(bar.label, style.font, FONT_SIZE) for bar in rows)
    label_width = min(widest, width * 0.3)
    left = label_width + LABEL_GAP
    plot_width = width - left - VALUE_ROOM

    interval, axis_max = hour_axis(max(bar.seconds for bar in rows), 5)
    scale = plot_width / axis_max

    # Grid lines and hour labels; the bars are drawn over them.
    for tick in range(0, axis_max + 1, interval):
        x = left + tick * scale
        drawing.add(Line(x, AXIS_HEIGHT, x, height, strokeColor=style.grid, strokeWidth=0.4))
        drawing.add(
            String(
                x,
                AXIS_HEIGHT - 11,
                format_duration(tick, locale),
                fontName=style.font,
                fontSize=FONT_SIZE - 1,
                fillColor=style.muted,
                textAnchor="middle",
            )
        )

    for index, bar in enumerate(rows):
        # Top row first: y counts up from the bottom of the drawing.
        row_bottom = height - (index + 1) * ROW_HEIGHT
        bar_y = row_bottom + (ROW_HEIGHT - BAR_HEIGHT) / 2
        text_y = bar_y + 2
        bar_width = bar.seconds * scale

        if bar.muted:
            fill = style.neutral
        elif bar.color:
            fill = colors.HexColor(bar.color)
        else:
            fill = colors.HexColor(SWATCHES[index % len(SWATCHES)])

        drawing.add(
            String(
                0,
                text_y,
                _fit(bar.label, style.font, label_width),
                fontName=style.font,
                fontSize=FONT_SIZE,
                fillColor=style.muted if bar.muted else style.text,
            )
        )
        drawing.add(
            Rect(left, bar_y, bar_width, BAR_HEIGHT, fillColor=fill, strokeColor=None, rx=1.5)
        )
        drawing.add(
            String(
                left + bar_width + 4,
                text_y,
                format_duration(bar.seconds, locale),
                fontName=style.font,
                fontSize=FONT_SIZE,
                fillColor=style.muted,
            )
        )

    return drawing
