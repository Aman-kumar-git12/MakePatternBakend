import { Request, Response } from 'express';
import { ApiResponse } from '../utils/apiResponse.js';
import { envConfig } from '../config/env.config.js';

class HealthController {
  checkHealth(_req: Request, res: Response): void {
    const healthStatus = {
      status: 'OK',
      uptime: process.uptime(),
      timestamp: new Date().toISOString(),
      environment: envConfig.NODE_ENV,
      nodeVersion: process.version,
    };

    ApiResponse.success(res, healthStatus, 'System is healthy and operational');
  }
}

export const healthController = new HealthController();
