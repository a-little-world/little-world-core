import pytest
import os


PUBLIC_PATHS = [
    "/login",
    "/sign-up",
    "/forgot-password",
    "/reset-password",
]


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_frontend_routes_render(page, e2e_base_url: str, path: str) -> None:
    response = page.goto(f"{e2e_base_url}{path}", wait_until="domcontentloaded")

    assert response is not None
    assert response.ok, f"Expected 2xx for {path}, got {response.status}"
    assert page.locator("#root").count() == 1


def test_login_sets_session_cookie(page, e2e_base_url: str) -> None:
    response = page.goto(f"{e2e_base_url}/login", wait_until="domcontentloaded")

    assert response is not None
    assert response.ok, f"Expected 2xx for /login, got {response.status}"

    for label in ["Deny", "Reject all", "Reject", "Decline", "No thanks"]:
        banner_button = page.get_by_role("button", name=label)
        if banner_button.count() > 0 and banner_button.is_visible():
            banner_button.click()
            break
    page.evaluate(
        """
        () => {
            const host = document.querySelector('#shadow-root');
            if (!host || !host.shadowRoot) return false;
            const buttons = Array.from(host.shadowRoot.querySelectorAll('button'));
            const target = buttons.find((button) =>
                /deny|reject all|reject|decline|no thanks|only necessary|necessary/i.test(
                    button.textContent || ''
                )
            );
            if (target) {
                target.click();
                return true;
            }
            return false;
        }
        """
    )
    page.evaluate(
        """
        () => {
            const host = document.querySelector('#shadow-root');
            if (host) {
                host.style.pointerEvents = 'none';
                host.style.display = 'none';
            }
            const root = document.querySelector('#root');
            if (root) {
                root.removeAttribute('inert');
            }
        }
        """
    )

    page.get_by_label("Email").fill("herrduenschnlate+2@gmail.com")
    page.get_by_label("Password").fill("Test123!")
    try:
        button_candidates = [
            page.get_by_role("button", name="Login"),
            page.get_by_role("button", name="Sign In"),
            page.get_by_role("button", name="Sign in"),
            page.locator("form button[type='submit']"),
            page.locator("form button").first,
        ]
        clicked = False
        for candidate in button_candidates:
            if candidate.count() > 0 and candidate.first.is_visible():
                candidate.first.click()
                clicked = True
                break
        if not clicked:
            raise RuntimeError("No visible login button found")
    except Exception:
        debug_dir = os.path.join(os.getcwd(), "artifacts")
        os.makedirs(debug_dir, exist_ok=True)
        html_path = os.path.join(debug_dir, "login_page.html")
        screenshot_path = os.path.join(debug_dir, "login_page.png")
        buttons_path = os.path.join(debug_dir, "login_page_buttons.txt")
        shadow_path = os.path.join(debug_dir, "cookie_banner_shadow.html")
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(page.content())
        with open(buttons_path, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('button')).map((button) => {
                            const label = button.getAttribute('aria-label') || '';
                            return `text=${(button.textContent || '').trim()} aria-label=${label}`.trim();
                        })
                        """
                    )
                )
            )
        with open(shadow_path, "w", encoding="utf-8") as handle:
            handle.write(
                page.evaluate(
                    """
                    () => {
                        const host = document.querySelector('#shadow-root');
                        if (!host || !host.shadowRoot) return '';
                        return host.shadowRoot.innerHTML || '';
                    }
                    """
                )
            )
        page.screenshot(path=screenshot_path, full_page=True)
        raise

    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => !window.location.pathname.includes('/login')")

    assert "/login" not in page.url

    cookies = page.context.cookies()
    assert any("session" in cookie.get("name", "").lower() for cookie in cookies)

    dashboard_candidates = [
        page.get_by_role("link", name="Dashboard"),
        page.get_by_role("button", name="Dashboard"),
        page.locator("a[href*='/app']"),
        page.locator("a[href*='dashboard']"),
    ]
    for candidate in dashboard_candidates:
        if candidate.count() > 0 and candidate.first.is_visible():
            candidate.first.click()
            break

    page.wait_for_timeout(1500)

    try:
        logout_candidates = [
            page.get_by_role("button", name="Logout"),
            page.get_by_role("button", name="Log out"),
            page.get_by_role("button", name="Sign out"),
            page.get_by_role("link", name="Logout"),
            page.get_by_role("link", name="Log out"),
            page.get_by_role("link", name="Sign out"),
        ]
        clicked_logout = False
        for candidate in logout_candidates:
            if candidate.count() > 0 and candidate.first.is_visible():
                candidate.first.click()
                clicked_logout = True
                break
        if not clicked_logout:
            raise RuntimeError("No visible logout control found")
    except Exception:
        debug_dir = os.path.join(os.getcwd(), "artifacts")
        os.makedirs(debug_dir, exist_ok=True)
        html_path = os.path.join(debug_dir, "dashboard_page.html")
        screenshot_path = os.path.join(debug_dir, "dashboard_page.png")
        buttons_path = os.path.join(debug_dir, "dashboard_page_buttons.txt")
        links_path = os.path.join(debug_dir, "dashboard_page_links.txt")
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(page.content())
        with open(buttons_path, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('button')).map((button) => {
                            const label = button.getAttribute('aria-label') || '';
                            return `text=${(button.textContent || '').trim()} aria-label=${label}`.trim();
                        })
                        """
                    )
                )
            )
        with open(links_path, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('a')).map((link) => {
                            const label = link.getAttribute('aria-label') || '';
                            const href = link.getAttribute('href') || '';
                            return `text=${(link.textContent || '').trim()} aria-label=${label} href=${href}`.trim();
                        })
                        """
                    )
                )
            )
        page.screenshot(path=screenshot_path, full_page=True)
        raise
