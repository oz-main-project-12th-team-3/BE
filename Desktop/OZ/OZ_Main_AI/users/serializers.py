from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from datetime import timedelta

User = get_user_model()


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('email', 'password')

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name')


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # 응답 데이터 커스터마이징
        data['user_id'] = self.user.id
        data['access_token'] = data.pop('access')
        data['refresh_token'] = data.pop('refresh')
        
        # expires_in은 access_token의 유효 시간(초 단위)을 의미합니다.
        # SIMPLE_JWT 설정에서 ACCESS_TOKEN_LIFETIME을 가져와 사용합니다.
        from django.conf import settings
        access_token_lifetime = settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME', timedelta(minutes=5))
        data['expires_in'] = int(access_token_lifetime.total_seconds())

        return data