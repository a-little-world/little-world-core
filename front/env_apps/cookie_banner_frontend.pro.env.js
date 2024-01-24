exports.DEVELOPMENT = false; // this is more like FRONTEND_LOCAL_DEVELOPENT ( it's ment to be false, when use in backend local development )
exports.PRODUCTION = true; // This allows to render either by path or by callback name
exports.DEFAULT_LOGIN_USERNAME = this.DEVELOPMENT
  ? 'benjamin.tim@gmx.de'
  : 'nopeHeAintExistInProduction:)';
exports.DEFAULT_LOGIN_PASSWORD = this.DEVELOPMENT
  ? 'Test123'
  : 'aPassYouCantUse:)';
// We HAVE TO explicitly specify `https://little-world.com` here, because it can be served via sub domain
exports.BACKEND_URL = this.DEVELOPMENT ? 'http://localhost:3333' : 'https://little-world.com';
exports.STORYBOOK = false;
