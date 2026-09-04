module.exports = {
  '/api': {
    target: 'http://localhost:10000',
    secure: false,
    timeout: 300000,
    proxyTimeout: 300000,
  },
};

