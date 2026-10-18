import express, { Application } from 'express';
import cors from 'cors';
import { envConfig } from './config/env.config.js';
import { requestLogger } from './middlewares/logger.middleware.js';
import { notFoundHandler } from './middlewares/notFound.middleware.js';
import { errorHandler } from './middlewares/errorHandler.middleware.js';
import { appRouter } from './routes/index.js';

export const createApp = (): Application => {
  const app = express();

  // Core Middlewares
  app.use(
    cors({
      origin: [envConfig.CLIENT_URL, 'http://localhost:5173', 'http://127.0.0.1:5173'],
      credentials: true,
    })
  );
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));
  app.use(requestLogger);

  // Mount API Routes
  app.use(envConfig.API_PREFIX, appRouter);

  // Catch 404
  app.use(notFoundHandler);

  // Centralized Error Handling
  app.use(errorHandler);

  return app;
};
