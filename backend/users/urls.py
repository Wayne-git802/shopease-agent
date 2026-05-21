from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import RegisterView, UserInfoView, ChangePasswordView, LogoutView, LowercaseTokenObtainPairView

urlpatterns = [
    # JWT 璁よ瘉
    path('token/', LowercaseTokenObtainPairView.as_view(), name='token_obtain_pair'),      # 鐧诲綍鑾峰彇Token
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),      # 鍒锋柊Token

    # 鐢ㄦ埛鎿嶄綔
    path('register/', RegisterView.as_view(), name='user_register'),              # 娉ㄥ唽
    path('info/', UserInfoView.as_view(), name='user_info'),                      # 鏌ョ湅/鏇存柊鐢ㄦ埛淇℃伅
    path('change-password/', ChangePasswordView.as_view(), name='change_password'), # 淇敼瀵嗙爜
    path('logout/', LogoutView.as_view(), name='user_logout'),                    # 鐧诲嚭
]
