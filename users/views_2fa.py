import base64
from io import BytesIO

import qrcode
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TwoFactorAuthSerializer


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

        return Response({
            "detail": "2FA 기기가 등록되었습니다.",
            "device_id": device.pk,
            "otp_uri": otp_uri,
            "qr_code_base64": qr_code_base64,
            "otp_secret": device.bin_key.hex(),
        })


class TwoFactorVerifyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        user = request.user
        device = TOTPDevice.objects.filter(user=user, name="default").first()
        if not device:
            return Response({"detail": "등록된 2FA 기기가 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        if device.verify_token(code):
            return Response({"detail": "2FA 인증 성공"}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "잘못된 인증 코드"}, status=status.HTTP_400_BAD_REQUEST)
