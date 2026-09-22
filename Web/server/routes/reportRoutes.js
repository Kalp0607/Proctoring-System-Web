const express = require('express');
const router = express.Router();
const { getTestReport, overrideMarks, downloadTestPDF } = require('../controllers/reportController');
const { protect, authorize } = require('../middleware/auth');

router.get('/test/:testId', protect, authorize('examiner'), getTestReport);
router.post('/submission/:submissionId/override-marks', protect, authorize('examiner'), overrideMarks);
router.get('/test/:testId/pdf', protect, authorize('examiner'), downloadTestPDF);

module.exports = router;
