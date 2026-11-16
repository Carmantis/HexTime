"""Response models for reports."""

from pydantic import BaseModel, ConfigDict

from app.services.reports import GroupBy


class ReportGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    total_seconds: int
    billable_seconds: int
    #: Integer cents, rounded once from the unrounded group total.
    billable_amount_cents: int
    entry_count: int


class ReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_by: GroupBy
    time_zone: str
    currency: str
    groups: list[ReportGroup]
    total_seconds: int
    billable_seconds: int
    billable_amount_cents: int
    entry_count: int
    #: Display names by key, in a by-user summary.
    labels: dict[str, str] = {}
