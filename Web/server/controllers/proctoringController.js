const mongoose = require('mongoose');
const Submission = require('../models/Submission');
const Test = require('../models/Test');
const Registration = require('../models/Registration');

/**
 * Accurately finds the submission for a specific student without ever leaking
 * violations or session data across different students.
 */
async function findStudentSubmission(testInternalId, studentIdStr) {
  if (!studentIdStr) return null;

  // 1. Direct match by studentId (User ObjectId)
  if (mongoose.Types.ObjectId.isValid(studentIdStr)) {
    let sub = await Submission.findOne({ testId: testInternalId, studentId: studentIdStr });
    if (sub) return sub;

    // 2. Try match by registrationId (Registration ObjectId)
    sub = await Submission.findOne({ testId: testInternalId, registrationId: studentIdStr });
    if (sub) return sub;

    // 3. Look up Registration doc by _id to resolve its user studentId
    const reg = await Registration.findById(studentIdStr);
    if (reg && reg.studentId) {
      sub = await Submission.findOne({ testId: testInternalId, studentId: reg.studentId });
      if (sub) return sub;
    }
  }

  // 4. Fallback search via registration formData (e.g. roll number or email)
  const regByTest = await Registration.findOne({
    testId: testInternalId,
    $or: [
      { 'formData.roll_no': studentIdStr },
      { 'formData.email': studentIdStr },
      { 'formData.studentId': studentIdStr },
    ],
  });

  if (regByTest && regByTest.studentId) {
    const sub = await Submission.findOne({ testId: testInternalId, studentId: regByTest.studentId });
    if (sub) return sub;
  }

  return null;
}

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

    const submission = await findStudentSubmission(test._id, studentId);
    if (!submission) {
      console.warn(`[Proctoring] Active exam submission not found for studentId: ${studentId} in test: ${testId}`);
      return res.status(404).json({ message: `Active exam submission not found for student: ${studentId}` });
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
      studentId: submission.studentId,
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

    const submission = await findStudentSubmission(test._id, studentId);
    if (!submission) {
      console.warn(`[Proctoring] Submission not found for session summary of student: ${studentId}`);
      return res.status(404).json({ message: `Submission not found for student: ${studentId}` });
    }

    if (['Low', 'Medium', 'High'].includes(riskLevel)) {
      if (submission.proctoring.riskLevel === 'High' && riskLevel !== 'High') {
        const hasCritical = (submission.proctoring.violations || []).some(
          (v) => v.severity === 'critical' || ['PHONE_DETECTED', 'MULTIPLE_PEOPLE', 'IDENTITY_MISMATCH', 'FACE_MISMATCH'].includes(v.type)
        );
        if (!hasCritical) {
          submission.proctoring.riskLevel = riskLevel;
        }
      } else {
        submission.proctoring.riskLevel = riskLevel;
      }
    }

    if (notes) {
      submission.examinerReview.notes = notes;
    }

    await submission.save();

    res.json({
      success: true,
      message: 'Session summary updated',
      studentId: submission.studentId,
      riskLevel: submission.proctoring.riskLevel,
    });
  } catch (error) {
    console.error('Ingest summary error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};
