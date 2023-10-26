
from django.core.management.base import BaseCommand
import csv , sys
from management.models.question_deck import CardContent, UserDeck
from management.models.state import State
from ...models.user import User

class Command(BaseCommand):
    def handle(self, *args, **options):
        
        with open("/back/dev_test_data/Questions_add.csv", 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            all_data_in_file = {}
            starting_category = None
            for line in reader:
                temp_data = {}
                count = 0 
                for key in line.keys():
                    category_name = key.split("/")[0]
                    category_lang = key.split("/")[1]
                    if count != 0:
                        if category_lang == starting_category:
                            if count not in all_data_in_file:
                                all_data_in_file[count] = []
                                all_data_in_file[count].append(temp_data)
                            else:
                                all_data_in_file[count].append(temp_data)
                            temp_data = {}
                            temp_data["content"] = {
                                category_lang:line[key]
                            }
                            temp_data["name"] = {
                                category_lang:category_name
                            }
                        else:
                            temp_data["content"][category_lang] = line[key]
                            temp_data["name"][category_lang] = category_name
                    elif count == 0:
                        starting_category = category_lang
                        temp_data["content"] = {
                            category_lang:line[key]
                        }
                        temp_data["name"] = {
                            category_lang:category_name
                        }
                    count += 1
                if temp_data:
                    if count not in all_data_in_file:
                        all_data_in_file[count] = []
                        all_data_in_file[count].append(temp_data)
                    else:
                        all_data_in_file[count].append(temp_data)
            count = 0 
            created_count = 0
            for keys in all_data_in_file.keys():
                for data in all_data_in_file[keys]:
                    try:
                        data_present = False
                        for key in data["content"].keys():
                            if data["content"][key].strip() != "":
                                data_present = True
                                break
                        if data_present:
                            obj, created = CardContent.objects.get_or_create(content=data["content"], category_name = data["name"])
                            if created:
                                created_count += 1
                            count += 1
                    except:
                        print("Error creating object")
            print(f"Object created count : {created_count}")
        if CardContent.objects.exists():
            user_obj = User.objects.all()
            for user in user_obj:
                cat_user,created = UserDeck.objects.get_or_create(user=user)
                cat_id = CardContent.objects.all()
                cat_user.content_id.set(cat_id)
                cat_user.save()   
                try:
                    state_user = State.objects.get(user=user) 
                    state_user.user_deck.set(cat_id)
                    state_user.save()
                except State.DoesNotExist:
                    print("State Does not exist")
        return "Assigned all questions to the user, and the questions have also been added."