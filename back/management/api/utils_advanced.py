from rest_framework import serializers
from django_filters import rest_framework as filters
from drf_spectacular.generators import SchemaGenerator

class DynamicFilterSerializer(serializers.Serializer):
    filter_type = serializers.CharField()
    name = serializers.CharField()
    nullable = serializers.BooleanField(default=False)
    value_type = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.DictField(), required=False)
    lookup_expr = serializers.ListField(child=serializers.CharField(), required=False)

def filterset_schema_dict(
        filterset, 
        include_lookup_expr=False, 
        view_key="/api/matching/users/",
        request=None
    ):
    _filters = []
    for field_name, filter_instance in filterset.get_filters().items():
        filter_data = {
            'name': field_name,
            'filter_type': type(filter_instance).__name__,
        }
        
        choices = getattr(filter_instance, 'extra', {}).get('choices', [])
        if len(choices):
            filter_data['choices'] = [{
                "tag": choice[1],
                "value": choice[0]
            } for choice in choices]

        if 'help_text' in filter_instance.extra:
            filter_data['description'] = filter_instance.extra['help_text']
        
        if include_lookup_expr:
            if isinstance(filter_instance, filters.RangeFilter):
                filter_data['lookup_expr'] = ['exact', 'gt', 'gte', 'lt', 'lte', 'range']
            elif isinstance(filter_instance, filters.BooleanFilter):
                filter_data['lookup_expr'] = ['exact']
            else:
                filter_data['lookup_expr'] = [filter_instance.lookup_expr] if isinstance(filter_instance.lookup_expr, str) else filter_instance.lookup_expr
        serializer = DynamicFilterSerializer(data=filter_data)

        serializer.is_valid(raise_exception=True)
        _filters.append(serializer.data)
    # 2 - retrieve the query shema
    generator = SchemaGenerator(
        patterns=None,
        urlconf=None
    )
    schema = generator.get_schema(request=request)
    filter_schemas = schema['paths'].get(view_key, {}).get('get', {}).get('parameters', [])
    for filter_schema in filter_schemas:
        for filter_data in _filters:
            if filter_data['name'] == filter_schema['name']:
                filter_data['value_type'] = filter_schema['schema']['type']
                filter_data['nullable'] = filter_schema['schema'].get('nullable', False)
                break
    return _filters