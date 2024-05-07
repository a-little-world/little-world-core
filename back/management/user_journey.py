from dataclasses import dataclass
from management.models.user import User
from management.models.state import State
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from django.utils import timezone
from django.db.models import Q, Count

@dataclass
class Bucket:
    name: str
    query: str
    category: str
    
    def to_dict(self):
        return {
            'name': self.name,
            'query': self.query,
            'category': self.category,
        }

class PerUserBuckets:
    """
Per-User-States:
    Sign-Up:
        1) 'User Created'
        - (b): [after 3 hours] send email verification reminder, 
               [after XX days] lands in `Inactive-User[0].Never-Active` [TODO]
        2) 'Email Verified'
        - (b): [after 2 days] send fill form reminder 1
               [after 3 days] send fill form reminder 2
               [after XX days] lands in `Inactive-User[0].Never-Active` [TODO]
        3) 'User form completed'
        - (b): [after XX days] send book pre-matching call reminder reminder [TODO]
               [after XX days] lands in `Inactive-User[0].Never-Active` [TODO]
        4) 'Booked Onboarding Call'
        - (m): When the call was had a matching user marks the 'had_prematching_call=True` ( or `state.to_low_german_level=True` )
    
    Active-User:
        0) 'First Search': user searching for the first time
        - (b): [after XX days] sorry that we dindn't find you a match yet [TODO]
        1) 'Searching' ( User that is searching and has at least one Match )
        - (b): [after XX days] sorry that we dindn't find you a match yet [TODO]
        2) 'Pre Matching' user has `Pre-Matching` Match ( Volunteers cannot be matched while the Learner hasn't confirmed the match )
            --> based of the existend of the 'UnconfirmedMatch' model
        3) 'Match Takeoff' `Kickoff-Matching` Match.
        4) 'Active Match': User has matchi in 'Ongoing' or 'Free Play'
    
    Inactive-User: ( users hat have only 0 or 'Inactive' matchings + ) ( or state.inactive=True was manually set ) [END]
        0) 'Never-Active': Did't ever become active
        0.2) 'No Show': Didn't show up to onboarding call
            - (m): Asks for another call to be booked, delete existing 'PreMatchingAppointment' [TODO manual work atm]
        1) 'Ghoster' ( user has matching in [3.G] 'ghosted' his match )
        2.L) 'No-Confirm' ( learner that has matching in 'Never Confirmed')
        3) 'Happy-Inactive' ( not searching, 1 or more matches at least one match in 'Completed Matching' )
        4) 'Too Low german level' ( user never active, but was flagged with a 'state.to_low_german_level=True' )
        5) 'Unmatched' ( 'first-search' for over XX days, we failed to match the user at-all )
        6) 'Gave-Up-Searching' user thats `searching=False` and has 0 matches
    """
    
    queryset = User.objects.all()
    
    @classmethod
    def categorize_user(cls, user = None):
        return cls(user).check_all_buckets_single_user()
    
    @classmethod
    def categorize_all_users(cls):
        return cls().query_all_buckets()
    
    @classmethod
    def create(cls, queryset = None):
        return cls(queryset)

    def __init__(self, queryset = None):
        if queryset is not None:
            self.queryset = queryset
            
    def query_all_buckets(self):
        res = {}
        for i, bucket in enumerate(self.BUCKETS):
            print(f"Checking Bucket: {bucket.name}")
            qs = getattr(self, bucket.query)()
            res[bucket.name] = qs.values_list('hash', flat=True)
            print(f"Bucket ({i+1}/{len(self.BUCKETS)}) has {len(res[bucket.name])} users")
        # assert no two users in same bucket
        self.assert_no_duplicate_buckets(res)
        return res
            
    def check_all_buckets_single_user(self):
        assert self.queryset.count() == 1, "This method is only for single user queries"
        results = []
        for bucket in self.BUCKETS:
            print(f"Checking Bucket: {bucket.name}")
            qs = getattr(self, bucket.query)()
            if qs.exists():
                results.append(bucket.name)
        # a user should only be in one bucket
        assert len(results) <= 1, f"User in multiple buckets: {results}"
        assert len(results) > 0, "User in no bucket"
        return results[0]

    def assert_no_duplicate_buckets(self, res):
        for bucket_name, user_hashes in res.items():
            for other_bucket_name, other_user_hashes in res.items():
                if bucket_name == other_bucket_name:
                    continue
                intersection = set(user_hashes).intersection(other_user_hashes)
                assert len(intersection) == 0, f"Users {intersection} in multiple buckets: {bucket_name} and {other_bucket_name}"
                
    @classmethod
    def get_schema(self):
        # serialize all buckets,
        serialized = []
        for bucket in self.BUCKETS:
            serialized.append({
                **bucket.to_dict(),
                "description": getattr(self, bucket.query).__doc__,
            })
        return serialized

    # ==================== Sign-Up =====================
    BUCKETS = [
        # 1 - Sign-Up
        Bucket(
            'User Created', 
            'user_created',
            'Sign-Up',
        ),
        Bucket(
            'Email Verified', 
            'email_verified',
            'Sign-Up',
        ),
        Bucket(
            'User-Form Completed', 
            'user_form_completed',
            'Sign-Up',
        ),
        Bucket(
            'Booked Onboarding Call', 
            'booked_onboarding_call',
            'Sign-Up',
        ),
        # 2 - Active User
        Bucket(
            'First Search',
            'first_search',
            'Active User',
        ),
        Bucket(
            'Searching', # User that is searching and has at least one Match
            'user_searching',
            'Active User',
        ),
        Bucket(
            'Pre Matching',
            'pre_matching',
            'Active User',
        ),
        Bucket(
            'Match Takeoff',
            'match_takeoff',
            'Active User',
        ),
        # Bucket(
        #    'Active Match',
        #    'active_match',
        #    'Active Match',
        #),
    ]    

    # 1.1 - 'User Created'
    def user_created(self):
        """
        1.1: User was created, 
            but still has to verify mail, 
            fill form and have a prematching call
        """
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.UNFILLED,
            state__unresponsive=False,
            state__email_authenticated=False,
            state__had_prematching_call=False,
        )
        
    # 1.2 - 'Email Verified'
    def email_verified(self):
        """
        1.2: User has verified email, 
            but still has to fill form and have a prematching call
        """
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.UNFILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=False,
        )
        
    # 1.3 - 'User-Form Completed'
    def user_form_completed(self):
        """
        1.3: User has filled form, 
            but still has to have a prematching call
        """
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=False,
        ).annotate(
            num_appointments=Count(
                'prematchingappointment', 
               filter=Q(prematchingappointment__end_time__gt=timezone.now())),
        ).filter(
            num_appointments=0
        )
        
    # 1.4 - 'Booked Onboarding Call'
    def booked_onboarding_call(self):
        """
        1.4: User has filled form and booked onboarding call
        """
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        ).annotate(
            num_appointments=Count(
                'prematchingappointment', 
               filter=Q(prematchingappointment__end_time__gt=timezone.now())),
        ).filter(
            num_appointments__gt=0
        )
        
    # ==================== Active User =====================
    
    # 2.1 - 'First Search'
    def first_search(self):
        """
        2.1: User is doing first search i.e.: has no 'non-support' match
        """
        # TODO: check again
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        ).annotate( 
            num_matches=Count(
                'match_user1', 
                filter=Q(match_user1__support_matching=False)
            ) + Count(
                'match_user2', 
                filter=Q(match_user2__support_matching=False)
            )
        ).filter(
            num_matches=0
        )
        
    # 2.2 - 'Searching'
    def user_searching(self):
        """
        2.2: User is searching and has at least one match
        """
        # TODO: possibly have to check that the match is not a failed match
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        ).annotate( 
            num_matches=Count(
                'match_user1', 
                filter=Q(match_user1__support_matching=False)
            ) + Count(
                'match_user2', 
                filter=Q(match_user2__support_matching=False)
            )
        ).filter(
            num_matches__gt=0
        )
        
    # 2.3 - 'Pre Matching'
    def pre_matching(self):
        """
        2.3: User has `Pre-Matching` or `Kickoff-Matching` Match. 
        """
        return self.queryset.filter(
            Q(unconfirmed_match_user1__closed=False) |
            Q(unconfirmed_match_user2__closed=False),
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        ).distinct()
        
    def match_takeoff(self):
        """
        2.3: User has `Pre-Matching` or `Kickoff-Matching` Match. 
        ( Volunteers cannot be matched while the Learner hasn't confirmed the match )
        """
        # TODO
        return self.queryset.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        ).annotate( 
            num_matches=Count(
                'match_user1', 
                filter=Q(match_user1__support_matching=False)
            ) + Count(
                'match_user2', 
                filter=Q(match_user2__support_matching=False)
            )
        ).filter(
            num_matches__gt=0
        )