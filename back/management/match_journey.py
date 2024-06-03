from management.models.matches import Match
from management.user_journey import Bucket

class PerMatchBuckets:
    """
    Per-Matching-States
        Pre-Matching:
[FILTER 1]     1.L) 'Learner Pending Matching Confirm, or Volunteer Waiting For Matching Confirm / Denial or Expire'
                learner path
                    - (b) [instantly] send match confirm mail 1 - asking the learner to accept the matching
                          [after 2 days] we send matching confirm reminder1
                          [after 5 days] send matching suggestion expired email
                volunteer path
                    - (b): Volunteer is blocked from matching, only unblocked if the matching is out of 'Pre-Matching'

        Kickoff-Matching:
[FILTER 2]   1) 'Match confirmed no contact'
            - (b): [after XX] days set to 'No Contact' [TODO]
[FILTER 3]   2) 'Match confirmed Single Party Contact' ( only one user send a message )
            - (b): [after XX] days set to ghosted [TODO]
[FILTER 4]   3) 'Match first contact' ( a message send from at least both users )
            - (b): [after XX] days still no video call, set to 'No Contact' [TODO]

        Ongoing-Matching:
[FILTER 5]    1) 'Match Ongoing' ( they had at least one video call, with both attending and last message or video call less than 14 days ago )
[FILTER 6]    2) 'Free Play' ( Basicly a 'Completed' match that is still on-going, still 'Ongoing' after 12 weeks )
            
        Finished-Matching [END]
[FILTER 7]    1) 'Completed Match': ( Happy path2 XX Weeks active matching, now became in-active ) 'still_in_contact_after_12w=True`

        Failed-Matching [END]
[FILTER 8]   1) 'Never Confirmed': The learner never confirmed the match
            - (b): The learner is set to 'No-Confirm' while the Voluntter is moved back to 'Searching'
[FILTER 9]   2) 'No Contact' both parties haven't contacted each other
            - (b): [after XX weeks] send 'still-in-contact' email ( extra path to 'Completed Match' if confirmed by either user, means they left the plattform but are still connected )
[FILTER 10]   3) 'User Ghosted' ( X days in 'Single Party Contact' )
[FILTER 11]  4) 'Contact stopped' ( X days no messages, X days no video calls, less than XX weeks active matching )
    """
    
    BUCKETS = [
        Bucket(
            "Learner Pending Matching Confirm",
            ""
        )        
    ]
    
    queryset = Match.objects.all()

    @classmethod
    def categorize_match(cls, match = None):
        return cls(match).check_all_buckets_single_match()
    
    @classmethod
    def categorize_all_matches(cls):
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
            res[bucket.name] = qs.values_list('uuid', flat=True)
            print(f"Bucket ({i+1}/{len(self.BUCKETS)}) has {len(res[bucket.name])} users")
        return res
            
    def check_all_buckets_single_match(self):
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
    
    BUCKETS = [
        Bucket(
            "Match No Confirm",
            "match_no_confirm",
            "Match-Kickoff",
        ),
        Bucket(
            "Match Single Party Confirm",
            "match_single_party_confirm",
            "Match-Kickoff",
        ),
        Bucket(
            "Match Confirmed",
            "match_confirmed",
            "Match-Kickoff",
        ),
    ]
    
    def match_no_confirm(self):
        # confirmed_by.count() == 0

        return self.queryset.filter(
            support_matching=False, # ignore support matches always
            confirmed=False,
            confirmed_by__count=0,
            active=True, # 'acive=False' ignored match
        )
        
    def match_single_party_confirm(self):
        # confirmed_by.count() == 1

        return self.queryset.filter(
            support_matching=False, # ignore support matches always
            confirmed=False,
            confirmed_by__count=1,
            active=True, # 'acive=False' ignored match
        )
        
    def match_confirmed(self):

        return self.queryset.filter(
            support_matching=False, # ignore support matches always
            confirmed=True,
            active=True, # 'acive=False' ignored match
        )
        
    def match_ongoing(self):
        # last_message or video_call less than 14 days ago
        # TODO: need the video call models for this
            
        return self.queryset.filter(
            support_matching=False,
            confirmed=True,
            active=True,
        )