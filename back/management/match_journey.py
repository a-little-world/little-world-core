
from management.user_journey import Bucket

class PerMatchBuckets:
    """
    Per-Matching-States
        Pre-Matching: ( TODO CANNOT actually be measured in there as it's not part of the 'Match' model )
            2.L) 'Learner Pending Matching Confirm'
            - (b) [instantly] send match confirm mail 1 - asking the learner to accept the matching
                  [after 2 days] we send matching confirm reminder1
                  [after 5 days] send matching suggestion expired email
            2.V) 'Volunteer Waiting For Matching Confirm / Denial or Expire'
            - (b): Volunteer is blocked from matching, only unblocked if the matching is out of 'Pre-Matching'

        Kickoff-Matching:
            1) 'Match confirmed no contact'
            - (b): [after XX] days set to 'No Contact' [TODO]
            2) 'Match confirmed Single Party Contact' ( only one user send a message )
            - (b): [after XX] days set to ghosted [TODO]
            3) 'Match first contact' ( a message send from at least both users )
            - (b): [after XX] days still no video call, set to 'No Contact' [TODO]

        Ongoing-Matching:
            1) 'Match Ongoing' ( they had at least one video call, with both attending and last message or video call less than 14 days ago )        
            2) 'Free Play' ( Basicly a 'Completed' match that is still on-going, still 'Ongoing' after 12 weeks )
            
        Finished-Matching [END]
            1) 'Completed Match': ( Happy path2 XX Weeks active matching, now became in-active ) 'still_in_contact_after_12w=True`

        Failed-Matching [END]
            1) 'Never Confirmed': The learner never confirmed the match
            - (b): The learner is set to 'No-Confirm' while the Voluntter is moved back to 'Searching'
            2) 'No Contact' both parties haven't contacted each other
            - (b): [after XX weeks] send 'still-in-contact' email ( extra path to 'Completed Match' if confirmed by either user, means they left the plattform but are still connected )
            3) 'User Ghosted' ( X days in 'Single Party Contact' )
            4) 'Contact stopped' ( X days no messages, X days no video calls, less than XX weeks active matching )
    """
    
    BUCKETS = [
        Bucket(
            "Learner Pending Matching Confirm",
            ""
        )        
    ]
    
    pass