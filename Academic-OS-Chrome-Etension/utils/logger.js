// logger.js — shared logging utility. Classic script (no import/export),
// loaded before every other module via importScripts (background) or
// manifest content_scripts ordering.
//
// Production logging control: set CONFIG.DEBUG = false (default) to
// silence info/debug output. warn/error always print — you want those
// in the field when a user reports a bug, DEBUG flag or not.

const Logger = {
  _prefix(level) {
    return `[AcademicOS:${level}]`;
  },

  debug(...args) {
    if (typeof CONFIG !== "undefined" && CONFIG.DEBUG) {
      console.debug(this._prefix("debug"), ...args);
    }
  },

  info(...args) {
    if (typeof CONFIG !== "undefined" && CONFIG.DEBUG) {
      console.info(this._prefix("info"), ...args);
    }
  },

  warn(...args) {
    console.warn(this._prefix("warn"), ...args);
  },

  error(...args) {
    console.error(this._prefix("error"), ...args);
  }
};

if (typeof globalThis !== "undefined") globalThis.Logger = Logger;
