# this creates default script injections and cookie names
from back.cookie_consent.models import CookieGroup, Cookie  # !dont_include
# !include from cookie_consent.models import CookieGroup, Cookie

# Our anlytics cookie group
analytics_cookiegroup = CookieGroup.objects.create(
    varname="analytics",
    description="Google analytics and Facebook Pixel",
    is_required=False,
    is_deletable=True
)

google_analytics_cookie = Cookie.objects.create(
    cookiegroup=analytics_cookiegroup,
    description="Google anlytics cookies and scripts",
    include_srcs=[
        "https://www.googletagmanager.com/gtag/js?id=AW-10994486925"],
    include_scripts=[
        "\nwindow.dataLayer = window.dataLayer || [];\n" +
        "function gtag(){dataLayer.push(arguments);}\n" +
        "gtag('js', new Date());\n" +
        "gtag('config', 'AW-10994486925');\n"
        # TODO: there was another gtag I should include
    ],
)

facebook_init_script = "\n!function(f,b,e,v,n,t,s)\n{if(f.fbq)return;n=f.fbq=function(){n.callMethod?\n" + \
    "n.callMethod.apply(n,arguments):n.queue.push(arguments)};\nif(!f._fbq)f._fbq=n;n.push=n;" + \
    "n.loaded=!0;n.version='2.0';\nn.queue=[];t=b.createElement(e);t.async=!0;\nt.src=v;s=b.getElementsByTagName(e)[0];" + \
    "\ns.parentNode.insertBefore(t,s)}(window, document,'script',\n'https://connect.facebook.net/en_US/fbevents.js');\n" + \
    "fbq('init', '1108875150004843');\nfbq('track', 'PageView');\n    "


facebook_pixel_cookie = Cookie.objects.create(
    cookiegroup=analytics_cookiegroup,
    description="Facebook Pixel analytics cookies and scripts",
    include_srcs=[],
    include_scripts=[facebook_init_script],
)
