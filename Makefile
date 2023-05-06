## ----------------------------------------------------------------------
## Little World Backend Makefile
## 
## this are the little world development scripts ( currently moving from the run script for more transparency )
## this contains **all** utility scripts for development and deployment and repetative tasks
## ----------------------------------------------------------------------

# development dir ( TODO spaces in path are not correctly escaped yet )
root_dir := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
dev_container_label := littleworld_dev
all_dev_container_ids := $(shell docker ps -a --filter "label=$(dev_container_label)=1" --format "{{.ID}}")
running_dev_container_ids := $(shell docker ps --filter "label=$(dev_container_label)=1" --format "{{.ID}}")


# env file to be used dev repo only included 'env'
env_file := $(root_dir)/env

# used to configure permission groups for data shared between host and container
user_id := $(shell id -u)
group_id := $(shell id -g)

# dev redis container setup
redis_port := 6379:6379
redis_img := redis:5
redis_label := littleworld_redis

# backend container setup
backend_port := 8000:8000
backend_img_sha := $(shell docker images -q littleworld_back.dev:latest) # lates development backend image
backend_tag := littleworld_back.dev
backend_label := littleworld_backend

## --------------------- docs and help -----------------------------------

help:     ## Show this help.
	@sed -ne '/@sed/!s/## //p' $(MAKEFILE_LIST)

build_docs: ## build the full documentation

	# copy the run.py module to the back for it to be included in documentation 
	cp $(root_dir)/run.py $(root_dir)/back/run.py
	cp -r $(root_dir)/cli/ $(root_dir)/back/cli/

	# install pdoc3 and build docs
	docker run -v $(root_dir)/back:/back --env-file $(env_file) -it $(backend_img_sha) sh -c 'pip3 install pdoc3 && \
		PYTHONPATH=../back:../back/management/:../back/front/:../back/cli/:../back/tracking/:../back/emails/:../:./:$$PYTHONPATH \
		DJANGO_SETTINGS_MODULE=back.settings \
		pdoc3 --html --template-dir ./pdoc3 --force --html-dir ./html back front management tracking emails index.py run.py && \
		chown -R $(user_id):$(group_id) ./html'
	
	# remove the run.py module from the back folder
	rm $(root_dir)/back/run.py
	rm -rf $(root_dir)/back/cli/

	# move 'em ( using rsync so files are overwritten )
	mkdir -p $(root_dir)/docs
	rsync -a $(root_dir)/back/html/ $(root_dir)/docs/


watch_docs: ## watch back for changes in docs files and auto-rebuild ( be aware the build thakes a few seconds )
	while true; \
	do \
		inotifywait -e modify,create,delete,move -r $(root_dir)/back/ && $(MAKE) build_docs; \
	done

## --------------------- backend development --------------------------------

get_all_dev_containers:
	@echo "Container IDs: $(all_dev_container_ids)"
	@echo "Running Container IDs: $(running_dev_container_ids)"
	
kill_all_dev_containers:
	@echo "Killing all dev containers"
	@docker kill $(running_dev_container_ids)

start_redis: ## Start development redis instance
	docker run -p $(redis_port) --label "$(redis_label)=1" --label "$(dev_container_label)=1" -d $(redis_img) 
	
start_backend: ## Start development backend instance
	docker run -i --env-file $(env_file) -v $(root_dir)/back:/back -v $(root_dir)/front:/front --add-host=host.docker.internal:host-gateway -p $(backend_port) -t $(backend_tag) --label $(backend_label)
	
start_local_dev_backend:
	$(MAKE) start_redis
	$(MAKE) start_backend