import { Request, Response, NextFunction } from 'express';

export const requestLogger = (req: Request, res: Response, next: NextFunction): void => {
  const start = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - start;
    const statusCode = res.statusCode;
    const color =
      statusCode >= 500
        ? '\x1b[31m' // red
        : statusCode >= 400
        ? '\x1b[33m' // yellow
        : statusCode >= 300
        ? '\x1b[36m' // cyan
        : '\x1b[32m'; // green

    console.log(
      `[${new Date().toISOString()}] ${req.method} ${req.originalUrl} ${color}${statusCode}\x1b[0m ${duration}ms`
    );
  });

  next();
};
