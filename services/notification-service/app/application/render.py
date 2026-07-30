"""Jinja2 template rendering (M22 plan Q1).

Two environments, chosen by channel:

* **email** — `autoescape=True`. The template body is HTML, and a variable like
  `customer_name` could contain `<`/`&`; escaping the *values* (not the
  template's own markup) closes an HTML-injection hole while leaving the
  template's layout intact.
* **sms** — `autoescape=False`. SMS bodies are plain text, so escaping `&` into
  `&amp;` would be wrong.

Both use Jinja2's default `Undefined`, which renders a missing variable as the
empty string rather than raising — so a contractor's template that references a
variable the caller didn't supply degrades gracefully instead of 500-ing.
"""

from __future__ import annotations

from collections.abc import Mapping

from jinja2 import Environment

_email_env = Environment(autoescape=True)
_text_env = Environment(autoescape=False)


def render(template: str, variables: Mapping[str, object], *, html: bool) -> str:
    """Render `template` with `variables`. `html=True` escapes variable values."""
    env = _email_env if html else _text_env
    return env.from_string(template).render(**variables)
