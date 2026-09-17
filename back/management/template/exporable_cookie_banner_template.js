{% load temp_utils %}
{% get_cookie_banner_data request hidden_cookie_banner as cookie_data_json %}
const cookieData = JSON.parse('{{ cookie_data_json.cookie_data | escapejs }}');
{% load render_bundle from webpack_loader %}
{% render_bundle 'staticfiles' 'js' 'cookie_banner_frontend' as JS_BASE_CODE %}
{% get_base_page_url as BASE_URL %}
const baseUrl = "{{ BASE_URL }}";
const script = '{{ JS_BASE_CODE }}';
const scripUrl = script.split('"')[1];
let cookieBannerIsHidden = false;
let cookieConsentName = "backend_cookie_consent";
try {
    cookieBannerIsHidden = cookieData.hiddenCookieBanner === true;
    if (cookieData.cookieConsentName) {
        cookieConsentName = cookieData.cookieConsentName;
    }
} catch (e) {
    console.error("Error getting cookie banner hidden state, using default value", e);
}

// The SPA may request the banner to stay hidden (e.g. after login) before this async script
// loaded and defined the real setCookieBannerHidden. Honor that request here.
const forcedHidden = cookieBannerIsHidden || window.__lwCookieBannerHidden === true;
cookieBannerIsHidden = forcedHidden;

const initCode = () => {
    const div = document.createElement('div');
    div.id = "shadow-root"; // The root container for the cookie banner
    if (!cookieBannerIsHidden) {
        div.style.zIndex = "1000";
    } else {
        div.style.zIndex = "0";
    }
    div.style.position = "fixed";
    if (cookieBannerIsHidden) {
        div.style.visibility = "hidden"; // then the script will still be loaded based on the users pre-selection
        div.style.display = "none";
    }
    document.body.appendChild(div);

    const scriptPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        document.head.appendChild(script);
        // document.head.insertBefore(script, document.head.firstElementChild)
        script.onload = resolve;
        script.onerror = reject;
        script.async = true;
        script.src = baseUrl + scripUrl;
    });
    const toImpressum = () => {
        window.location.replace("https://home.little-world.com/impressum");
    }
    const toPrivacy = () => {
        window.location.replace("https://home.little-world.com/datenschutz");
    }
    scriptPromise.then(() => {
        cookieBanner(
            cookieData.cookieGroups,
            cookieData.cookieSets,
            cookieData.cookieStateDict,
            toImpressum,
            toPrivacy,
            cookieBannerIsHidden,
            {},
            cookieConsentName,
        );
    });
}

if (document.readyState !== 'loading') {
    initCode();
} else {
    document.addEventListener('DOMContentLoaded', function () {
        initCode();
    });
}

window.unloadCookieBanner = () => {
    document.getElementById("shadow-root").remove();
}

window.setCookieBannerHidden = (hidden) => {
    window.__lwCookieBannerHidden = hidden;
    cookieBannerIsHidden = hidden;

    const root = document.getElementById("shadow-root");
    if (!root) {
        return;
    }

    if (hidden) {
        root.style.zIndex = "0";
        root.style.visibility = "hidden";
        root.style.display = "none";
    } else {
        root.style.zIndex = "1000";
        root.style.visibility = "visible";
        root.style.display = "block";
    }
}