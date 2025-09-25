from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.ai_service import get_gemini_response


class GenerateTextView(APIView):
    """
    An API view to generate text using the Gemini AI model.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        prompt = request.data.get("prompt")
        if not prompt:
            return Response(
                {"error": "Prompt is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        response_text = get_gemini_response(prompt)

        return Response({"response": response_text}, status=status.HTTP_200_OK)
