import { Router } from 'express';
import { taskRoutes } from './task.routes.js';
import { healthRoutes } from './health.routes.js';

const router = Router();

router.use('/tasks', taskRoutes);
router.use('/health', healthRoutes);

export const appRouter = router;
