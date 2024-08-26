import json

LOCALE_DIR = "./locale"
LANGS = ["de", "en", "tag"]
FALLBACK_LANG = "tag"

translations = {}


def setup_translations():
    global translations
    translations = {}

    for lang in filter(lambda x: x != "tag", LANGS):
        translations[lang] = {}

        with open(f"{LOCALE_DIR}/{lang}.json", "r") as f:
            translations[lang] = json.load(f)

    translations[FALLBACK_LANG] = {key: key for key in translations["en"]}

    # check that keys are the same in all languages
    for lang in LANGS:
        for key in translations[FALLBACK_LANG]:
            assert key in translations[lang], f"Key {key} not found in {lang}.json"


setup_translations()


def get_context_translations(request, key):
    lang = request.session.get("lang", "en")
    return get_translation(lang, key)


EXCLUDE_PREFIXES = ["auto_messages"]


def get_translation_catalog(filter_prefixes=True):
    if filter_prefixes:
        return {lang: {key: translations[lang][key] for key in translations[lang] if not any(key.startswith(prefix) for prefix in EXCLUDE_PREFIXES)} for lang in LANGS}
    return {lang: translations[lang] for lang in LANGS}


def get_translation(key, lang=FALLBACK_LANG) -> str:
    assert lang in LANGS, f"Language {lang} not supported"

    key_present = key in translations[lang]
    if not key_present:
        print(f"Key {key} not found in {lang}.json, tying fallback language {FALLBACK_LANG}")
        return translations[FALLBACK_LANG].get(key, key)
    else:
        return translations[lang][key]
