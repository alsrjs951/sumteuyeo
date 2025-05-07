from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()

# 회원가입 폼

class UserSignupAPIForm(forms.Form):
    """
    API를 통한 사용자 회원가입을 위한 일반 폼입니다.
    """
    username = forms.CharField(max_length=150, required=True)
    password_1 = forms.CharField(label="비밀번호", widget=forms.PasswordInput, required=True)
    password_2 = forms.CharField(label="비밀번호 확인", widget=forms.PasswordInput, required=True)
    email = forms.EmailField(label="이메일 주소", required=True) # 이메일 다시 추가

    def clean_username(self):
        """사용자 이름 중복 검사"""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("이미 사용 중인 사용자 이름입니다.")
        return username

    def clean_email(self):
        """이메일 중복 검사"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("이미 사용 중인 이메일 주소입니다.")
        return email

    def clean_password_2(self):
        """비밀번호 일치 여부 확인"""
        password_1 = self.cleaned_data.get('password_1')
        password_2 = self.cleaned_data.get('password_2')
        if password_1 and password_2 and password_1 != password_2:
            raise ValidationError("비밀번호가 일치하지 않습니다.")
        return password_2 # 두 번째 비밀번호는 cleaned_data에 저장될 필요는 보통 없음

    # save 메서드는 직접 만들 필요 없이, 뷰에서 form.cleaned_data를 사용