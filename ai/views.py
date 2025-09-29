from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from services.ai_service import AIService

from .ai_client import client


class ScheduleAssistantView(APIView):
    permission_classes = [IsAuthenticated]
    ai_service = AIService(client)

    def post(self, request):
        user_message = request.data.get("message")
        if not user_message:
            return Response({"error": "message 필수"}, status=400)

        result = self.ai_service.process_schedule_command(request.user, user_message)

        if result is None:
            # 일정 변경 아님 -> 기존 일정 질문 기능 유지
            reply = self.ai_service.ask_schedule_assistant(request.user, user_message)
        else:
            # 일정 생성/수정/삭제 결과 메시지 반환
            reply = result

        return Response({"reply": reply})
