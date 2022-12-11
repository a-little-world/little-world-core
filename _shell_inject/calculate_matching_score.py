# Calculates a simple matching score between two users
from back.management.matching import matching_score  # !dont_include
from back.management import controller  # !dont_include # used for syntax only
from back.management import tasks  # !dont_include
# !include from management import tasks
# !include from management.matching import matching_score
# !include from management import controller # this will be used on script execution

usr1 = controller.get_user_by_email('test1@user.de')
# usr2 = controller.get_user_by_email('test2@user.de')
#matching_score.calculate_directional_score_write_results_to_db(usr1, usr2)
tasks.calculate_directional_matching_score_background(usr1)
