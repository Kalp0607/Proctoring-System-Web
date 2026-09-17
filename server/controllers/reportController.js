const Test = require('../models/Test');
const Submission = require('../models/Submission');
const Registration = require('../models/Registration');
const { generateTestReportPDF } = require('../services/pdfService');

// @desc    Get detailed test report for examiner
// @route   GET /api/reports/test/:testId
// @access  Private (Examiner only)
exports.getTestReport = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() }).populate('examinerId', 'name email');
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    if (test.examinerId._id.toString() !== req.user._id.toString()) {
      return res.status(403).json({ message: 'Not authorized to view report for this test' });
    }

    // Fetch all registrations
    const registrations = await Registration.find({ testId: test._id }).populate('studentId', 'name email');

    // Fetch all submissions
    const submissions = await Submission.find({ testId: test._id })
      .populate('studentId', 'name email')
      .populate('registrationId')
      .sort({ submittedAt: -1 });

    const totalRegistered = registrations.length;
    const totalAppeared = submissions.length;

    let totalMarksSum = 0;
    let highRisk = [];
    let mediumRisk = [];
    let lowRisk = [];

    const enrichedSubmissions = submissions.map((sub) => {
      const reg = registrations.find((r) => r.studentId?._id?.toString() === sub.studentId?._id?.toString());
      const effectiveMarks = sub.examinerReview?.isDisqualified
        ? 0
        : sub.examinerReview?.finalMarks !== undefined
        ? sub.examinerReview.finalMarks
        : sub.totalMarksObtained;

      totalMarksSum += effectiveMarks || 0;

      const risk = sub.proctoring?.riskLevel || 'Low';
      const item = {
        ...sub.toObject(),
        effectiveMarks,
        registrationData: reg ? reg.formData : {},
        photoUrl: reg ? reg.photoUrl : '',
      };

      if (risk === 'High') highRisk.push(item);
      else if (risk === 'Medium') mediumRisk.push(item);
      else lowRisk.push(item);

      return item;
    });

    const averageMarks = totalAppeared > 0 ? (totalMarksSum / totalAppeared).toFixed(1) : 0;

    res.json({
      test: {
        _id: test._id,
        testId: test.testId,
        title: test.title,
        description: test.description,
        startTime: test.startTime,
        endTime: test.endTime,
        totalMarks: test.totalMarks,
        questions: test.questions,
        examiner: test.examinerId,
      },
      summary: {
        totalRegistered,
        totalAppeared,
        averageMarks,
        highRiskCount: highRisk.length,
        mediumRiskCount: mediumRisk.length,
        lowRiskCount: lowRisk.length,
        disqualifiedCount: submissions.filter((s) => s.examinerReview?.isDisqualified).length,
      },
      categorizedByRisk: {
        highRisk,
        mediumRisk,
        lowRisk,
      },
      allSubmissions: enrichedSubmissions,
    });
  } catch (error) {
    console.error('Get test report error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Examiner reviews student and overrides marks (e.g. 0 marks for cheating)
// @route   POST /api/reports/submission/:submissionId/override-marks
// @access  Private (Examiner only)
exports.overrideMarks = async (req, res) => {
  try {
    const { isDisqualified, disqualificationReason, finalMarks, notes } = req.body;
    const submission = await Submission.findById(req.params.submissionId).populate('testId');

    if (!submission) {
      return res.status(404).json({ message: 'Submission not found' });
    }

    // Verify examiner ownership
    if (submission.testId.examinerId.toString() !== req.user._id.toString()) {
      return res.status(403).json({ message: 'Not authorized to review this submission' });
    }

    submission.examinerReview = {
      isDisqualified: !!isDisqualified,
      disqualificationReason: isDisqualified ? disqualificationReason || 'Cheating violation detected' : '',
      finalMarks: isDisqualified ? 0 : finalMarks !== undefined ? Number(finalMarks) : submission.totalMarksObtained,
      notes: notes || '',
      reviewedAt: new Date(),
    };

    await submission.save();

    res.json({
      success: true,
      message: isDisqualified ? 'Student disqualified with 0 marks' : 'Submission marks updated',
      examinerReview: submission.examinerReview,
    });
  } catch (error) {
    console.error('Override marks error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Download PDF Report for a test
// @route   GET /api/reports/test/:testId/pdf
// @access  Private (Examiner only)
exports.downloadTestPDF = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() }).populate('examinerId', 'name email');
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    if (test.examinerId._id.toString() !== req.user._id.toString()) {
      return res.status(403).json({ message: 'Not authorized to download report for this test' });
    }

    const registrations = await Registration.find({ testId: test._id }).populate('studentId', 'name email');
    const submissions = await Submission.find({ testId: test._id })
      .populate('studentId', 'name email')
      .sort({ submittedAt: -1 });

    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="report_${test.testId}.pdf"`);

    generateTestReportPDF({ test, submissions, registrations, res });
  } catch (error) {
    console.error('Download PDF error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};
