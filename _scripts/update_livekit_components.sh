#!/bin/bash

# if ./front/components-js exists, 
# remove `./packages/react/*.tgz` and `./packages/react/dist` 
# also `./packages/react/node_modules` ( seems like cash is causing issues otherwise )
# don't fail if the files don't exist
if [ -d "./components-js" ]; then
  rm -rf ./components-js/packages/react/*.tgz || true
  rm -rf ./components-js/packages/react/dist || true
else
  git clone https://github.com/a-little-world/components-js
fi

cd components-js
pnpm install
pnpm build:react
# add a random version number to the package.json
VERSION=$(python3 -c "import json; f=open('./packages/react/package.json'); data=json.load(f); v=data['version'].split('.'); v[-1]=str(int(v[-1])+1); print('.'.join(v)); f.close()")
python3 -c """
import json
f = open('./packages/react/package.json', 'r+')
data = json.load(f)
data['version'] = '$VERSION'
f.seek(0)
json.dump(data, f, indent=4)
f.truncate()
f.close()
"""
cd ./packages/react && pnpm pack
echo "Created ./components-js/packages/react/livekit-components-react-$VERSION.tgz"
cd ../../..
pwd
if [ ! -d "./front" ]; then
    # just so we are def in the root dir!
    exit 0
fi
rm ./front/apps/main_fontend/prebuild/livekit-components-react-*.tgz || true
cp ./components-js/packages/react/livekit-components-react-$VERSION.tgz ./front/apps/main_frontend/prebuild/livekit-components-react-$VERSION.tgz
# modify main frontend package.json to use the new version
python3 -c """
import json
f = open('./front/apps/main_frontend/package.json', 'r+')
data = json.load(f)
data['dependencies']['@livekit/components-react'] = 'file:prebuild/livekit-components-react-$VERSION.tgz'
f.seek(0)
json.dump(data, f, indent=4)
f.truncate()
f.close()
"""
echo "Setup complete, please run 'npm install' in the main frontend"
echo "Also to update the upsteam version commit the new livekit-components-react-$VERSION.tgz file and commit the updated package.json in the main frontend."