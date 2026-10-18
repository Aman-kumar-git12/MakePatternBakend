import { Task, CreateTaskDTO, UpdateTaskDTO, TaskFilterQuery } from '../types/task.types.js';
import { ApiError } from '../utils/apiError.js';
import crypto from 'crypto';

class TaskService {
  // In-memory data store seeded with standard initial tasks
  private tasks: Task[] = [
    {
      id: 'task-101',
      title: 'Initialize Express + TypeScript backend',
      description: 'Set up modular routes, controllers, middlewares, and services with strict types.',
      status: 'completed',
      priority: 'high',
      createdAt: new Date(Date.now() - 3600000 * 2).toISOString(),
      updatedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
    },
    {
      id: 'task-102',
      title: 'Configure Vite & Tailwind CSS',
      description: 'Structure frontend with component hierarchy, API services, and responsive design.',
      status: 'in-progress',
      priority: 'medium',
      createdAt: new Date(Date.now() - 3600000).toISOString(),
      updatedAt: new Date(Date.now() - 3600000).toISOString(),
    },
    {
      id: 'task-103',
      title: 'Integrate Environment Variables (.env)',
      description: 'Add API endpoint URLs and server configuration variables to .env and .env.example.',
      status: 'todo',
      priority: 'low',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
  ];

  async getAllTasks(filter?: TaskFilterQuery): Promise<Task[]> {
    let result = [...this.tasks];

    if (filter?.status) {
      result = result.filter((task) => task.status === filter.status);
    }

    if (filter?.priority) {
      result = result.filter((task) => task.priority === filter.priority);
    }

    if (filter?.search) {
      const q = filter.search.toLowerCase();
      result = result.filter(
        (task) =>
          task.title.toLowerCase().includes(q) ||
          task.description.toLowerCase().includes(q)
      );
    }

    // Sort newest first
    return result.sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );
  }

  async getTaskById(id: string): Promise<Task> {
    const task = this.tasks.find((t) => t.id === id);
    if (!task) {
      throw ApiError.notFound(`Task with ID "${id}" was not found.`);
    }
    return task;
  }

  async createTask(dto: CreateTaskDTO): Promise<Task> {
    const now = new Date().toISOString();
    const newTask: Task = {
      id: `task-${crypto.randomUUID().slice(0, 8)}`,
      title: dto.title.trim(),
      description: dto.description?.trim() || '',
      status: dto.status || 'todo',
      priority: dto.priority || 'medium',
      createdAt: now,
      updatedAt: now,
    };

    this.tasks.unshift(newTask);
    return newTask;
  }

  async updateTask(id: string, dto: UpdateTaskDTO): Promise<Task> {
    const taskIndex = this.tasks.findIndex((t) => t.id === id);
    if (taskIndex === -1) {
      throw ApiError.notFound(`Task with ID "${id}" was not found.`);
    }

    const existingTask = this.tasks[taskIndex];
    const updatedTask: Task = {
      ...existingTask,
      title: dto.title !== undefined ? dto.title.trim() : existingTask.title,
      description: dto.description !== undefined ? dto.description.trim() : existingTask.description,
      status: dto.status !== undefined ? dto.status : existingTask.status,
      priority: dto.priority !== undefined ? dto.priority : existingTask.priority,
      updatedAt: new Date().toISOString(),
    };

    this.tasks[taskIndex] = updatedTask;
    return updatedTask;
  }

  async deleteTask(id: string): Promise<void> {
    const taskIndex = this.tasks.findIndex((t) => t.id === id);
    if (taskIndex === -1) {
      throw ApiError.notFound(`Task with ID "${id}" was not found.`);
    }

    this.tasks.splice(taskIndex, 1);
  }
}

export const taskService = new TaskService();
