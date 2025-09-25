import base64
from io import BytesIO

import qrcode
from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import TwoFactorAuthSerializer
from .services.token_service import generate_tokens


class TwoFactorSetupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        device, created = TOTPDevice.objects.get_or_create(user=user, name="default")

        otp_uri = device.config_url

        qr = qrcode.make(otp_uri)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

        return Response(
            {
                "detail": "2FA 기기가 등록되었습니다.",
                "device_id": device.pk,
                "otp_uri": otp_uri,
                "qr_code_base64": qr_code_base64,
                "otp_secret": device.bin_key.hex(),
            }
        )


class TwoFactorVerifyView(APIView):
    permission_classes = [permissions.AllowAny]  # 인증 전이므로 허용

    def post(self, request):
        serializer = TwoFactorAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        email = request.data.get("email")  # 이메일도 같이 받아야 함

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "사용자가 존재하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device = TOTPDevice.objects.filter(user=user, name="default").first()
        if not device:
            return Response(
                {"detail": "등록된 2FA 기기가 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if device.verify_token(code):
            # 2FA 인증 성공 시 토큰 발급
            access_token, refresh_token, access_token_lifetime = generate_tokens(user)

            response = Response(
                {
                    "detail": "2FA 인증 성공",
                    "user_id": user.id,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                },
                status=status.HTTP_200_OK,
            )
            secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(access_token_lifetime.total_seconds()),
            )
            response.set_cookie(
                "refresh_token",
                refresh_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(
                    settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
                ),
            )
            return response
        else:
            return Response(
                {"detail": "잘못된 인증 코드"}, status=status.HTTP_400_BAD_REQUEST
            )
