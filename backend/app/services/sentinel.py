"""The "not given" sentinel shared by the update services.

A partial update has to tell three things apart: a field the caller did not
mention, a field set to a value, and a field explicitly set to None. ``None``
alone cannot express that, so the "not mentioned" case needs a value of its
own.

A one-member enum is used rather than ``object()`` because an enum member has
a real type: ``str | Unset | None`` stays a precise annotation, while
``str | None | object`` collapses to ``object`` and says nothing.
"""

from enum import Enum


class Unset(Enum):
    """The type of :data:`UNSET`. One member, used only for identity."""

    TOKEN = 0


#: "The caller did not mention this field", as opposed to "set it to None".
UNSET = Unset.TOKEN
