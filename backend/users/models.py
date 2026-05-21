from django.db import models
from django.contrib.auth.models import AbstractUser
import re


class User(AbstractUser):
    """
    扩展Django默认User模型
    - username: 登录账号（唯一，仅英文+数字）
    - display_name: 显示名称（无限制）
    """
    
    # 登录账号（继承自AbstractUser，但限制为英文+数字）
    # Django默认使用username作为认证字段，这里直接复用
    username = models.CharField(
        max_length=30,
        unique=True,
        verbose_name='登录账号',
        help_text='登录账号，仅允许英文和数字'
    )
    
    # 显示名称（无限制）
    display_name = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='显示名称',
        help_text='显示名称，无限制'
    )
    
    phone = models.CharField(
        max_length=11,
        blank=True,
        null=True,
        verbose_name='手机号',
        help_text='手机号'
    )
    avatar = models.URLField(
        blank=True,
        null=True,
        verbose_name='头像URL',
        help_text='头像URL'
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='收货地址',
        help_text='收货地址'
    )

    class Meta:
        db_table = 'users'
        verbose_name = '用户'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.display_name or self.username

    def save(self, *args, **kwargs):
        # 如果没有设置显示名，使用账号名
        if not self.display_name:
            self.display_name = self.username
        super().save(*args, **kwargs)

    @classmethod
    def validate_user_id(cls, user_id):
        """
        验证账号格式：只允许英文和数字
        """
        if not re.match(r'^[A-Za-z0-9]+$', user_id):
            raise ValueError('账号只能包含英文和数字')
        return True
