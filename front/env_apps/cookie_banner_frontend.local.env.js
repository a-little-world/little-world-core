exports.DEVELOPMENT = true; // this is more like FRONTEND_LOCAL_DEVELOPENT ( it's ment to be false, when use in backend local development )
exports.PRODUCTION = false; // This allows to render either by path or by callback name
exports.BACKEND_URL = this.DEVELOPMENT ? "http://localhost:3333" : "";