from django.conf import settings
from django.contrib.auth import get_user_model


def get_demo_user():
    user_model = get_user_model()
    demo_user, created = user_model.objects.get_or_create(username=settings.DEMO_USERNAME)
    if created:
        demo_user.set_unusable_password()
        demo_user.save(update_fields=['password'])
    return demo_user


def get_default_owner_id():
    return get_demo_user().pk


def get_owner(user):
    return user if settings.AUTH_REQUIRED else get_demo_user()