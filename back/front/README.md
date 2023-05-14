## Frontend Development

All of Little World's JavaScript frontends are written in React (there are also some HTML-generated Django admin views).

React apps are developed using the Webpack Dev Server and built using Webpack. In production, the bundles are injected into Django views.

The backend passes render data to a function in `src/index.js`. The file `src/ENVIRONMENT.js` is used to configure different frontend versions. This will be dynamically replaced by the backend depending on the build configuration.

### TL;DR

```bash
# Start routing to staging API server (localhost:3333/api/* -> s1.littleworld-test.com/api/*)
./schrodingers-nginx.sh
# Start Webpack server (localhost:3000)
npx webpack serve --env DEV_TOOL=eval-cheap-module-source-map --env DEBUG=1 --mode development
# Start developing view frontend at `localhost:3333/`
```

### Starting the Local Development Server

This is configured in `./webpack.config.js:devServer`.

```bash
npx webpack serve --env DEV_TOOL=eval-cheap-module-source-map --env DEBUG=1 --mode development
```

### Local Backend Development Using Staging Server API

> Note: Your frontend might already provide a custom `schroedingers-nginx.sh` setup. In that case, you will not need to perform the next steps.

We set up 3 API routes:

```bash
# bash `copy-paste` (Docker required)
# 1. Download schroedingers-nginx.sh (script to set up Nginx Docker container)
# 2. Overwrite default script routes (alternatively, edit the script manually)
read -r -d '' ROUTES << EOM
SERVER_URL=("host.docker.internal:3000" "s1.littleworld-test.com" "s1.littleworld-test.com/media/")
PROXY_PATH=("/" "/api/" "/media")
SERVER_PATH=("/" "/api/" "/media")
EOM ; { echo "$ROUTES" ;wget -qO- https://raw.githubusercontent.com/tbscode/schroedingers-nginx/main/schrodingers-nginx.sh | tail -n 73 ;} > schrodingers-nginx.sh
```

The default development route is `localhost:3333`. So we end up with:

```
localhost:3333/api -> <staging-server>/api
localhost:3333/media -> <staging-server>/media
localhost:3333/* -> <frontend>/* (default: localhost:3000)
```

You can test if the reverse proxy is working by calling some API, e.g.:

```bash
./schrodingers-nginx.sh # <- Start the Nginx container
curl -X 'POST' \
  'https://localhost:3333/api/user/login/' \
  -H 'accept: */*' \
  -H 'Content-Type: application/json' \
  -d '{
  "email": "test1@user.de",
  "password": "Test123!"
}'
...
"Successfully logged in!"
```
