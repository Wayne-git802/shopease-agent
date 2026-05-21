from rest_framework import generics, status, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    UserRegisterSerializer,
    UserSerializer,
    ChangePasswordSerializer,
    LowercaseTokenObtainPairSerializer,
)


class LowercaseTokenObtainPairView(TokenObtainPairView):
    serializer_class = LowercaseTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    """
    用户注册接口
    POST /api/users/register/
    """
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]  # 注册不需要登录

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            'code': 0,
            'msg': '注册成功',
            'data': {
                'username': user.username,
                'email': user.email
            }
        }, status=status.HTTP_201_CREATED)


class UserInfoView(generics.RetrieveUpdateAPIView):
    """
    用户信息查看/更新接口
    GET /api/users/info/ - 查看当前用户信息
    PUT /api/users/info/ - 更新当前用户信息
    """
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data
        })

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'code': 0,
            'msg': '更新成功',
            'data': serializer.data
        })


class ChangePasswordView(APIView):
    """
    修改密码接口
    POST /api/users/change-password/
    """
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({
            'code': 0,
            'msg': '密码修改成功，请重新登录'
        })


class LogoutView(APIView):
    """
    登出接口
    POST /api/users/logout/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response({
            'code': 0,
            'msg': '已登出'
        })
