const express = require('express');
const router = express.Router();
const { ingestAIViolation, ingestAISessionSummary } = require('../controllers/proctoringController');
const upload = require('../middleware/upload');

// Ingestion endpoints for AI Proctoring system
router.post('/violation', upload.single('screenshot'), ingestAIViolation);
router.post('/session-summary', ingestAISessionSummary);

module.exports = router;
