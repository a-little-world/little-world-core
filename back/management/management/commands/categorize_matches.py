from django.core.management.base import BaseCommand
from management.user_journey import PerUserBuckets
from management.models.user import User

class Command(BaseCommand):
    
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('arg1', type=str, help='User hash')

    def handle(self, **options):
        uuid = options['arg1']
        