const Submission = require('../models/Submission');
const Test = require('../models/Test');

// @desc    Ingest real-time violation event from AI proctoring system (future-proof)
// @route   POST /api/proctoring/violation
// @access  Public or Protected with API token
exports.ingestAIViolation = async (req, res) => {
  try {
    const { testId, studentId, type, message, duration_seconds, similarity } = req.body;

    if (!testId || !studentId || !type) {
      return res.status(400).json({ message: 'testId, studentId, and type are required' });
    }

    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    let submission = await Submission.findOne({ testId: test._id, studentId });
    if (!submission) {
      submission = await Submission.findOne({ testId: test._id, registrationId: studentId });
    }
    if (!submission) {
      // Fallback: try finding by user _id if studentId was passed as string or registration
      submission = await Submission.findOne({ testId: test._id }).sort({ createdAt: -1 });
    }
    if (!submission) {
      return res.status(404).json({ message: 'Active exam submission not found' });
    }

    let screenshotUrl = '';
    // Looking Away is the only exception: do not attach any screenshot
    if (type !== 'LOOKING_AWAY') {
      if (req.file) {
        screenshotUrl = `/uploads/${req.file.filename}`;
      } else if (req.body.screenshotUrl) {
        screenshotUrl = req.body.screenshotUrl;
      }
    }

    const highRiskTypes = ['PHONE_DETECTED', 'MULTIPLE_PEOPLE', 'IDENTITY_MISMATCH', 'FACE_MISMATCH', 'MULTIPLE_SPEAKERS'];

    const violation = {
      id: `ai_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
      type,
      message: message || (type === 'IDENTITY_MISMATCH' || type === 'FACE_MISMATCH' ? 'Face Mismatch violation detected' : `AI detected: ${type}`),
      timestamp: new Date(),
      screenshotUrl: type === 'LOOKING_AWAY' ? '' : screenshotUrl,
      durationSeconds: Number(duration_seconds) || 0,
      severity: highRiskTypes.includes(type) ? 'critical' : 'warning',
    };

    submission.proctoring.violations.push(violation);

    // Auto-escalate risk level based on AI detections
    if (highRiskTypes.includes(type) || submission.proctoring.violations.length >= 3) {
      submission.proctoring.riskLevel = 'High';
    } else if (submission.proctoring.violations.length >= 1 && submission.proctoring.riskLevel !== 'High') {
      submission.proctoring.riskLevel = 'Medium';
    }

    await submission.save();

    res.status(201).json({
      success: true,
      message: 'Violation recorded',
      currentRiskLevel: submission.proctoring.riskLevel,
      totalViolations: submission.proctoring.violations.length,
    });
  } catch (error) {
    console.error('Ingest violation error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Ingest AI session summary and risk classification
// @route   POST /api/proctoring/session-summary
// @access  Public or Protected with API token
exports.ingestAISessionSummary = async (req, res) => {
  try {
    const { testId, studentId, riskLevel, notes } = req.body;

    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    let submission = await Submission.findOne({ testId: test._id, studentId });
    if (!submission) {
      submission = await Submission.findOne({ testId: test._id, registrationId: studentId });
    }
    if (!submission) {
      return res.status(404).json({ message: 'Submission not found' });
    }

    if (['Low', 'Medium', 'High'].includes(riskLevel)) {
      submission.proctoring.riskLevel = riskLevel;
    }

    if (notes) {
      submission.examinerReview.notes = notes;
    }

    await submission.save();

    res.json({
      success: true,
      message: 'Session summary updated',
      riskLevel: submission.proctoring.riskLevel,
    });
  } catch (error) {
    console.error('Ingest summary error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};
