from dragonclaw.provider_catalog import get_provider_label, load_provider_catalog_document, menu_primary_providers


def test_load_provider_catalog_has_openrouter():
    doc = load_provider_catalog_document()
    assert doc is not None
    ids = {str(p.get("id", "")).lower() for p in doc.get("providers") or [] if isinstance(p, dict)}
    assert "openrouter" in ids


def test_menu_primary_includes_openrouter():
    menu = menu_primary_providers()
    assert any(pid == "openrouter" for pid, _ in menu)


def test_get_provider_label():
    assert "openrouter" in get_provider_label("openrouter").lower()
