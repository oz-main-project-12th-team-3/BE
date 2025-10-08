
import logging

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from users.models import User

# 로거 설정
logger = logging.getLogger(__name__)


class SupabaseWebhookAPIView(APIView):
    @csrf_exempt
    def post(self, request, *args, **kwargs):
        """
        Supabase auth.users 테이블에 새로운 레코드가 추가될 때 호출되는 웹훅을 처리합니다.
        """
        payload = request.data
        logger.info(f"Supabase webhook received: {payload}")

        # 이벤트 유형 및 테이블 확인
        event_type = payload.get("type")
        table = payload.get("table")

        if event_type != "INSERT" or table != "users":
            logger.warning(f"Ignoring event type '{event_type}' on table '{table}'")
            return Response(
                {"status": "ignored", "reason": "Event type not applicable"},
                status=status.HTTP_200_OK,
            )

        record = payload.get("record")
        if not record:
            logger.error("No record found in the payload")
            return Response(
                {"error": "No record found"}, status=status.HTTP_400_BAD_REQUEST
            )

        supabase_uid = record.get("id")
        email = record.get("email")
        raw_user_meta_data = record.get("raw_user_meta_data", {})
        nickname = raw_user_meta_data.get("user_name") or raw_user_meta_data.get(
            "name"
        )
        profile_image_url = raw_user_meta_data.get("avatar_url")

        if not supabase_uid or not email:
            logger.error("Supabase UID or email is missing in the record")
            return Response(
                {"error": "Supabase UID or email is missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                # supabase_uid를 기준으로 사용자를 찾거나 생성합니다.
                user, created = User.objects.update_or_create(
                    supabase_uid=supabase_uid,
                    defaults={
                        "email": email,
                    },
                )

                if created:
                    # 새로운 사용자인 경우, 비밀번호를 사용 불가능하게 설정합니다.
                    user.set_unusable_password()
                    user.save()
                    logger.info(f"New user created: {email} (Supabase UID: {supabase_uid})")
                else:
                    logger.info(f"User updated: {email} (Supabase UID: {supabase_uid})")

                # UserProfile 업데이트 또는 생성
                # (post_save 시그널에 의해 프로필은 자동으로 생성됩니다)
                if nickname or profile_image_url:
                    user_profile = user.user_profile
                    if nickname and not user_profile.nickname:
                        user_profile.nickname = nickname
                    if profile_image_url and not user_profile.profile_image_url:
                        user_profile.profile_image_url = profile_image_url
                    user_profile.save()
                    logger.info(f"UserProfile updated for {email}")

        except Exception as e:
            logger.error(f"Error processing webhook for supabase_uid {supabase_uid}: {e}")
            return Response(
                {"error": "An internal error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"status": "processed"}, status=status.HTTP_200_OK)

