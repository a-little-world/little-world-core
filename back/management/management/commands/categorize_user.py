from django.core.management.base import BaseCommand
from management.user_journey import PerUserBuckets
from management.models.user import User

class Command(BaseCommand):
    
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('arg1', type=str, help='User hash')

    def handle(self, **options):
        hash = options['arg1']
        
        if hash == "all":
            buckets = PerUserBuckets.categorize_all_users()
            print(f"Users have been categorized into buckets: {buckets}")
        else:
            user = User.objects.filter(hash=hash)
            bucket = PerUserBuckets.categorize_user(user)
            
            print("User is in bucket: ", bucket)