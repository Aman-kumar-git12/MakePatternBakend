import { Request, Response, NextFunction } from 'express';
import { ApiError } from '../utils/apiError.js';
import { TaskPriority, TaskStatus } from '../types/task.types.js';

const VALID_STATUSES: TaskStatus[] = ['todo', 'in-progress', 'completed'];
const VALID_PRIORITIES: TaskPriority[] = ['low', 'medium', 'high'];

export const validateCreateTask = (req: Request, _res: Response, next: NextFunction): void => {
  const { title, status, priority } = req.body;
  const errors: string[] = [];

  if (!title || typeof title !== 'string' || title.trim() === '') {
    errors.push('Field "title" is required and must be a non-empty string.');
  }

  if (status && !VALID_STATUSES.includes(status)) {
    errors.push(`Field "status" must be one of: ${VALID_STATUSES.join(', ')}.`);
  }

  if (priority && !VALID_PRIORITIES.includes(priority)) {
    errors.push(`Field "priority" must be one of: ${VALID_PRIORITIES.join(', ')}.`);
  }

  if (errors.length > 0) {
    return next(ApiError.badRequest('Validation failed for create task request', errors));
  }

  next();
};

export const validateUpdateTask = (req: Request, _res: Response, next: NextFunction): void => {
  const { title, status, priority } = req.body;
  const errors: string[] = [];

  if (title !== undefined && (typeof title !== 'string' || title.trim() === '')) {
    errors.push('Field "title" must be a non-empty string when provided.');
  }

  if (status !== undefined && !VALID_STATUSES.includes(status)) {
    errors.push(`Field "status" must be one of: ${VALID_STATUSES.join(', ')}.`);
  }

  if (priority !== undefined && !VALID_PRIORITIES.includes(priority)) {
    errors.push(`Field "priority" must be one of: ${VALID_PRIORITIES.join(', ')}.`);
  }

  if (errors.length > 0) {
    return next(ApiError.badRequest('Validation failed for update task request', errors));
  }

  next();
};
