const mongoose = require('mongoose');

const violationItemSchema = new mongoose.Schema({
  id: { type: String },
  type: {
    type: String,
    enum: [
      'TAB_SWITCH',
      'FULLSCREEN_EXIT',
      'MULTIPLE_PEOPLE',
      'MULTIPLE_FACES',
      'PHONE_DETECTED',
      'BOOK_DETECTED',
      'LOOKING_AWAY',
      'MULTIPLE_SPEAKERS',
      'FACE_MISSING',
      'IDENTITY_MISMATCH',
      'FACE_MISMATCH',
      'OTHER',
    ],
    required: true,
  },
  message: { type: String, default: '' },
  timestamp: { type: Date, default: Date.now },
  screenshotUrl: { type: String, default: '' },
  durationSeconds: { type: Number, default: 0 },
  severity: { type: String, enum: ['info', 'warning', 'critical'], default: 'warning' },
});

const answerSchema = new mongoose.Schema({
  questionId: { type: String, required: true },
  questionType: { type: String, enum: ['mcq', 'coding'], required: true },
  selectedOption: { type: Number },
  code: { type: String, default: '' },
  language: { type: String, default: 'javascript' },
  marksAwarded: { type: Number, default: 0 },
  evaluationDetails: {
    testCasesTotal: { type: Number, default: 0 },
    testCasesPassed: { type: Number, default: 0 },
    details: [
      {
        testCaseIndex: Number,
        passed: Boolean,
        input: String,
        expectedOutput: String,
        actualOutput: String,
        error: String,
      },
    ],
  },
});

const submissionSchema = new mongoose.Schema(
  {
    testId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Test',
      required: true,
    },
    studentId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    registrationId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Registration',
    },
    startedAt: {
      type: Date,
      default: Date.now,
    },
    submittedAt: {
      type: Date,
    },
    status: {
      type: String,
      enum: ['in_progress', 'submitted', 'auto_submitted'],
      default: 'in_progress',
    },
    submissionReason: {
      type: String,
      enum: ['manual', 'time_up', 'violation_limit', 'in_progress'],
      default: 'in_progress',
    },
    answers: [answerSchema],
    totalMarksObtained: {
      type: Number,
      default: 0,
    },
    totalTestMarks: {
      type: Number,
      default: 0,
    },
    proctoring: {
      riskLevel: {
        type: String,
        enum: ['Low', 'Medium', 'High'],
        default: 'Low',
      },
      tabSwitchCount: {
        type: Number,
        default: 0,
      },
      fullscreenExitCount: {
        type: Number,
        default: 0,
      },
      violations: [violationItemSchema],
    },
    examinerReview: {
      isDisqualified: {
        type: Boolean,
        default: false,
      },
      disqualificationReason: {
        type: String,
        default: '',
      },
      finalMarks: {
        type: Number,
      },
      notes: {
        type: String,
        default: '',
      },
      reviewedAt: {
        type: Date,
      },
    },
  },
  { timestamps: true }
);

// One submission per student per test
submissionSchema.index({ testId: 1, studentId: 1 }, { unique: true });

module.exports = mongoose.model('Submission', submissionSchema);
