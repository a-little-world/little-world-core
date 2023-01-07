## Frontend development quick intro

All of little world js frontends are written in react ( there are also some html generated django admin views ).

React apps are developed using webpack dev server and build using webpack.
In production the bundles are injeted into django views.

The backend passes render data to a function in `src/index.js`.
The file `src/ENVIRONMENT.js` is to configure different frontend versions. This will be dynamicly replaced by the backend depending on build configuration.

### Starting the local development server

This is configured in `./webpack.config.js:devServer`.

```bash
npx webpack serve --env DEV_TOOL=eval-cheap-module-source-map --env DEBUG=1 --mode development
```

### local backend development using staging server api

We setup 3 routes api routes:

```bash
# bash `copy-paste` ( docker required )
# 1. download schroedingers-nginx.sh ( script to setup nginx docker container )
# 2. overwrite default script routes ( alternatively edit the script manually )
read -r -d '' ROUTES << EOM
SERVER_URL=( "host.docker.internal:3000" "s1.littleworld-test.com" "s1.littleworld-test.com/media/" )
PROXY_PATH=( "/" "/api/" "/media" )
SERVER_PATH=( "/" "/api/" "/media" )
EOM ; { echo "$ROUTES" ;wget -qO- https://raw.githubusercontent.com/tbscode/schroedingers-nginx/main/schrodingers-nginx.sh | tail -n 73 ;} > schrodingers-nginx.sh
```

The default development route is `localhost:3333`.
So we endup with:

```
localhost:3333/api -> <staging-server>/api
localhost:3333/media -> <staging-server>/media
localhost:3333/* -> <frontend>/* ( default: localhost:3000 )
```

You can test if the reverse proxy is working by calling some api e.g.:

```bash
./schrodingers-nginx.sh # <- start the nginx container
curl -X 'POST' \
  'https://localhost:3333/api/user/login/' \
  -H 'accept: */*' \
  -H 'Content-Type: application/json' \
  -d '{
  "email": "test1@user.de",
  "password": "Test123!"
}'
...
"Sucessfully logged in!"
```
