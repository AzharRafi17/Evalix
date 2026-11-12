from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create or update a user who can authenticate with JWT.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--password')

    def handle(self, *args, **options):
        password = options['password']
        if password is None:
            password = getpass('Password: ')
            confirmation = getpass('Confirm password: ')
            if password != confirmation:
                raise CommandError('Passwords do not match.')
        if not password:
            raise CommandError('Password cannot be empty.')

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=options['username'])
        user.set_password(password)
        user.save(update_fields=['password'])
        action = 'Created' if created else 'Updated'
        self.stdout.write(f'{action} user {user.get_username()}')