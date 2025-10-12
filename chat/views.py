from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from chat.paginations import ChatSessionPagination

from .models import ChatLog, VoiceLog
from .serializers import ChatLogSerializer, ChatSessionSerializer, VoiceLogSerializer
from .services.chat_service import (
    create_chat_message,
    create_chat_session,
    create_voice_log,
    get_chat_messages_for_session,
    get_chat_sessions_for_user,
    get_voice_logs_for_session,
)


class ChatSessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "session_id"

    def get_queryset(self):
        return get_chat_sessions_for_user(user=self.request.user)

    @extend_schema(
        summary="챗 세션 상세 조회, 수정, 삭제",
        description="특정 세션 ID에 대한 조회, 수정, 삭제를 지원합니다.",
        responses={
            200: OpenApiResponse(description="챗 세션 상세 정보 반환"),
            404: OpenApiResponse(description="챗 세션을 찾을 수 없습니다."),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=ChatSessionSerializer,
        responses={200: OpenApiResponse(description="챗 세션 수정 성공")},
        summary="챗 세션 수정",
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        responses={204: OpenApiResponse(description="챗 세션 삭제 완료")},
        summary="챗 세션 삭제",
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


class ChatMessageSearchView(generics.ListAPIView):
    serializer_class = ChatLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        search_query = self.request.query_params.get("q", "")
        if not search_query:
            return ChatLog.objects.none()

        return ChatLog.objects.filter(
            user=self.request.user, message__icontains=search_query
        ).order_by("-timestamp")

    @extend_schema(
        summary="챗 메시지 검색",
        description="현재 로그인한 사용자가 메시지 내용으로 검색할 수 있습니다.",
        parameters=[
            OpenApiParameter(
                name="q",
                description="Search term for message content",
                required=True,
                type=str,
            )
        ],
        responses={200: ChatLogSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ChatSessionListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ChatSessionPagination

    def get_queryset(self):
        return get_chat_sessions_for_user(user=self.request.user)

    @extend_schema(
        summary="챗 세션 목록 조회",
        description="현재 사용자의 챗 세션 리스트를 반환합니다.",
        responses={200: OpenApiResponse(description="챗 세션 목록 반환")},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "sessions": serializer.data,
                "detail": "채팅 세션 목록을 불러왔습니다.",
            }
        )

    @extend_schema(
        request=ChatSessionSerializer,
        responses={201: OpenApiResponse(description="챗 세션 생성 성공")},
        summary="챗 세션 생성",
        description="새 챗 세션을 생성합니다.",
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        chat_session = create_chat_session(
            user=request.user,
            title=validated_data.get("title", "New Chat"),
        )

        response_serializer = self.get_serializer(chat_session)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ChatMessageListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get("session_id")
        if not session_id:
            return ChatLog.objects.none()

        return get_chat_messages_for_session(
            user=self.request.user, session_id=session_id
        )

    @extend_schema(
        summary="챗 메시지 목록 조회",
        description="특정 세션의 챗 메시지 리스트를 반환합니다.",
        responses={200: OpenApiResponse(description="챗 메시지 목록 반환")},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=ChatLogSerializer,
        responses={201: OpenApiResponse(description="챗 메시지 생성 성공")},
        summary="챗 메시지 생성",
        description="특정 세션에 새 챗 메시지를 만듭니다.",
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        chat_log = create_chat_message(
            user=request.user,
            session_id=validated_data["session"].id,
            message=validated_data["message"],
        )

        response_serializer = self.get_serializer(chat_log)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class VoiceLogListCreateView(generics.ListCreateAPIView):
    serializer_class = VoiceLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get("session_id")
        if not session_id:
            return VoiceLog.objects.none()

        return get_voice_logs_for_session(user=self.request.user, session_id=session_id)

    @extend_schema(
        summary="음성 로그 목록 조회",
        description="특정 세션의 음성 기록 리스트를 반환합니다.",
        responses={200: OpenApiResponse(description="음성 로그 목록 반환")},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=VoiceLogSerializer,
        responses={201: OpenApiResponse(description="음성 로그 생성 성공")},
        summary="음성 로그 생성",
        description="특정 세션에 새 음성 로그를 저장합니다.",
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        voice_log = create_voice_log(
            user=request.user,
            session_id=validated_data["session"].id,
            input_audio_url=validated_data["input_audio_url"],
        )

        response_serializer = self.get_serializer(voice_log)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
