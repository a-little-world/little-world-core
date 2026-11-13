exports.DEVELOPMENT = false; // this is more like FRONTEND_LOCAL_DEVELOPENT ( it's ment to be false, when use in backend local development )
exports.PRODUCTION = true; // This allows to render either by path or by callback name
exports.DEFAULT_LOGIN_USERNAME = this.DEVELOPMENT
  ? 'benjamin.tim@gmx.de'
  : 'nopeHeAintExistInProduction:)';
exports.DEFAULT_LOGIN_PASSWORD = this.DEVELOPMENT
  ? 'Test123'
  : 'aPassYouCantUse:)';
// This defaults to production because the banner may be served from another subdomain.
exports.BACKEND_URL =
  process.env.COOKIE_BANNER_BACKEND_URL || 'https://little-world.com';
exports.STORYBOOK = false;
