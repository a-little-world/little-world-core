from rest_framework.views import APIView
from django.views.i18n import JavaScriptCatalog, JSONCatalog
from django.utils.translation.trans_real import DjangoTranslation
from django.utils.translation import get_language
from django.conf import settings
from django.http import JsonResponse


class OverwriteJScatalogue(JavaScriptCatalog):
    """
    We keep everything the same but we allow to manaully overwirte the language 
    """

    def get(self, request, *args, set_lang=None, **kwargs):
        locale = set_lang if set_lang else get_language()
        domain = kwargs.get('domain', self.domain)
        # If packages are not provided, default to all installed packages, as
        # DjangoTranslation without localedirs harvests them all.
        packages = kwargs.get('packages', '')
        packages = packages.split('+') if packages else self.packages
        paths = self.get_paths(packages) if packages else None
        print("TBS: ", paths)
        self.translation = DjangoTranslation(
            locale, domain=domain, localedirs=paths)
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(context)  # We want only the json data


class TranslationsGet(APIView):

    def get(self, request, **kwargs):
        """
        Get the translation catalogue for any translated language
        """
        _view = OverwriteJScatalogue.as_view()
        return _view(request, set_lang=kwargs.get("lang"))
