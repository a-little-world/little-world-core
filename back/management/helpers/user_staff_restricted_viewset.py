from typing import Any, Callable, cast

from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response


class UserStaffRestricedModelViewsetMixin:
    kwargs: dict[str, Any] = {}
    request: Request
    format_kwarg: str | None
    action: str = ""
    allow_user_list: bool = False
    user_editable: list[str] = []

    @classmethod
    def emulate(cls, request: Request, **kwargs: Any):
        obj = cls()
        obj.request = request
        obj.format_kwarg = None

        cls.kwargs = {**cls.kwargs, **kwargs}

        def pop_data(function: Callable[..., Response]) -> Callable[..., Any]:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                kwargs["request"] = request
                return function(*args, **kwargs).data

            return wrapper

        POP_FUNCS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]
        for func in POP_FUNCS:
            if hasattr(obj, func):
                setattr(obj, func, pop_data(getattr(obj, func)))
        return obj

    def check_unallowed_args(self, kwargs):
        res = []
        for item in kwargs:
            if item not in self.user_editable:
                res.append(item)
        return res

    def get_object(self):
        base = cast(Any, super())
        if not self.request.user.is_staff:
            self.kwargs["pk"] = self.request.user.pk
        else:
            if "pk" not in self.kwargs:
                self.kwargs["pk"] = self.request.user.pk

        pk_value = self.kwargs.get("pk")
        if isinstance(pk_value, int):
            return base.get_object()
        elif isinstance(pk_value, str) and pk_value.isnumeric():
            self.kwargs["pk"] = int(pk_value)
            # assume uuid
            return base.get_object()
        elif isinstance(pk_value, str):
            return base.get_queryset().get(uuid=pk_value)
        return base.get_object()

    def update(self, request, *args, **kwargs):
        base = cast(Any, super())
        print("CALLING UPDATE", request.data)
        if not request.user.is_staff:
            unallowed_args = self.check_unallowed_args(request.data)
            if len(unallowed_args) > 0:
                return Response(
                    {arg: "Not User editable" for arg in unallowed_args}, status=status.HTTP_400_BAD_REQUEST
                )
        return base.update(request, *args, **kwargs)

    def get_queryset(self):
        base = cast(Any, super())
        if not self.request.user.is_staff:
            return base.get_queryset().filter(user=self.request.user)
        else:
            return base.get_queryset()

    def get_permissions(self):
        if self.action == "list" and (not self.allow_user_list):
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
