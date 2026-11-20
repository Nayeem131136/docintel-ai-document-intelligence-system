"""Create (or update) an API user and print the token used to sign in.

    python manage.py create_api_user alice            # asks for a password
    python manage.py create_api_user admin --staff    # staff users can see every user's documents
"""
import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Create or update an API user and print their token."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", help="Password (prompted when omitted; avoid passing it on the command line).")
        parser.add_argument("--staff", action="store_true", help="Give the user access to all documents and the admin site.")

    def handle(self, *args, **options):
        password = options["password"] or getpass.getpass("Password: ")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        User = get_user_model()
        user, created = User.objects.get_or_create(username=options["username"])
        user.set_password(password)
        if options["staff"]:
            user.is_staff = True
            user.is_superuser = True
        user.save()
        token, _ = Token.objects.get_or_create(user=user)
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} user '{user.username}'."))
        self.stdout.write(f"API token: {token.key}")
