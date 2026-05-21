import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


def validate_user_id_format(value):
    """
    验证账号格式：只允许英文和数字
    """
    if not re.match(r'^[A-Za-z0-9]+$', value):
        raise serializers.ValidationError('账号只能包含英文和数字，不能使用特殊符号')
    return value


def validate_password_with_cases_and_numbers(value):
    """
    验证密码必须包含大小写字母和数字
    """
    if not re.search(r'[A-Z]', value):
        raise serializers.ValidationError('密码必须包含至少一个大写字母')
    if not re.search(r'[a-z]', value):
        raise serializers.ValidationError('密码必须包含至少一个小写字母')
    if not re.search(r'[0-9]', value):
        raise serializers.ValidationError('密码必须包含至少一个数字')
    return value


class LowercaseTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        if "username" in attrs and isinstance(attrs["username"], str):
            attrs["username"] = attrs["username"].lower()
        return super().validate(attrs)


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    用户注册序列化器
    - username: 登录账号（仅英文+数字）
    - display_name: 显示名称（无限制）
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password, validate_password_with_cases_and_numbers],
        style={'input_type': 'password'}
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    # 显示名称（可选，无限制）
    display_name = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text='显示名称，无限制'
    )

    class Meta:
        model = User
        fields = ('username', 'display_name', 'email', 'password', 'password2', 'phone')
        extra_kwargs = {
            'email': {'required': True},
            'username': {'validators': [validate_user_id_format]},
        }

    def validate_username(self, value):
        """验证账号格式和唯一性"""
        validate_user_id_format(value)
        value = value.lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('该账号已被注册')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({
                'password2': '两次密码不一致'
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        # 如果没有提供显示名，使用账号名
        if not validated_data.get('display_name'):
            validated_data['display_name'] = validated_data.get('username', '')
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    """
    用户信息序列化器（查看/更新）
    - username: 登录账号
    - display_name: 显示名称
    """

    class Meta:
        model = User
        fields = ('username', 'display_name', 'email', 'phone', 'avatar', 'address', 'date_joined')
        read_only_fields = ('username', 'date_joined')


class ChangePasswordSerializer(serializers.Serializer):
    """
    修改密码序列化器
    """
    old_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(
        required=True,
        validators=[validate_password, validate_password_with_cases_and_numbers],
        style={'input_type': 'password'}
    )

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('旧密码不正确')
        return value
