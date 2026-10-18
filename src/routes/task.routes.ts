import { Router } from 'express';
import { taskController } from '../controllers/task.controller.js';
import { validateCreateTask, validateUpdateTask } from '../middlewares/validate.middleware.js';

const router = Router();

router.get('/', (req, res, next) => taskController.getAllTasks(req, res, next));
router.get('/:id', (req, res, next) => taskController.getTaskById(req, res, next));
router.post('/', validateCreateTask, (req, res, next) => taskController.createTask(req, res, next));
router.put('/:id', validateUpdateTask, (req, res, next) => taskController.updateTask(req, res, next));
router.delete('/:id', (req, res, next) => taskController.deleteTask(req, res, next));

export const taskRoutes = router;
