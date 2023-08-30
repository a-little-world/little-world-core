# First replace the env; main_frontend, user_form, user_form_frontend, cookie_banner_frontend, admin_panel_frontend
cp /front/env_apps/main_frontend.dev.env.js /front/apps/main_frontend/src/ENVIROMENT.js
cp /front/env_apps/user_form_frontend.dev.env.js /front/apps/user_form_frontend/src/ENVIROMENT.js
cp /front/env_apps/user_form.dev.env.js /front/apps/user_form/src/ENVIROMENT.js
cp /front/env_apps/cookie_banner_frontend.dev.env.js /front/apps/cookie_banner_frontend/src/ENVIROMENT.js
cp /front/env_apps/admin_panel_frontend.dev.env.js /front/apps/admin_panel_frontend/src/ENVIROMENT.js

./node_modules/.bin/webpack --watch --env PUBLIC_PATH= --env DEV_TOOL=eval-cheap-module-source-map --env DEBUG=1 --mode development --config webpack.$1.config.js