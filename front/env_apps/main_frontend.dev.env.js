exports.DEVELOPMENT = false; // this is more like FRONTEND_LOCAL_DEVELOPENT ( it's ment to be false, when use in backend local development )
// Yeah I know this is somewhat redundant, but there is a difference between backend-dev and frontend-dev
// e.g.: we need to use 'wss' for websocket in production but 'ws' in both frontend and backend localdev
exports.PRODUCTION = false;
exports.DEFAULT_LOGIN_USERNAME = this.DEVELOPMENT
  ? 'benjamin.tim@gmx.de'
  : 'nopeHeAintExistInProduction:)';
exports.DEFAULT_LOGIN_PASSWORD = this.DEVELOPMENT
  ? 'Test123'
  : 'aPassYouCantUse:)';
exports.BACKEND_URL = this.DEVELOPMENT ? 'http://localhost:81' : '';
exports.BACKEND_PATH = this.DEVELOPMENT ? '' : '/app';
exports.CORE_WS_SHEME = this.PRODUCTION ? 'ws://' : 'wss://';
exports.CORE_WS_PATH = '/api/core/ws';