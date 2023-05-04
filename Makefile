root_dir := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
backend_img_sha := $(shell docker images -q littleworld_back.dev:latest)
env_file := $(root_dir)/env
user_id := $(shell id -u)
group_id := $(shell id -g)

build_docs:
	# install pdoc3 and build docs
	docker run -v $(root_dir)/back:/back --env-file $(env_file) -it $(backend_img_sha) sh -c 'pip3 install pdoc3 && \
		PYTHONPATH=../back:../back/management/:../back/tracking/:../back/emails/:../:./:$$PYTHONPATH \
		DJANGO_SETTINGS_MODULE=back.settings \
		pdoc3 --html --template-dir ./pdoc3 --force --html-dir ./html back management tracking emails index.py && \
		chown -R $(user_id):$(group_id) ./html'

	# move 'em
	mkdir -p $(root_dir)/docs
	rsync -a $(root_dir)/back/html/ $(root_dir)/docs/
	
watch_docs:
	while true; \
	do \
		inotifywait -e modify,create,delete,move -r $(root_dir)/back/ && $(MAKE) build_docs; \
	done