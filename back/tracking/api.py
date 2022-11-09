from rest_framework.views import APIView


class EventTriggerApi(APIView):
    """
    General api to create an event object
    we provide **both** 'post' and 'get'
    for a more complete tracking we should always call POST
    but for cross site or small event tracking it is sufficient to call 'get'
    """

    def get(self, request):
        pass

    def post(self, request):
        pass
