import os
import re
import time


def _dismiss_cookie_banner(page) -> None:
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


def test_registration_page_renders_form(page, e2e_base_url: str) -> None:
    response = page.goto(f"{e2e_base_url}/sign-up", wait_until="domcontentloaded")

    assert response is not None
    assert response.ok, f"Expected 2xx for /sign-up, got {response.status}"

    _dismiss_cookie_banner(page)

    email_inputs = page.locator("input[type='email'], input[name*='email']")
    password_inputs = page.locator("input[type='password']")

    if email_inputs.count() == 0 or password_inputs.count() == 0:
        debug_dir = os.path.join(os.getcwd(), "artifacts")
        os.makedirs(debug_dir, exist_ok=True)
        html_path = os.path.join(debug_dir, "signup_page.html")
        screenshot_path = os.path.join(debug_dir, "signup_page.png")
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(page.content())
        page.screenshot(path=screenshot_path, full_page=True)

    assert email_inputs.count() > 0
    assert password_inputs.count() > 0


def test_registration_flow_creates_user(page, e2e_base_url: str) -> None:
    response = page.goto(f"{e2e_base_url}/sign-up", wait_until="domcontentloaded")

    assert response is not None
    assert response.ok, f"Expected 2xx for /sign-up, got {response.status}"

    _dismiss_cookie_banner(page)

    unique_email = f"e2e+{int(time.time())}@example.com"

    page.locator("input[name='firstName']").fill("Emma")
    page.locator("input[name='lastName']").fill("Testerson")
    page.locator("input[name='email']").fill(unique_email)
    page.locator("input[name='password']").fill("Test123!")
    page.locator("input[name='confirmPassword']").fill("Test123!")
    page.locator("input[name='birthYear']").fill("1992")

    selects = page.locator("select")
    if selects.count() > 0:
        for index in range(selects.count()):
            select = selects.nth(index)
            if not select.is_visible():
                continue
            options = select.locator("option")
            if options.count() > 1:
                select.select_option(index=1)

    radio = page.get_by_role("radio")
    if radio.count() > 0:
        radio.first.check(force=True)

    page.evaluate(
        """
        () => {
            const input = document.querySelector("input[type='checkbox'][name='terms']");
            if (input && input.labels && input.labels.length) {
                input.labels[0].click();
                return;
            }
            const label = Array.from(document.querySelectorAll('label')).find((node) =>
                /terms|conditions|privacy|policy/i.test(node.textContent || '')
            );
            if (label) {
                label.click();
            }
        }
        """
    )

    page.evaluate(
        """
        () => {
            const requiredCheckboxes = document.querySelectorAll("input[type='checkbox'][required]");
            requiredCheckboxes.forEach((input) => {
                if (input.labels && input.labels.length) {
                    input.labels[0].click();
                }
            });
        }
        """
    )

    submit_candidates = [
        page.get_by_role("button", name=re.compile(r"sign\s*up|register|create", re.IGNORECASE)),
        page.locator("form button[type='submit']"),
        page.locator("form button").first,
    ]
    clicked = False
    for candidate in submit_candidates:
        if candidate.count() > 0 and candidate.first.is_visible():
            candidate.first.click()
            clicked = True
            break
    if not clicked:
        raise RuntimeError("No visible registration submit button found")

    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_function("() => !window.location.pathname.includes('/sign-up')")
    except Exception:
        debug_dir = os.path.join(os.getcwd(), "artifacts")
        os.makedirs(debug_dir, exist_ok=True)
        html_path = os.path.join(debug_dir, "signup_submit_page.html")
        screenshot_path = os.path.join(debug_dir, "signup_submit_page.png")
        inputs_path = os.path.join(debug_dir, "signup_form_inputs.txt")
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(page.content())
        with open(inputs_path, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('input, select, textarea')).map((field) => {
                            const label = field.getAttribute('aria-label') || '';
                            const name = field.getAttribute('name') || '';
                            const fieldId = field.getAttribute('id') || '';
                            const placeholder = field.getAttribute('placeholder') || '';
                            const type = field.getAttribute('type') || field.tagName.toLowerCase();
                            return `type=${type} name=${name} id=${fieldId} aria-label=${label} placeholder=${placeholder}`.trim();
                        })
                        """
                    )
                )
            )
        page.screenshot(path=screenshot_path, full_page=True)
        raise

    assert "/sign-up" not in page.url

    cookies = page.context.cookies()
    assert any("session" in cookie.get("name", "").lower() for cookie in cookies)
