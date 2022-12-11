# Calculates a simple matching score between two users
from back.management.matching import matching_score  # !dont_include
from back.management import controller  # !dont_include # used for syntax only
# !include from management.matching import matching_score
# !include from management import controller # this will be used on script execution

usr1 = controller.get_user_by_email('test1@user.de')
usr2 = controller.get_user_by_email('test2@user.de')
print(matching_score.calculate_directional_matching_score(usr1, usr2))
