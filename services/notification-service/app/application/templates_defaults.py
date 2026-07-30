"""Built-in fallback templates.

Used when a tenant hasn't defined a custom `notification_template` row for a
given (name, channel). Keyed by `(name, channel)`; each entry is
`(subject_template, body_template)` — subject is `None` for SMS.

Templates are Jinja2. The variables they reference (`customer_name`,
`company_name`, `quote_title`, `quote_total`, `view_link`, …) are supplied by
the caller in `template_vars`; any that are missing render as empty strings
(see `application/render`), so a template never crashes on an absent variable.
"""

from __future__ import annotations

# (name, channel) -> (subject_template | None, body_template)
DEFAULT_TEMPLATES: dict[tuple[str, str], tuple[str | None, str]] = {
    ("quote_delivery", "email"): (
        "Your quote from {{ company_name }}",
        (
            "<p>Hi {{ customer_name }},</p>"
            "<p>{{ company_name }} has prepared a quote for you"
            "{% if quote_title %}: <strong>{{ quote_title }}</strong>{% endif %}"
            "{% if quote_total %} — total {{ quote_total }}{% endif %}.</p>"
            '<p><a href="{{ view_link }}">View your quote</a></p>'
            "<p>Thank you,<br>{{ company_name }}</p>"
        ),
    ),
    ("quote_delivery", "sms"): (
        None,
        (
            "{{ company_name }}: your quote{% if quote_total %} for {{ quote_total }}{% endif %}"
            " is ready. View it here: {{ view_link }}"
        ),
    ),
    ("proposal_delivery", "email"): (
        "Your proposal from {{ company_name }}",
        (
            "<p>Hi {{ customer_name }},</p>"
            "<p>Your proposal{% if proposal_title %} <strong>{{ proposal_title }}</strong>"
            "{% endif %} from {{ company_name }} is ready to review.</p>"
            '<p><a href="{{ view_link }}">Review your proposal</a></p>'
            "<p>Thank you,<br>{{ company_name }}</p>"
        ),
    ),
    ("proposal_delivery", "sms"): (
        None,
        "{{ company_name }}: your proposal is ready to review: {{ view_link }}",
    ),
    ("signature_request", "email"): (
        "Signature requested by {{ company_name }}",
        (
            "<p>Hi {{ customer_name }},</p>"
            "<p>{{ company_name }} has requested your signature"
            "{% if document_title %} on <strong>{{ document_title }}</strong>{% endif %}.</p>"
            '<p><a href="{{ sign_link }}">Review &amp; sign</a></p>'
            "<p>Thank you,<br>{{ company_name }}</p>"
        ),
    ),
    ("signature_request", "sms"): (
        None,
        "{{ company_name }} requests your signature. Review & sign: {{ sign_link }}",
    ),
}


def default_template(name: str, channel: str) -> tuple[str | None, str] | None:
    """Return `(subject_template, body_template)` for a built-in, or None."""
    return DEFAULT_TEMPLATES.get((name, channel))
