"""
This are all the outsources schema extensions to make all the open api magic work
they heavily rely on information the basic model APIViews offer, this suffices for all basic actions
but you can also extend them how ever you want
"""


def get_register_schema(params, serializer):
    return dict(description="Little World Registration API called with data from the registration form", auth=None, operation_id=None, operation=None, methods=["POST"], request=serializer)
