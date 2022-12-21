# To execute on old server
kubectl exec --stdin --tty <POD> sh
python3 manage.py dumpdata --indent 2 user_management django_private_chat2 cookie_consent > old_db_full_dump.json
# Download all the files fron the kubernetes node:
kubectl cp <POD>:/app/old_db_full_dump.json ./back/old_db_full_dump.json
# Then clean up the json datas ( delte non json log data in the *.json files )
# Mege all json files into one
# Create base directory path
mkdir ./back/old_backend_p_images
# Now create the transformed database fixture. ( automaticly stores to "./back/transformed_fixture.json" )
python3 _shell_inject/import_old_backend_database_dump.py
# Now be sure to checkout the upsteam env ( so all these operation happen on the upsteam db )
./run.py switch_env <production-env>
# 1 - delete all existing DB values
./run.py ma flush
# 2 - create base management user and second test user
./run.py inject -i _shell_inject/pre_fixture_import.py
# 3 - now run the fixture import
./run.py ma loaddata ./transformed_fixture.json --verbosity 3
# 4 - now add intial rooms for all matches and add all matches to the base management user & upload all old profile pictures
./run.py inject -i _shell_inject/post_fixture_import.py
# 5 - update the search score for every user that is currently searching
./run.py inject -i _shell_inject/update_search_score.py