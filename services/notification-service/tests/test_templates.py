"""Jinja2 rendering + built-in default templates (M22 plan Q1)."""

from __future__ import annotations

from app.application.render import render
from app.application.templates_defaults import DEFAULT_TEMPLATES, default_template


def test_render_interpolates_variables() -> None:
    out = render("Hi {{ name }}, total {{ total }}", {"name": "Jane", "total": "$1,200"}, html=False)
    assert out == "Hi Jane, total $1,200"


def test_render_missing_variable_is_empty_not_crash() -> None:
    # A contractor's template referencing an unsupplied variable must degrade,
    # not 500.
    assert render("Hi {{ name }}!", {}, html=False) == "Hi !"


def test_render_html_escapes_variable_values() -> None:
    # Variable values are escaped so a customer name can't inject markup...
    out = render("<p>{{ name }}</p>", {"name": "<script>x</script>"}, html=True)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_html_does_not_escape_the_template_markup() -> None:
    out = render("<p>{{ name }}</p>", {"name": "Jane"}, html=True)
    assert out == "<p>Jane</p>"


def test_render_sms_plain_text_not_escaped() -> None:
    out = render("Tom & Jerry {{ x }}", {"x": "A&B"}, html=False)
    assert out == "Tom & Jerry A&B"


def test_default_templates_cover_the_three_names_both_channels() -> None:
    for name in ("quote_delivery", "proposal_delivery", "signature_request"):
        for channel in ("email", "sms"):
            assert (name, channel) in DEFAULT_TEMPLATES


def test_default_email_has_subject_sms_does_not() -> None:
    email_subject, email_body = default_template("quote_delivery", "email")
    assert email_subject is not None and email_body
    sms_subject, sms_body = default_template("quote_delivery", "sms")
    assert sms_subject is None and sms_body


def test_default_template_unknown_returns_none() -> None:
    assert default_template("nope", "email") is None


def test_default_templates_render_with_expected_vars() -> None:
    subject, body = default_template("quote_delivery", "email")
    rendered_subject = render(subject, {"company_name": "ACME Electric"}, html=False)
    rendered_body = render(
        body,
        {
            "customer_name": "Jane Doe",
            "company_name": "ACME Electric",
            "quote_title": "Panel Upgrade",
            "quote_total": "$1,200.00",
            "view_link": "http://x/view",
        },
        html=True,
    )
    assert rendered_subject == "Your quote from ACME Electric"
    assert "Jane Doe" in rendered_body
    assert "http://x/view" in rendered_body
