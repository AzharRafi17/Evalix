from django.core.management import call_command


def test_migrations_apply_cleanly(db):
    call_command('migrate', interactive=False, verbosity=0)