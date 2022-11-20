import random
from uuid import uuid4
from rest_framework.metadata import SimpleMetadata
from copy import deepcopy

VERSION = 1


def _api_url(slug, _v=VERSION, admin=False, end_slash=True):
    v = "" if _v == 1 else f"/v{_v}"
    return (f"api/admin{v}/{slug}" if admin else f"api/{slug}{v}") + ("/" if end_slash else "")


def _double_uuid():
    return str(uuid4()) + "-" + str(uuid4())


def _rand_int5():
    return random.randint(10000, 99999)


def get_options_serializer(self, obj):
    d = {}
    dataG = SimpleMetadata()
    for k, v in self.get_fields().items():
        # Per default we only send 'options' for choice fields
        # This keeps the overhead low and doesn't expose any unnecessary model information
        _f = dataG.get_field_info(v)
        if "type" in _f and _f["type"] == "choice":
            _t_choices = []
            for choice in _f["choices"]:
                # We do assume that models.IntegerChoices is used
                # sadly it seems int keys are auto transformed to string when jsonized
                _t_choices.append(
                    {"tag": choice["display_name"], "value": choice["value"]})
                d[k] = _t_choices
    return d


def transform_add_options_serializer(serializer):
    class WOptionSerializer(serializer):  # type: ignore
        class Meta:
            model = deepcopy(serializer.Meta.model)
            fields = [
                *deepcopy(serializer.Meta.fields), "options"]
    return WOptionSerializer
