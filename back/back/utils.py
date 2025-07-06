import json
import random
from copy import deepcopy
from uuid import UUID

from rest_framework.metadata import SimpleMetadata

class CoolerJson(json.JSONEncoder):
    """
    This is our custom json serializer that can also encode sets!
    """

    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, UUID):
            return str(obj)
        try:
            # But especially for __proxy__ elements this is the only way I found
            # I would love to type check for proxy instead but I can't find the __proxy__ type!
            return json.JSONEncoder.default(self, obj)
        except:
            return str(obj)


def dataclass_as_dict(data):
    return {k: getattr(data, k) for k in data.__annotations__}


def get_options_serializer(self, obj):
    """
    Takes the default django rest options serializer
    and transformes it to a little bit more limited amount of data
    """
    d = {}
    dataG = SimpleMetadata()
    for k, v in self.get_fields().items():
        # Per default we only send 'options' for choice fields
        # This keeps the overhead low and doesn't expose any unnecessary model information
        _f = dataG.get_field_info(v)
        if "type" in _f and (_f["type"] == "choice" or _f["type"] == "multiple choice"):
            _t_choices = []
            for choice in _f["choices"]:
                # We do assume that models.IntegerChoices or models.TextChoices is used
                # sadly it seems int keys are auto transformed to string when jsonized
                _t_choices.append({"tag": choice["display_name"], "value": choice["value"]})
                d[k] = _t_choices
    return d


def transform_add_options_serializer(serializer):
    class WOptionSerializer(serializer):  # type: ignore
        class Meta:
            model = deepcopy(serializer.Meta.model)
            fields = [*deepcopy(serializer.Meta.fields), "options"]

    return WOptionSerializer
