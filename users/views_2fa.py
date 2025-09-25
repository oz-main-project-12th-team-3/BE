from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import TwoFactorAuthSerializer
from .services.token_service import generate_tokens


class TwoFactorSetupView(APIView):
    permission_classes = [permissions.IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        user = request.user

        if not user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # 이미 등록된 기기가 있으면 신규 생성하지 않고 해당 기기 반환
        existing_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if existing_device:
            otp_uri = existing_device.config_url
            qr_code_base64 = None  # QR 코드는 프론트에서 otp_uri로 생성 가능
            return Response(
                {
                    "detail": "2FA 기기가 이미 등록되어 있습니다.",
                    "device_id": existing_device.id,
                    "otp_uri": otp_uri,
                    "qr_code_base64": qr_code_base64,
                },
                status=status.HTTP_200_OK,
            )

        # 신규 2FA 기기 생성
        device = TOTPDevice.objects.create(user=user, name="default")
        otp_uri = device.config_url

        # QR 코드 생성(시리얼라이저 또는 프론트에서 처리 권장)
        qr_code_base64 = None

        return Response(
            {
                "detail": "2FA 기기가 등록되었습니다.",
                "device_id": device.id,
                "otp_uri": otp_uri,
                "qr_code_base64": qr_code_base64,
            },
            status=status.HTTP_201_CREATED,
        )


class TwoFactorConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        code = request.data.get("code")

        device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
        if device and device.verify_token(code):
            device.confirmed = True
            device.save()
            return Response({"detail": "2FA 등록이 완료되었습니다."})
        return Response(
            {"detail": "잘못된 인증 코드"}, status=status.HTTP_400_BAD_REQUEST
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
