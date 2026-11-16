"""Drawing reports as PDF with ReportLab.

This module only lays out values it is given; it never adds anything up.
Inter is embedded so "ä" and "ö" print the same on every machine, and the
colours are the light theme's (tokens.css), because paper is white.
"""

from dataclasses import dataclass
from functools import cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import Flowable

from app.core.i18n import Translate, translator
from app.reports.charts import Bar, ChartStyle, bar_chart
from app.reports.data import (
    EntryLine,
    GroupLine,
    PeriodReport,
    ProjectReport,
    ReportHeader,
    TeamReport,
    Totals,
)
from app.reports.formatting import (
    format_date,
    format_date_range,
    format_duration,
    format_money,
    format_time,
    format_time_range,
)

FONT_DIR = Path(__file__).parent / "fonts"
FONT = "Inter"
FONT_BOLD = "Inter-Bold"

# The light theme from frontend/src/lib/theme/tokens.css.
TEXT = colors.HexColor("#212529")
MUTED = colors.HexColor("#868e96")
BORDER = colors.HexColor("#dee2e6")
BORDER_LIGHT = colors.HexColor("#e9ecef")
SURFACE = colors.HexColor("#f8f9fa")

MARGIN = 18 * mm
PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


@cache
def _register_fonts() -> None:
    """Teach ReportLab the Inter files once per process."""
    pdfmetrics.registerFont(TTFont(FONT, FONT_DIR / "Inter-Regular.ttf"))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, FONT_DIR / "Inter-Bold.ttf"))


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT, fontSize=9, leading=12, textColor=TEXT)
    return {
        "title": ParagraphStyle("title", base, fontName=FONT_BOLD, fontSize=18, leading=22),
        "meta": ParagraphStyle("meta", base, textColor=MUTED),
        "h2": ParagraphStyle(
            "h2", base, fontName=FONT_BOLD, fontSize=11, leading=14, spaceBefore=6, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "h3", base, fontName=FONT_BOLD, fontSize=9.5, leading=12, spaceBefore=4, spaceAfter=4
        ),
        "cell": base,
        "cell_muted": ParagraphStyle("cell_muted", base, textColor=MUTED),
        "label": ParagraphStyle("label", base, fontSize=8, textColor=MUTED),
        "value": ParagraphStyle("value", base, fontName=FONT_BOLD, fontSize=14, leading=18),
        "note": ParagraphStyle("note", base, fontSize=7.5, leading=10, textColor=MUTED),
        "head": ParagraphStyle("head", base, fontSize=8, textColor=MUTED),
        "head_right": ParagraphStyle(
            "head_right", base, fontSize=8, textColor=MUTED, alignment=TA_RIGHT
        ),
        "right": ParagraphStyle("right", base, alignment=TA_RIGHT),
    }


def _p(text: str | None, style: ParagraphStyle) -> Paragraph:
    """A paragraph from user text: escaped, because ReportLab reads markup."""
    return Paragraph(escape(text or ""), style)


def _table_style(*extra: tuple[object, ...]) -> TableStyle:
    """Rows separated by a hairline, a heavier line under the header."""
    return TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, BORDER),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, BORDER_LIGHT),
            *extra,
        ]
    )


@dataclass(frozen=True)
class _Context:
    """What every part of one document needs: its language and styles."""

    t: Translate
    locale: str
    s: dict[str, ParagraphStyle]
    currency: str

    def duration(self, seconds: int) -> str:
        return format_duration(seconds, self.locale)

    def money(self, cents: int) -> str:
        return format_money(cents, self.currency, self.locale)


def _context(locale: str, currency: str) -> _Context:
    _register_fonts()
    return _Context(t=translator(locale), locale=locale, s=_styles(), currency=currency)


def _summary(c: _Context, totals: Totals) -> Table:
    tiles = [
        (c.t("pdf.totalHours"), c.duration(totals.total_seconds)),
        (c.t("pdf.billableHours"), c.duration(totals.billable_seconds)),
        (c.t("pdf.billableAmount"), c.money(totals.billable_amount_cents)),
    ]
    table = Table(
        [[[_p(label, c.s["label"]), _p(value, c.s["value"])] for label, value in tiles]],
        colWidths=[CONTENT_WIDTH / 3] * 3,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LINEAFTER", (0, 0), (-2, -1), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _groups(c: _Context, lines: list[GroupLine], name_key: str, none_key: str) -> Table:
    """Hours by project or by task. Lines with a colour get a thin colour bar."""
    s = c.s
    rows: list[list[object]] = [
        [
            "",
            _p(c.t(name_key), s["head"]),
            _p(c.t("pdf.hours"), s["head_right"]),
            _p(c.t("pdf.billableHours"), s["head_right"]),
            _p(c.t("pdf.amount"), s["head_right"]),
        ]
    ]
    swatches = []
    for index, line in enumerate(lines, start=1):
        rows.append(
            [
                "",
                _p(line.name, s["cell"]) if line.name else _p(c.t(none_key), s["cell_muted"]),
                _p(c.duration(line.total_seconds), s["right"]),
                _p(c.duration(line.billable_seconds), s["right"]),
                _p(c.money(line.billable_amount_cents), s["right"]),
            ]
        )
        # The project colour as a thin bar, never a filled row (as in the UI).
        if line.color:
            swatches.append(("BACKGROUND", (0, index), (0, index), colors.HexColor(line.color)))

    widths = [0.43, 0.17, 0.2, 0.2]
    table = Table(
        rows,
        colWidths=[3, CONTENT_WIDTH * widths[0] - 3] + [CONTENT_WIDTH * w for w in widths[1:]],
        repeatRows=1,
    )
    table.setStyle(
        _table_style(
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 0),
            *swatches,
        )
    )
    return table


def _chart(c: _Context, lines: list[GroupLine], none_key: str) -> Flowable:
    """The same lines as the table under it, as bars."""
    bars = [
        Bar(
            label=line.name or c.t(none_key),
            seconds=line.total_seconds,
            color=line.color,
            muted=line.name is None,
        )
        for line in lines
    ]
    style = ChartStyle(font=FONT, text=TEXT, muted=MUTED, grid=BORDER_LIGHT, neutral=MUTED)
    return bar_chart(bars, width=CONTENT_WIDTH, locale=c.locale, style=style)


def _entries(c: _Context, entries: list[EntryLine], *, with_project: bool) -> Table:
    """The entry list. A project report drops the project from each row: it
    would say the same name on every line."""
    s = c.s
    where_head = f"{c.t('pdf.project')} / {c.t('pdf.task')}" if with_project else c.t("pdf.task")
    none_key = "pdf.noProject" if with_project else "pdf.noTask"
    rows: list[list[object]] = [
        [
            _p(c.t("pdf.date"), s["head"]),
            _p(c.t("pdf.time"), s["head"]),
            _p(where_head, s["head"]),
            _p(c.t("pdf.description"), s["head"]),
            _p(c.t("pdf.duration"), s["head_right"]),
            _p(c.t("pdf.amount"), s["head_right"]),
        ]
    ]
    for line in entries:
        parts = (line.project, line.task) if with_project else (line.task,)
        where = " / ".join(part for part in parts if part)
        rows.append(
            [
                _p(format_date(line.started_at.date(), c.locale), s["cell"]),
                _p(format_time_range(line.started_at, line.ended_at), s["cell"]),
                _p(where, s["cell"]) if where else _p(c.t(none_key), s["cell_muted"]),
                _p(line.description, s["cell"]),
                _p(c.duration(line.duration_seconds), s["right"]),
                _p(c.money(line.amount_cents) if line.amount_cents is not None else "", s["right"]),
            ]
        )

    widths = [0.12, 0.13, 0.22, 0.27, 0.12, 0.14]
    table = Table(rows, colWidths=[CONTENT_WIDTH * w for w in widths], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _entry_section(c: _Context, entries: list[EntryLine], *, with_project: bool) -> list[Flowable]:
    story: list[Flowable] = [
        _p(c.t("pdf.entries"), c.s["h2"]),
        _entries(c, entries, with_project=with_project),
    ]
    if any(line.amount_cents is not None for line in entries):
        story += [Spacer(1, 3 * mm), _p(c.t("pdf.roundingNote"), c.s["note"])]
    return story


def _footer(t: Translate) -> object:
    def draw(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 10 * mm, "HexTime")
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, t("pdf.page", n=doc.page))
        canvas.restoreState()

    return draw


def _document(
    c: _Context,
    title: str,
    header: ReportHeader,
    meta: list[str],
    body: list[Flowable],
    *,
    person_key: str = "pdf.person",
) -> bytes:
    """Title, the lines under it, then the body; the same frame for every report."""
    period = format_date_range(header.first_day, header.last_day, c.locale)
    generated = (
        f"{format_date(header.generated_at.date(), c.locale)} {format_time(header.generated_at)}"
    )
    lines = [
        *meta,
        f"{c.t('pdf.period')}: {period}",
        f"{c.t(person_key)}: {header.person}",
        f"{c.t('pdf.generated')}: {generated}",
    ]
    story: list[Flowable] = [
        _p(title, c.s["title"]),
        Spacer(1, 2 * mm),
        *[_p(line, c.s["meta"]) for line in lines],
        Spacer(1, 6 * mm),
        *body,
    ]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{title} {period}",
        author=header.person,
        creator="HexTime",
    )
    footer = _footer(c.t)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_period_pdf(report: PeriodReport, locale: str) -> bytes:
    """The period report as PDF bytes, in the given language."""
    c = _context(locale, report.totals.currency)
    meta = [f"{c.t('pdf.team')}: {report.team_name}"] if report.team_name else []
    body: list[Flowable] = [_summary(c, report.totals), Spacer(1, 6 * mm)]
    if not report.entries:
        body.append(_p(c.t("pdf.noEntries"), c.s["cell_muted"]))
    else:
        body += [
            _p(c.t("pdf.byProject"), c.s["h2"]),
            _chart(c, report.projects, "pdf.noProject"),
            Spacer(1, 4 * mm),
            _groups(c, report.projects, "pdf.project", "pdf.noProject"),
            Spacer(1, 6 * mm),
            *_entry_section(c, report.entries, with_project=True),
        ]
    if report.team_name:
        body += [Spacer(1, 3 * mm), _p(c.t("pdf.ownInTeamNote"), c.s["note"])]
    title = c.t("pdf.ownInTeamTitle") if report.team_name else c.t("pdf.periodTitle")
    return _document(c, title, report.header, meta, body)


def render_project_pdf(report: ProjectReport, locale: str) -> bytes:
    """One project's report as PDF bytes, in the given language."""
    c = _context(locale, report.totals.currency)
    project = report.project

    meta = [f"{c.t('pdf.project')}: {project.name}"]
    if project.client_name:
        meta.append(f"{c.t('pdf.client')}: {project.client_name}")
    if project.hourly_rate_cents is not None:
        rate = format_money(project.hourly_rate_cents, project.currency, locale)
        meta.append(f"{c.t('pdf.hourlyRate')}: {c.t('pdf.perHour', amount=rate)}")

    body: list[Flowable] = [_summary(c, report.totals), Spacer(1, 6 * mm)]
    if not report.entries:
        body.append(_p(c.t("pdf.noEntries"), c.s["cell_muted"]))
    else:
        body += [
            _p(c.t("pdf.byTask"), c.s["h2"]),
            _chart(c, report.tasks, "pdf.noTask"),
            Spacer(1, 4 * mm),
            _groups(c, report.tasks, "pdf.task", "pdf.noTask"),
            Spacer(1, 6 * mm),
            *_entry_section(c, report.entries, with_project=False),
        ]
    return _document(c, c.t("pdf.projectTitle"), report.header, meta, body)


def render_team_pdf(report: TeamReport, locale: str) -> bytes:
    """A team's report as PDF bytes: totals only, never single entries."""
    c = _context(locale, report.totals.currency)
    meta = [f"{c.t('pdf.team')}: {report.team_name}"]

    body: list[Flowable] = [_summary(c, report.totals), Spacer(1, 6 * mm)]
    if not report.projects:
        body.append(_p(c.t("pdf.noTeamHours"), c.s["cell_muted"]))
    else:
        body += [
            _p(c.t("pdf.byMember"), c.s["h2"]),
            _chart(c, report.members, "pdf.unknownMember"),
            Spacer(1, 4 * mm),
            _groups(c, report.members, "pdf.member", "pdf.unknownMember"),
            Spacer(1, 6 * mm),
            _p(c.t("pdf.byProject"), c.s["h2"]),
            _chart(c, report.projects, "pdf.noProject"),
            Spacer(1, 4 * mm),
            _groups(c, report.projects, "pdf.project", "pdf.noProject"),
            Spacer(1, 6 * mm),
            _p(c.t("pdf.membersByProject"), c.s["h2"]),
        ]
        for part in report.breakdown:
            body += [
                _p(part.project.name or c.t("pdf.noProject"), c.s["h3"]),
                _groups(c, part.members, "pdf.member", "pdf.unknownMember"),
                Spacer(1, 4 * mm),
            ]
        body.append(_p(c.t("pdf.teamNote"), c.s["note"]))
    return _document(
        c, c.t("pdf.teamTitle"), report.header, meta, body, person_key="pdf.exportedBy"
    )
