console.log("Rendering imported banner js")
{% load temp_utils %}
{% get_cookie_banner_data request=request as cookie_data_json %}
const cookieData = JSON.parse(JSON.parse('{{ cookie_data_json | escapejs }}').cookie_data);
{% load render_bundle from webpack_loader %}
{% render_bundle 'staticfiles' 'js' 'cookie_banner_frontend' as JS_BASE_CODE %}
{% get_base_page_url as BASE_URL %}
const baseUrl = "{{ BASE_URL }}";
const script = '{{ JS_BASE_CODE }}';
const scripUrl = script.split('"')[1];
console.log("Script Url", scripUrl);
// TODO: test if this works, normally cookies are not send cross domain, but this is the same domain only another sub-domain

console.log("COOKIE DATA", cookieData);

const initCode = () => {
    console.log("DOM loaded");
    console.log("Script loaded");

    const div = document.createElement('div');
    div.id = "shadow-root"; // The root container for the cookie banner
    div.style.zIndex = "100"
    document.body.appendChild(div);

    const scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    document.head.appendChild(script);
    //document.head.insertBefore(script, document.head.firstElementChild)
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
        cookieBanner(JSON.parse(cookieData.cookieGroups), JSON.parse(cookieData.cookieSets), null, toImpressum, toPrivacy);
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