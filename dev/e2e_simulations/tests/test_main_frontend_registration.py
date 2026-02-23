import os
import re
import time


def _dismiss_cookie_banner(page) -> None:
    for label in ["Deny", "Reject all", "Reject", "Decline", "No thanks", "Only necessary", "Necessary"]:
        banner_button = page.get_by_role("button", name=re.compile(label, re.IGNORECASE))
        if banner_button.count() > 0 and banner_button.is_visible():
            banner_button.first.click(timeout=3000)
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
    try:
        page.wait_for_function(
            """
            () => {
                const host = document.querySelector('#shadow-root');
                if (!host) return true;
                const style = window.getComputedStyle(host);
                return (
                    style.display === 'none' ||
                    style.visibility === 'hidden' ||
                    style.pointerEvents === 'none' ||
                    host.hidden ||
                    host.getBoundingClientRect().height === 0
                );
            }
            """,
            timeout=3000,
        )
    except Exception:
        # In CI the host may remain mounted a bit longer; keep going and retry if needed.
        pass
    page.evaluate(
        """
        () => {
            const host = document.querySelector('#shadow-root');
            if (host) {
                host.style.pointerEvents = 'none';
                host.style.display = 'none';
                host.setAttribute('aria-hidden', 'true');
            }
            const root = document.querySelector('#root');
            if (root) root.removeAttribute('inert');
            document.documentElement?.removeAttribute('inert');
            document.body?.removeAttribute('inert');
        }
        """
    )
    page.wait_for_timeout(400)


def _fetch_email_auth_pin(page, e2e_base_url: str, email: str, timeout_seconds: int = 10) -> str:
    deadline = time.time() + timeout_seconds
    last_response = ""
    while time.time() < deadline:
        response = page.request.get(
            f"{e2e_base_url}/api/dev/e2e_tests/email_auth_pin/",
            params={"email": email},
        )
        if response.status == 200:
            payload = response.json()
            pin = str(payload.get("email_auth_pin", "")).strip()
            if re.fullmatch(r"\d{5}", pin):
                return pin
            last_response = f"200 with invalid payload: {payload}"
        else:
            try:
                payload = response.json()
            except Exception:
                payload = response.text()
            last_response = f"{response.status}: {payload}"

        page.wait_for_timeout(400)

    raise AssertionError(f"Could not fetch email auth pin for {email}. Last response: {last_response}")


def _submit_email_verification_code(page, pin: str) -> None:
    input_candidates = [
        page.locator("input[name='verificationCode']"),
        page.locator("input[placeholder*='code' i]"),
        page.locator("input[type='number']").first,
    ]
    filled = False
    for candidate in input_candidates:
        if candidate.count() > 0 and candidate.first.is_visible():
            candidate.first.fill(pin)
            filled = True
            break
    if not filled:
        raise RuntimeError("No visible verification code input found")

    submit_candidates = [
        page.locator("form button[type='submit']"),
        page.get_by_role("button", name=re.compile(r"verify|confirm|submit", re.IGNORECASE)),
    ]
    clicked = False
    for candidate in submit_candidates:
        if candidate.count() > 0 and candidate.first.is_visible():
            candidate.first.click(timeout=5000)
            clicked = True
            break
    if not clicked:
        raise RuntimeError("No visible verify-email submit button found")


def _select_volunteer_on_user_form(page) -> None:
    # `/app/user-form` first renders a welcome screen; continue into `user-type`.
    if re.search(r"/app/user-form/?$", page.url):
        welcome_candidates = [
            page.get_by_role("button", name=re.compile(r"start now|jetzt starten", re.IGNORECASE)),
            page.locator("button"),
        ]
        clicked_welcome = False
        for candidate in welcome_candidates:
            if candidate.count() > 0 and candidate.first.is_visible():
                candidate.first.click(timeout=5000)
                clicked_welcome = True
                break
        if not clicked_welcome:
            raise RuntimeError("Could not find welcome continue button on user-form page")
        page.wait_for_url(re.compile(r"/app/user-form/user-type($|\\?)"), timeout=15000)

    _dump_debug_artifacts(page, "user_form_user_type_before_select")

    volunteer_pattern = re.compile(r"volunteer|sprachpate", re.IGNORECASE)
    option_candidates = [
        page.locator("button", has_text=volunteer_pattern),
        page.get_by_role("button", name=volunteer_pattern),
        page.get_by_text(volunteer_pattern),
    ]

    selected = False
    for candidate in option_candidates:
        if candidate.count() > 0 and candidate.first.is_visible():
            candidate.first.click(timeout=5000)
            selected = True
            break
    if not selected:
        selected = page.evaluate(
            """
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const target = buttons.find((button) =>
                    /volunteer|sprachpate/i.test(button.textContent || '')
                );
                if (!target) return false;
                target.click();
                return true;
            }
            """
        )
    page.evaluate(
        """
        () => {
            const input = document.querySelector("input[name='user_type']");
            if (!input) return;
            input.value = 'volunteer';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """
    )
    if not selected:
        raise RuntimeError("Could not find volunteer option on user-form page")

    next_button = page.locator("form button[type='submit']")
    if next_button.count() == 0 or not next_button.first.is_visible():
        raise RuntimeError("Could not find next button on user-form page")
    next_button.first.click(timeout=5000)
    _dump_debug_artifacts(page, "user_form_user_type_after_submit_click")


def _dump_debug_artifacts(page, prefix: str) -> None:
    debug_dir = os.path.join(os.getcwd(), "artifacts")
    os.makedirs(debug_dir, exist_ok=True)
    html_path = os.path.join(debug_dir, f"{prefix}.html")
    screenshot_path = os.path.join(debug_dir, f"{prefix}.png")
    controls_path = os.path.join(debug_dir, f"{prefix}_controls.txt")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(page.content())
    with open(controls_path, "w", encoding="utf-8") as handle:
        handle.write(
            "\n".join(
                page.evaluate(
                    """
                    () => {
                        const controls = Array.from(document.querySelectorAll(
                            "input, select, textarea, button, [role='combobox'], [role='option']"
                        ));
                        return controls.map((el) => {
                            const role = el.getAttribute('role') || '';
                            const name = el.getAttribute('name') || '';
                            const fieldId = el.getAttribute('id') || '';
                            const type = el.getAttribute('type') || el.tagName.toLowerCase();
                            const aria = el.getAttribute('aria-label') || '';
                            const placeholder = el.getAttribute('placeholder') || '';
                            const text = (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
                            return `type=${type} role=${role} name=${name} id=${fieldId} aria-label=${aria} placeholder=${placeholder} text=${text}`.trim();
                        });
                    }
                    """
                )
            )
        )
    page.screenshot(path=screenshot_path, full_page=True)


def _fill_self_info_1_and_continue(page) -> None:
    _dump_debug_artifacts(page, "self_info_1_before_fill")

    postal_candidates = [
        page.locator("input[name='postal_code']"),
        page.locator("input[aria-label*='post' i]"),
        page.locator("input[placeholder*='post' i]"),
    ]
    for candidate in postal_candidates:
        if candidate.count() > 0 and candidate.first.is_visible():
            candidate.first.fill("10115")
            break

    for label_regex in [
        re.compile(r"gender|geschlecht", re.IGNORECASE),
        re.compile(r"where do you live|wo wohnst du", re.IGNORECASE),
        re.compile(r"language level|sprachniveau", re.IGNORECASE),
    ]:
        field = page.get_by_role("combobox", name=label_regex)
        if field.count() > 0 and field.first.is_visible():
            field.first.click(timeout=3000)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")

    submit_button = page.locator("form button[type='submit']")
    if submit_button.count() == 0 or not submit_button.first.is_visible():
        raise RuntimeError("Could not find submit button on self-info-1 page")
    submit_button.first.click(timeout=5000)

    try:
        page.wait_for_load_state("networkidle")
        page.wait_for_url(re.compile(r"/app/user-form/interests($|\\?)"), timeout=15000)
    except Exception:
        _dump_debug_artifacts(page, "self_info_1_submit_failed")
        raise


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
            try:
                candidate.first.click(timeout=5000)
            except Exception:
                _dismiss_cookie_banner(page)
                candidate.first.click(timeout=5000)
            clicked = True
            break
    if not clicked:
        raise RuntimeError("No visible registration submit button found")

    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_function("() => !window.location.pathname.includes('/sign-up')")
        page.wait_for_url(re.compile(r"/app/verify-email"), timeout=15000)
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
    assert "/app/verify-email" in page.url

    email_auth_pin = _fetch_email_auth_pin(page, e2e_base_url, unique_email)
    assert re.fullmatch(r"\d{5}", email_auth_pin)
    _submit_email_verification_code(page, email_auth_pin)
    page.wait_for_load_state("networkidle")
    page.wait_for_url(re.compile(r"/app/user-form($|/)"), timeout=15000)
    _select_volunteer_on_user_form(page)
    page.wait_for_load_state("networkidle")
    page.wait_for_url(re.compile(r"/app/user-form/self-info-1($|\\?)"), timeout=15000)
    _fill_self_info_1_and_continue(page)

    assert "/app/verify-email" not in page.url
    assert "/app/user-form/interests" in page.url

    cookies = page.context.cookies()
    assert any("session" in cookie.get("name", "").lower() for cookie in cookies)
