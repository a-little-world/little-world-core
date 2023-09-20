from rest_framework.views import APIView
from django.views.i18n import JavaScriptCatalog, JSONCatalog
from django.utils.translation.trans_real import DjangoTranslation
from django.utils.translation import get_language
from django.conf import settings
from django.http import JsonResponse
from rest_framework.response import Response


class OverwriteJScatalogue(JavaScriptCatalog):
    """
    We keep everything the same but we allow to manaully overwirte the language 
    """

    def get(self, request, *args, set_lang=None, **kwargs):
        context = self._get_context(
            self, request, *args, set_lang=set_lang, **kwargs)
        return self.render_to_response(context)

    def _get_context(self, request, *args, set_lang=None, **kwargs):
        locale = set_lang if set_lang else get_language()
        domain = kwargs.get('domain', self.domain)
        # If packages are not provided, default to all installed packages, as
        # DjangoTranslation without localedirs harvests them all.
        packages = kwargs.get('packages', '')
        packages = packages.split('+') if packages else self.packages
        paths = self.get_paths(packages) if packages else None
        self.translation = DjangoTranslation(
            locale, domain=domain, localedirs=paths)
        return self.get_context_data(**kwargs)

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(context)  # We want only the json data


def get_trans_as_tag_catalogue(request, _set_lang):
    _view = OverwriteJScatalogue(domain="django")
    # Then we will replace keys with 'aka' translation
    # -> our inofficial translation tags
    context_aka = _view._get_context(
        request, set_lang="tag")['catalog']
    context_other_lang = _view._get_context(
        request, set_lang=_set_lang)['catalog']
    # Perdefault we only return the keys that have an aka,
    print("context_aka: ", list(context_aka.keys()))
    #print("context_other_lang: ", context_other_lang)
    _data = {}
    for k in context_aka:
        print("PROCESSING", k, context_aka[k])
        if isinstance(context_aka[k], str):
            # For english we can just use the deafault catalogue!
            if _set_lang == "en":
                # "\u0004"
                print("WARNING: 'aka' tag is not translated in english!", k)
                try:
                    _data[context_aka[k]] = k.split("\u0004")[1]
                except:
                    _data[context_aka[k]] = k
            elif k in context_other_lang:
                # Or we could use 'from django.utils.text import slugify' <--use-flag
                _data[context_aka[k]] = context_other_lang[k]
        else:
            print(
                f"WARNING 'aka' tag '{context_aka[k]}' has no traslation yet!")
    return _data


class TranslationsGet(APIView):

    def get(self, request, **kwargs):
        """
        Get the translation catalogue for any translated language by tag e.g.: 'interest_art' : 'Kunst'
        Use ?notag then they will be prefixed with the default lang englisch e.g.: 'Art' : 'Kunst'
        """
        _set_lang = kwargs.get("lang")
        if _set_lang == "auto":
            _set_lang = None  # Will cause self.get_language() to be used in the JSCatalogue

        if not request.GET.get("notag", None) is not None:
            # This is the daufault behavior
            # if you wan't to get the old django behavior you must use '?noaka'
            return Response(get_trans_as_tag_catalogue(request, _set_lang))
        else:
            _view = OverwriteJScatalogue.as_view(
                domain="django", packages=["management"])
            return _view(request, set_lang=_set_lang)
