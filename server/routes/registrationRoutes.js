const express = require('express');
const router = express.Router();
const { getTestRegistrations, removeStudentFromTest } = require('../controllers/registrationController');
const { protect, authorize } = require('../middleware/auth');

router.get('/:testId/registrations', protect, authorize('examiner'), getTestRegistrations);
router.delete('/:testId/registrations/:registrationId', protect, authorize('examiner'), removeStudentFromTest);

module.exports = router;
