exports.DEVELOPMENT = false; // this is more like FRONTEND_LOCAL_DEVELOPENT ( it's ment to be false, when use in backend local development )
exports.PRODUCTION = true; // This allows to render either by path or by callback name
exports.DEFAULT_LOGIN_USERNAME = this.DEVELOPMENT
  ? 'benjamin.tim@gmx.de'
  : 'nopeHeAintExistInProduction:)';
exports.DEFAULT_LOGIN_PASSWORD = this.DEVELOPMENT
  ? 'Test123'
  : 'aPassYouCantUse:)';
exports.BACKEND_URL =
  process.env.COOKIE_BANNER_BACKEND_URL || 'http://localhost:8000';
exports.STORYBOOK = false;
