import base64
import io
import secrets
import string

import qrcode
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

TOTP_DEVICE_NAME = "authenticator"
RECOVERY_DEVICE_NAME = "recovery"


def get_confirmed_device(user):
    return (
        TOTPDevice.objects.filter(user=user, name=TOTP_DEVICE_NAME, confirmed=True)
        .order_by("-id")
        .first()
    )


def get_pending_device(user):
    return (
        TOTPDevice.objects.filter(user=user, name=TOTP_DEVICE_NAME, confirmed=False)
        .order_by("-id")
        .first()
    )


def start_enrollment(user):
    device = get_pending_device(user)
    if device:
        return device
    return TOTPDevice.objects.create(user=user, name=TOTP_DEVICE_NAME, confirmed=False)


def cancel_enrollment(user):
    TOTPDevice.objects.filter(user=user, name=TOTP_DEVICE_NAME, confirmed=False).delete()


def disable_two_factor(user):
    TOTPDevice.objects.filter(user=user, name=TOTP_DEVICE_NAME).delete()
    StaticDevice.objects.filter(user=user, name=RECOVERY_DEVICE_NAME).delete()


def generate_recovery_codes(user, count=8):
    device, _ = StaticDevice.objects.get_or_create(user=user, name=RECOVERY_DEVICE_NAME)
    device.token_set.all().delete()
    codes = []
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(count):
        code = "".join(secrets.choice(alphabet) for _ in range(10))
        StaticToken.objects.create(device=device, token=code)
        codes.append(code)
    return codes


def recovery_device(user):
    return StaticDevice.objects.filter(user=user, name=RECOVERY_DEVICE_NAME).first()


def build_qr_image(otpauth_uri):
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def manual_key(device):
    return base64.b32encode(device.bin_key).decode("ascii").strip("=")
