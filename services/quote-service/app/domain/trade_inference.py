"""Domain logic for inferring trade categories from quote context."""

from __future__ import annotations

# Keyword → trade taxonomy mapping
_TRADE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("electric", "electrical"),
    ("panel", "electrical"),
    ("wiring", "electrical"),
    ("wire", "electrical"),
    ("outlet", "electrical"),
    ("breaker", "electrical"),
    ("plumb", "plumbing"),
    ("pipe", "plumbing"),
    ("drain", "plumbing"),
    ("faucet", "plumbing"),
    ("leak", "plumbing"),
    ("hvac", "hvac"),
    ("furnace", "hvac"),
    ("air condition", "hvac"),
    ("ac ", "hvac"),
    ("heat pump", "hvac"),
    ("duct", "hvac"),
    ("solar", "solar"),
    ("pv ", "solar"),
    ("inverter", "solar"),
    ("roof", "roofing"),
    ("shingle", "roofing"),
    ("gutter", "roofing"),
    ("floor", "flooring"),
    ("tile", "flooring"),
    ("hardwood", "flooring"),
    ("paint", "painting"),
    ("drywall", "painting"),
    ("landscap", "landscaping"),
    ("lawn", "landscaping"),
)


def infer_trade(title: str | None, line_item_descriptions: list[str] | None = None) -> str:
    """Infer trade category from quote title and optional line item descriptions.

    Returns one of: electrical, plumbing, hvac, solar, roofing, flooring, painting, landscaping, or general.
    """
    candidates: list[str] = []
    if title:
        candidates.append(title.lower())
    if line_item_descriptions:
        candidates.extend(desc.lower() for desc in line_item_descriptions if desc)

    for text in candidates:
        for keyword, trade in _TRADE_KEYWORDS:
            if keyword in text:
                return trade

    return "general"
