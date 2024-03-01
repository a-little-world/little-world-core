# First replace the env; main_frontend, cookie_banner_frontend, admin_panel_frontend
cp /front/env_apps/$1.dev.env.js /front/apps/$1/src/ENVIRONMENT.js

./node_modules/.bin/webpack --watch --env PUBLIC_PATH= --env DEV_TOOL=eval-cheap-module-source-map --env DEBUG=1 --mode development --config webpack.$1.config.js