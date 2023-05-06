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
setup_repo: not_initialized := $(shell git submodule foreach 'if [ ! -f $$toplevel/$$path/.git ]; then echo 1; fi' | grep -q 1 && echo 1 || echo 0)


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

# frontend container setup
frontends := user_form_frontend,main_frontend,cookie_banner_frontend,admin_panel_frontend
frontend_build_all_dev: build_type := dev

## --------------------- docs and help -----------------------------------
##  

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

	# move generated documentation ( using rsync so files are overwritten )
	mkdir -p $(root_dir)/docs
	rsync -a $(root_dir)/back/html/ $(root_dir)/docs/


watch_docs: ## watch back for changes in docs files and auto-rebuild ( be aware the build thakes a few seconds )
	while true; \
	do \
		inotifywait -e modify,create,delete,move -r $(root_dir)/back/ && $(MAKE) build_docs; \
	done

## --------------------- initial setup --------------------------------------
##  

setup_repo: ## run after repo was cloned, initalized submodules and build development containers
	@echo "Setting up repo"
	@echo "1. Clone all submodules"
	@if [ $(not_initialized) -eq 1 ]; then \
	  echo "At least one submodule not initalized initalizing"; \
	  git submodule update --init --recursive; \
	else \
	  echo "Submodules are already initalized, doing nothing ..."; \
	fi
	@echo "2. Building frontend development container"

## --------------------- backend development --------------------------------
##  

get_all_dev_containers: ## print summary of all dev containers build / running
	@echo "Little world dev containers:"
	@echo "All Container IDs: $(all_dev_container_ids)"
	@echo "Running Container IDs: $(running_dev_container_ids)"
	
kill_all_dev_containers: ## kill all running dev containers
	@echo "Killing all dev containers"
	docker kill $(running_dev_container_ids)

start_redis: ## Start development redis instance
	docker run -p $(redis_port) --label "$(redis_label)=1" --label "$(dev_container_label)=1" -d $(redis_img) 
	
start_backend: ## Start development backend instance
	docker run --env-file $(env_file) -v $(root_dir)/back:/back -v $(root_dir)/front:/front --label "$(dev_container_label)=1" --label "$(backend_label)=1" --add-host=host.docker.internal:host-gateway -p $(backend_port) -t $(backend_tag) 
	
build_backend: ## rebuild the django backend ( only required if dependencies are updated )
	docker build -f Dockerfile.dev -t $(backend_tag) ./back
	
backend_static: ## extract static files for django backend
	docker run --env-file $(env_file) -v $(root_dir)/back:/back -v $(root_dir)/front:/front --label "$(dev_container_label)=1" --label "$(backend_label)=1" --add-host=host.docker.internal:host-gateway -p $(backend_port) -t $(backend_tag) \
		sh -c 'python3 manage.py collectstatic --noinput --verbosity 3'

backend_make_migrations: ## generate migrations files ( use when models changed )
	docker run --env-file $(env_file) -v $(root_dir)/back:/back -v $(root_dir)/front:/front --label "$(dev_container_label)=1" --label "$(backend_label)=1" --add-host=host.docker.internal:host-gateway -p $(backend_port) -t $(backend_tag) \
		sh -c 'python3 manage.py makemigrations --noinput --verbosity 3'
	
backend_apply_migrations: ## apply migrations ( before: make sure there are no conflicting or wrong migrations )
	docker run --env-file $(env_file) -v $(root_dir)/back:/back -v $(root_dir)/front:/front --label "$(dev_container_label)=1" --label "$(backend_label)=1" --add-host=host.docker.internal:host-gateway -p $(backend_port) -t $(backend_tag) \
		sh -c 'python3 manage.py migrate --noinput --verbosity 3'

backend_migrate: ## make and apply migrations ( only use if sure there can be no conflicting or wrong migrations, else use make, then check or modify migrations, then apply )
	$(MAKE) backend_make_migrations
	$(MAKE) backend_apply_migrations
	
frontend_build_dev: ## build the development frontend container
	pass

frontend_build_all_dev: ## build development frontend container and all frontends webpack bundles
	# this assumes all frontend are listed comma seperated in 'frontends' above
	# for each frontend a webpack config file is expected at 'front/webpack.<frontend>.config.js'
	# if that frontends `ENVIRONMENT.js` should be overwritten a file at `front/env_apps/<frontend>.<build_type>.env.js` is expected
	# the frontends must reside at `front/apps/<frontend>/` and build scripts must be defined in `front/apps/<frontend>/package.json`
	@echo "Building frontend development containers and webpack bundles"
	@echo ${frontends} | tr ',' '\n' | while read item; do \
	  echo "Processing frontend: $$item"; \
	  config_path="front/webpack.$$item.config.js"; \
	  env_path="front/env_apps/$$item.$$build_type.env.js"; \
	  echo "1. Checking env replacement, checking '$$config_path'"; \
	  if [ -e "$$config_path" ]; then \
	    echo "File $$config_path exists, starting webpack build ..."; \
	  else \
	    echo "ERROR $$config_path does not exist, repo is setup wrong or the frontend '$$item' doesn't exist"; \
	  fi; \
	  if [ -e "$$env_path" ]; then \
	  	replace_env=""./front/apps/$$item/src/ENVIRONMENT.js" \
	    echo "File '$$env_path' exists, replacing it as frontend ENV file"; \
	  else \
	    echo "No extra ENV file found at '$$env_path' using env as is"; \
	  fi; \
	done
	
frontend_webpack_build: ## Build webpack bundle for ONE of the frontend MUST provide front=name e.g.: `make frontend_webpack_build front=main_frontend`
	pass

	
	
start_local_dev_backend: ## start all development containers attach to output ( automaticly kills all dev containers on ctl-C )
	$(MAKE) start_redis
	$(MAKE) start_backend &
	# press ctl-C to kill all dev containers
	-@sh -c 'trap "echo \"\nReceived Ctrl+C. Killing containers...\"; $(MAKE) kill_all_dev_containers; exit" INT; echo "Press Ctrl+C to stop containers..."; while :; do sleep 1; done'
