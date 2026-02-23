import pytest


PUBLIC_PATHS = [
    "/login",
    "/sign-up",
    "/forgot-password",
    "/reset-password",
    "/email-preferences",
]


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_frontend_routes_render(page, e2e_base_url: str, path: str) -> None:
    response = page.goto(f"{e2e_base_url}{path}", wait_until="domcontentloaded")

    assert response is not None
    assert response.ok, f"Expected 2xx for {path}, got {response.status}"
    assert page.locator("#root").count() == 1


def test_login_page_loads_non_hidden_cookie_banner_script(page, e2e_base_url: str) -> None:
    page.goto(f"{e2e_base_url}/login", wait_until="domcontentloaded")
    script = page.locator("script[src*='/api/cookies/cookie_banner.js']")
    assert script.count() > 0
    assert page.locator("script[src*='cookie_banner.js?hidden=true']").count() == 0


def test_unauthenticated_app_route_redirects_to_login(page, e2e_base_url: str) -> None:
    page.goto(f"{e2e_base_url}/app/", wait_until="domcontentloaded")
    assert page.url.startswith(f"{e2e_base_url}/login")
    assert "next=%2Fapp" in page.url or "next=/app" in page.url
