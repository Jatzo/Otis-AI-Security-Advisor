"""How the retrieved units are put in front of the model.

Header and body come from upstream text, which anyone can write. Every &, < and > in them is
escaped before the unit is placed, so a record cannot open or close an evidence block whatever
case or spacing it uses. The tags and the id attribute are the only markup in the message.
"""

import re

from advisor.retrieval.units import Unit

UNIT_ID = re.compile(r"[a-z]+:[A-Za-z0-9-]+")


def escape(text: str) -> str:
    """The ampersand goes first, so the entities written here are not escaped again."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_unit(unit: Unit) -> str:
    if not UNIT_ID.fullmatch(unit.unit_id):
        raise ValueError(f"The unit id {unit.unit_id!r} cannot go in an evidence tag.")
    inside = escape(f"{unit.header}\n{unit.body}".strip())
    return f'<evidence id="{unit.unit_id}">\n{inside}\n</evidence>'


def user_message(shown: list[Unit], question: str) -> str:
    """The evidence in rank order, then the question. The question is the user's own words and
    is not escaped: it grounds nothing, and the list of units shown is the runner's, never read
    back out of this text."""
    records = "\n\n".join(render_unit(unit) for unit in shown) or "No records were found."
    return f"{records}\n\nQuestion: {question}"
