"""The PDF bar chart and its hour axis."""

from reportlab.graphics.shapes import Rect, String
from reportlab.lib import colors

from app.reports.charts import Bar, ChartStyle, bar_chart, hour_axis
from app.reports.pdf import _register_fonts

HOUR = 3600
STYLE = ChartStyle(
    font="Inter",
    text=colors.black,
    muted=colors.grey,
    grid=colors.lightgrey,
    neutral=colors.grey,
)


# The same cases as hourAxis() in frontend/src/lib/chart.test.ts, so the
# PDF and the Reports view tick the same way.


def test_steps_in_whole_hours() -> None:
    assert hour_axis(16.5 * HOUR, 5) == (4 * HOUR, 20 * HOUR)


def test_quarter_hours_for_short_totals() -> None:
    assert hour_axis(40 * 60, 4) == (15 * 60, 45 * 60)


def test_ends_on_the_top_value_when_it_is_a_whole_step() -> None:
    assert hour_axis(8 * HOUR, 4) == (2 * HOUR, 8 * HOUR)


def test_an_axis_with_no_time() -> None:
    assert hour_axis(0, 4) == (15 * 60, 15 * 60)


def test_past_the_largest_step() -> None:
    interval, top = hour_axis(5000 * HOUR, 4)
    assert interval % (500 * HOUR) == 0
    assert top / interval <= 4


def chart(bars: list[Bar]):
    _register_fonts()
    return bar_chart(bars, width=400, locale="fi", style=STYLE)


def rects(drawing) -> list[Rect]:
    return [shape for shape in drawing.contents if isinstance(shape, Rect)]


def texts(drawing) -> list[str]:
    return [shape.text for shape in drawing.contents if isinstance(shape, String)]


def test_one_bar_per_row_with_time() -> None:
    drawing = chart(
        [Bar("Website", 2 * HOUR, "#4A90D9"), Bar("Empty", 0, None), Bar("Other", HOUR, None)]
    )

    bars = rects(drawing)
    assert len(bars) == 2
    # Bars are drawn to scale: twice the hours, twice the length.
    assert bars[0].width == 2 * bars[1].width
    assert "Empty" not in texts(drawing)


def test_bars_keep_their_colour_and_others_get_a_swatch() -> None:
    drawing = chart([Bar("Website", HOUR, "#2ECC71"), Bar("Design", HOUR, None)])

    first, second = rects(drawing)
    assert first.fillColor == colors.HexColor("#2ECC71")
    assert second.fillColor == colors.HexColor("#E74C3C")  # the second swatch


def test_the_none_bar_is_muted() -> None:
    drawing = chart([Bar("Ei projektia", HOUR, None, muted=True)])

    assert rects(drawing)[0].fillColor == STYLE.neutral


def test_labels_show_hours_and_axis_ticks() -> None:
    labels = texts(chart([Bar("Website", 16 * HOUR + 30 * 60, None)]))

    assert "16 t 30 min" in labels
    assert {"0 min", "4 t", "8 t", "12 t", "16 t", "20 t"} <= set(labels)


def test_a_long_label_is_shortened() -> None:
    labels = texts(chart([Bar("A" * 200, HOUR, None)]))

    assert any(label.endswith("…") and len(label) < 200 for label in labels)


def test_nothing_to_draw_gives_an_empty_drawing() -> None:
    assert rects(chart([Bar("Empty", 0, None)])) == []
