import { Request, Response, NextFunction } from 'express';
import { ApiError } from '../utils/apiError.js';
import { envConfig } from '../config/env.config.js';

export const errorHandler = (
  err: Error | ApiError,
  _req: Request,
  res: Response,
  _next: NextFunction
): void => {
  if (err instanceof ApiError) {
    res.status(err.statusCode).json({
      success: false,
      message: err.message,
      errors: err.errors || [],
      timestamp: new Date().toISOString(),
      ...(envConfig.NODE_ENV === 'development' && { stack: err.stack }),
    });
    return;
  }

  console.error('Unhandled Exception:', err);

  res.status(500).json({
    success: false,
    message: 'Internal Server Error',
    timestamp: new Date().toISOString(),
    ...(envConfig.NODE_ENV === 'development' && { stack: err.stack }),
  });
};
