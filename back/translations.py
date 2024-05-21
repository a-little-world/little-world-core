import json

LOCALE_DIR = "./locale"
LANGS = ["de", "en"]
FALLBACK_LANG = "de"

translations = {}

for lang in LANGS:
    translations[lang] = {}
    
    with open(f"{LOCALE_DIR}/{lang}.json", "r") as f:
        translations[lang] = json.load(f)
        
def get_context_translations(request, key):
    lang = request.session.get("lang", "en")
    return get_translation(lang, key)

def get_translation_catalog():
    return {
        lang: translations[lang]
        for lang in LANGS
    }

def get_translation(key, lang=FALLBACK_LANG) -> str:
    assert lang in LANGS, f"Language {lang} not supported"
    
    key_present = key in translations[lang] 
    if not key_present:
        print(f"Key {key} not found in {lang}.json, tying fallback language {FALLBACK_LANG}")
        return translations[FALLBACK_LANG].get(key, key)
    else:
        return translations[lang][key]