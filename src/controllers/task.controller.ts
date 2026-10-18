import { Request, Response, NextFunction } from 'express';
import { taskService } from '../services/task.service.js';
import { ApiResponse } from '../utils/apiResponse.js';
import { TaskFilterQuery } from '../types/task.types.js';

class TaskController {
  async getAllTasks(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const filter: TaskFilterQuery = {
        status: req.query.status as TaskFilterQuery['status'],
        priority: req.query.priority as TaskFilterQuery['priority'],
        search: req.query.search as string,
      };

      const tasks = await taskService.getAllTasks(filter);
      ApiResponse.success(res, tasks, 'Tasks retrieved successfully');
    } catch (error) {
      next(error);
    }
  }

  async getTaskById(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const { id } = req.params;
      const task = await taskService.getTaskById(id);
      ApiResponse.success(res, task, 'Task retrieved successfully');
    } catch (error) {
      next(error);
    }
  }

  async createTask(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const newTask = await taskService.createTask(req.body);
      ApiResponse.created(res, newTask, 'Task created successfully');
    } catch (error) {
      next(error);
    }
  }

  async updateTask(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const { id } = req.params;
      const updatedTask = await taskService.updateTask(id, req.body);
      ApiResponse.success(res, updatedTask, 'Task updated successfully');
    } catch (error) {
      next(error);
    }
  }

  async deleteTask(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const { id } = req.params;
      await taskService.deleteTask(id);
      ApiResponse.success(res, { id }, 'Task deleted successfully');
    } catch (error) {
      next(error);
    }
  }
}

export const taskController = new TaskController();
