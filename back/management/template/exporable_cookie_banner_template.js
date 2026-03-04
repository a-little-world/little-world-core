{% load temp_utils %}
{% get_cookie_banner_data request hidden_cookie_banner as cookie_data_json %}
const cookieData = JSON.parse(JSON.parse('{{ cookie_data_json | escapejs }}').cookie_data);
{% load render_bundle from webpack_loader %}
{% render_bundle 'staticfiles' 'js' 'cookie_banner_frontend' as JS_BASE_CODE %}
{% get_base_page_url as BASE_URL %}
const baseUrl = "{{ BASE_URL }}";
const script = '{{ JS_BASE_CODE }}';
const scripUrl = script.split('"')[1];
let cookieBannerIsHidden = cookieData?.hiddenCookieBanner;

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
        cookieBanner(JSON.parse(cookieData.cookieGroups), JSON.parse(cookieData.cookieSets), null, toImpressum, toPrivacy, cookieBannerIsHidden);
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
    cookieBannerIsHidden = hidden;

    const root = document.getElementById("shadow-root");
    if (!root) {
        return;
    }

    if (hidden) {
        root.style.zIndex = "0";
        root.style.visibility = "hidden";
    } else {
        root.style.zIndex = "1000";
        root.style.visibility = "visible";
    }
}