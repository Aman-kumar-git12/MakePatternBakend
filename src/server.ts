import { createApp } from './app.js';
import { envConfig } from './config/env.config.js';

const app = createApp();

const server = app.listen(envConfig.PORT, () => {
  console.log(`
🚀 Server successfully started!
📡 Environment: ${envConfig.NODE_ENV}
🌐 Listening on: http://localhost:${envConfig.PORT}
🔗 API Base: http://localhost:${envConfig.PORT}${envConfig.API_PREFIX}
📋 Health Check: http://localhost:${envConfig.PORT}${envConfig.API_PREFIX}/health
✅ Tasks API: http://localhost:${envConfig.PORT}${envConfig.API_PREFIX}/tasks
  `);
});

// Graceful shutdown handlers
const shutdown = (signal: string) => {
  console.log(`\nReceived ${signal}. Shutting down gracefully...`);
  server.close(() => {
    console.log('HTTP server closed.');
    process.exit(0);
  });

  // Force close if taking too long
  setTimeout(() => {
    console.error('Forced shutdown due to timeout.');
    process.exit(1);
  }, 10000);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
