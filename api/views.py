from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import AccountSerializer


class MeView(APIView):
    """Return metadata for the authenticated API account."""

    def get(self, request):
        return Response({
            'account': AccountSerializer(request.user).data,
        })
