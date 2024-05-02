## Django Backend

...

#### Matching V3



( 'Awareness', not backend trackable, use matomo / ad - data )
( 'Information', not backend trackable, use matomo / ad - data )

```
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
        2) 'Match Takeoff' user has `Pre-Matching` or `Kickoff-Matching` Match. ( Volunteers cannot be matched while the Learner hasn't confirmed the match )
        3) 'Active Match': User has matchi in 'Ongoing' or 'Free Play'
    
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
```


```
Per-Matching-States
    Pre-Matching:
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
```