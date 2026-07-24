from app.application.pagination import resolve_page


def test_defaults_when_none_given() -> None:
    page = resolve_page(None, None, default_size=20, max_size=100)
    assert page.page == 1
    assert page.page_size == 20
    assert page.offset == 0
    assert page.limit == 20


def test_computes_offset_for_later_pages() -> None:
    page = resolve_page(3, 10, default_size=20, max_size=100)
    assert page.page == 3
    assert page.page_size == 10
    assert page.offset == 20


def test_floors_page_at_1() -> None:
    page = resolve_page(0, 10, default_size=20, max_size=100)
    assert page.page == 1
    assert page.offset == 0

    page_negative = resolve_page(-5, 10, default_size=20, max_size=100)
    assert page_negative.page == 1


def test_floors_page_size_at_1() -> None:
    page = resolve_page(1, 0, default_size=20, max_size=100)
    assert page.page_size == 1


def test_caps_page_size_at_max() -> None:
    page = resolve_page(1, 9999, default_size=20, max_size=100)
    assert page.page_size == 100
