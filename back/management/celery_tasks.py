from back.celery import app
from .models import User


@app.task(name="matching_score_calculation")
def calculate_directional_matching_score_background(usr):
    """
    This is the backend task for calculating a matching score. 
    This will *automaticly* be executed everytime a users changes his user form
    run with calculate_directional_matching_score_background.delay(usr)
    """
    for other_usr in User.objects.all():
        # We do loop over all users, but for most users the score calculation will abort quickly
        # e.g.: if the user is a volunteer and the 'other_usr' is also a volunteer
        # then the score calculation would abbort imediately and return 'matchable = False'

        pass
    pass
