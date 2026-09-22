const express = require('express');
const router = express.Router();
const {
  createTest,
  getExaminerTests,
  getPublicTestDetails,
  verifyTestPassword,
  registerForTest,
  getStudentUpcomingTests,
  getTestForExam,
  deleteTest,
} = require('../controllers/testController');
const { protect, authorize } = require('../middleware/auth');
const upload = require('../middleware/upload');

// Examiner routes
router.post('/', protect, authorize('examiner'), createTest);
router.get('/examiner', protect, authorize('examiner'), getExaminerTests);
router.delete('/:testId', protect, authorize('examiner'), deleteTest);

// Student routes
router.get('/student/upcoming', protect, authorize('examinee'), getStudentUpcomingTests);
router.get('/:testId/take', protect, authorize('examinee'), getTestForExam);
router.post('/:testId/register', protect, authorize('examinee'), upload.single('photo'), registerForTest);

// Shared / verification routes
router.get('/:testId/details', protect, getPublicTestDetails);
router.post('/:testId/verify-password', protect, verifyTestPassword);

module.exports = router;
