const express = require('express');
const router = express.Router();
const {
  startExam,
  saveAnswer,
  runCode,
  submitCodeQuestion,
  logViolation,
  submitExam,
} = require('../controllers/submissionController');
const { protect, authorize } = require('../middleware/auth');

router.post('/start', protect, authorize('examinee'), startExam);
router.post('/save', protect, authorize('examinee'), saveAnswer);
router.post('/code-run', protect, authorize('examinee'), runCode);
router.post('/code-submit', protect, authorize('examinee'), submitCodeQuestion);
router.post('/violation', protect, authorize('examinee'), logViolation);
router.post('/submit', protect, authorize('examinee'), submitExam);

module.exports = router;
