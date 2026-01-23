from drf_spectacular.extensions import OpenApiAuthenticationExtension


class NativeOnlyJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """
    OpenAPI extension for NativeOnlyJWTAuthentication.

    This registers the custom JWT authentication class with drf-spectacular
    so it can properly document the authentication method in the schema.
    """

    target_class = "management.authentication.NativeOnlyJWTAuthentication"
    name = "NativeOnlyJWTAuthentication"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token for native app authentication. Token must contain 'client': 'native' claim.",
        }
