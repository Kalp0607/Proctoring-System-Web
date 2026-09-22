const Test = require('../models/Test');
const Registration = require('../models/Registration');
const Submission = require('../models/Submission');
const { customAlphabet } = require('nanoid');
const nanoid = customAlphabet('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', 6);

// Helper to generate unique Test ID
const generateUniqueTestId = async () => {
  let isUnique = false;
  let testId = '';
  while (!isUnique) {
    testId = `TEST-${nanoid()}`;
    const existing = await Test.findOne({ testId });
    if (!existing) isUnique = true;
  }
  return testId;
};

// @desc    Create a new test
// @route   POST /api/tests
// @access  Private (Examiner only)
exports.createTest = async (req, res) => {
  try {
    const {
      title,
      description,
      testPassword,
      startTime,
      endTime,
      registrationDeadline,
      registrationFields,
      requirePhoto,
      questions,
    } = req.body;

    if (!title || !testPassword || !startTime || !endTime || !registrationDeadline) {
      return res.status(400).json({ message: 'Please provide all required test fields' });
    }

    const start = new Date(startTime);
    const end = new Date(endTime);
    const deadline = new Date(registrationDeadline);

    if (start >= end) {
      return res.status(400).json({ message: 'End time must be after start time' });
    }

    if (deadline > start) {
      return res.status(400).json({ message: 'Registration deadline must be before or at test start time' });
    }

    const testId = await generateUniqueTestId();

    const formattedQuestions = (questions || []).map((q, idx) => ({
      id: q.id || `q_${idx + 1}_${Date.now()}`,
      questionType: q.questionType,
      questionText: q.questionText,
      marks: Number(q.marks) || 1,
      options: q.options || [],
      correctOption: q.correctOption !== undefined ? Number(q.correctOption) : 0,
      description: q.description || '',
      starterCode: q.starterCode || '// Write your solution here\n',
      language: q.language || 'javascript',
      testCases: (q.testCases || []).map((tc) => ({
        input: tc.input || '',
        expectedOutput: tc.expectedOutput || '',
        isHidden: !!tc.isHidden,
      })),
    }));

    const formattedFields = (registrationFields || []).map((f, idx) => ({
      id: f.id || `field_${idx + 1}`,
      label: f.label,
      fieldType: f.fieldType || 'text',
      required: f.required !== false,
    }));

    const test = await Test.create({
      testId,
      title,
      description,
      examinerId: req.user._id,
      testPassword,
      startTime: start,
      endTime: end,
      registrationDeadline: deadline,
      registrationFields: formattedFields,
      requirePhoto: requirePhoto !== false,
      questions: formattedQuestions,
    });

    res.status(201).json(test);
  } catch (error) {
    console.error('Create test error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Get all tests created by the logged in examiner
// @route   GET /api/tests/examiner
// @access  Private (Examiner only)
exports.getExaminerTests = async (req, res) => {
  try {
    const tests = await Test.find({ examinerId: req.user._id }).sort({ createdAt: -1 });

    // Fetch registration and submission counts for each test
    const enrichedTests = await Promise.all(
      tests.map(async (t) => {
        const registrationCount = await Registration.countDocuments({ testId: t._id, isRemoved: false });
        const submissionCount = await Submission.countDocuments({ testId: t._id });
        return {
          ...t.toObject(),
          registrationCount,
          submissionCount,
        };
      })
    );

    res.json(enrichedTests);
  } catch (error) {
    console.error('Get examiner tests error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Get public test details for student entry/registration
// @route   GET /api/tests/:testId/details
// @access  Public / Authenticated
exports.getPublicTestDetails = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() })
      .populate('examinerId', 'name email')
      .select('-testPassword -questions.correctOption -questions.testCases');

    if (!test) {
      return res.status(404).json({ message: 'Test not found with this ID' });
    }

    // Check if user is already registered
    let isRegistered = false;
    let isRemoved = false;
    if (req.user) {
      const existingReg = await Registration.findOne({ testId: test._id, studentId: req.user._id });
      if (existingReg) {
        isRegistered = true;
        isRemoved = existingReg.isRemoved;
      }
    }

    res.json({
      test,
      isRegistered,
      isRemoved,
    });
  } catch (error) {
    console.error('Get test details error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Verify test password
// @route   POST /api/tests/:testId/verify-password
// @access  Private
exports.verifyTestPassword = async (req, res) => {
  try {
    const { password } = req.body;
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() });

    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    if (test.testPassword !== password) {
      return res.status(400).json({ message: 'Incorrect test password' });
    }

    res.json({ success: true, message: 'Password verified successfully' });
  } catch (error) {
    console.error('Verify password error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Register examinee for test
// @route   POST /api/tests/:testId/register
// @access  Private (Examinee)
exports.registerForTest = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    // Validate registration deadline
    const now = new Date();
    if (now > new Date(test.registrationDeadline)) {
      return res.status(400).json({ message: 'Registration deadline for this test has already passed' });
    }

    // Check if already registered
    let registration = await Registration.findOne({ testId: test._id, studentId: req.user._id });
    if (registration) {
      if (registration.isRemoved) {
        return res.status(403).json({ message: 'You were removed from this test by the examiner' });
      }
      return res.status(400).json({ message: 'You are already registered for this test' });
    }

    // Parse form data
    let formData = {};
    if (req.body.formData) {
      try {
        formData = typeof req.body.formData === 'string' ? JSON.parse(req.body.formData) : req.body.formData;
      } catch (_) {
        formData = req.body.formData;
      }
    }

    // Check required fields
    for (const field of test.registrationFields) {
      if (field.required && (!formData[field.id] || !formData[field.id].toString().trim())) {
        return res.status(400).json({ message: `Field '${field.label}' is required` });
      }
    }

    // Photo file
    let photoUrl = '';
    if (req.file) {
      photoUrl = `/uploads/${req.file.filename}`;
    } else if (req.body.photoDataUrl) {
      // Base64 snapshot fallback from webcam
      const base64Data = req.body.photoDataUrl.replace(/^data:image\/\w+;base64,/, '');
      const buffer = Buffer.from(base64Data, 'base64');
      const filename = `photo-webcam-${Date.now()}-${Math.round(Math.random() * 1e9)}.jpg`;
      const fs = require('fs');
      const path = require('path');
      const filepath = path.join(__dirname, '../uploads', filename);
      fs.writeFileSync(filepath, buffer);
      photoUrl = `/uploads/${filename}`;
    }

    if (test.requirePhoto && !photoUrl) {
      return res.status(400).json({ message: 'Student photo is required for test registration' });
    }

    registration = await Registration.create({
      testId: test._id,
      studentId: req.user._id,
      formData,
      photoUrl,
    });

    res.status(201).json({
      success: true,
      message: 'Successfully registered for the test',
      registration,
    });
  } catch (error) {
    console.error('Register for test error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Get upcoming tests for student
// @route   GET /api/tests/student/upcoming
// @access  Private (Examinee)
exports.getStudentUpcomingTests = async (req, res) => {
  try {
    const registrations = await Registration.find({
      studentId: req.user._id,
      isRemoved: false,
    }).populate({
      path: 'testId',
      populate: { path: 'examinerId', select: 'name email' },
    });

    const now = new Date();

    const upcoming = await Promise.all(
      registrations
        .filter((r) => r.testId) // filter out deleted tests
        .map(async (reg) => {
          const test = reg.testId;
          const preTestTime = new Date(new Date(test.startTime).getTime() - 15 * 60 * 1000);

          let status = 'upcoming'; // default
          if (now < preTestTime) {
            status = 'upcoming';
          } else if (now >= preTestTime && now < new Date(test.startTime)) {
            status = 'pre_test_open'; // 15 min window open
          } else if (now >= new Date(test.startTime) && now <= new Date(test.endTime)) {
            status = 'active'; // exam ongoing
          } else {
            status = 'ended';
          }

          // Check if student has already submitted
          const submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
          const hasSubmitted = submission && (submission.status === 'submitted' || submission.status === 'auto_submitted');

          return {
            registrationId: reg._id,
            registeredAt: reg.registeredAt,
            photoUrl: reg.photoUrl,
            formData: reg.formData,
            test: {
              _id: test._id,
              testId: test.testId,
              title: test.title,
              description: test.description,
              examiner: test.examinerId,
              startTime: test.startTime,
              endTime: test.endTime,
              totalMarks: test.totalMarks,
              questionCount: test.questions.length,
            },
            status,
            hasSubmitted,
            submission: hasSubmitted ? {
              submittedAt: submission.submittedAt,
              marks: submission.examinerReview?.isDisqualified ? 0 : submission.examinerReview?.finalMarks ?? submission.totalMarksObtained,
              isDisqualified: submission.examinerReview?.isDisqualified,
            } : null,
          };
        })
    );

    // Sort by startTime ascending
    upcoming.sort((a, b) => new Date(a.test.startTime) - new Date(b.test.startTime));

    res.json(upcoming);
  } catch (error) {
    console.error('Get upcoming tests error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Get test panel data for taking the exam (Pre-test panel or active test)
// @route   GET /api/tests/:testId/take
// @access  Private (Examinee)
exports.getTestForExam = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() })
      .populate('examinerId', 'name email');

    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    // Verify registration
    const registration = await Registration.findOne({ testId: test._id, studentId: req.user._id });
    if (!registration) {
      return res.status(403).json({ message: 'You must register for this test before entering' });
    }
    if (registration.isRemoved) {
      return res.status(403).json({ message: 'You have been removed from this test by the examiner' });
    }

    const now = new Date();
    const preTestStart = new Date(new Date(test.startTime).getTime() - 15 * 60 * 1000);
    const testEnd = new Date(test.endTime);

    // Timing check: can only enter within pre-test window or during active test
    if (now < preTestStart) {
      return res.status(400).json({
        message: 'Pre-test panel will open 15 minutes before the test start time',
        preTestStart,
        startTime: test.startTime,
      });
    }

    if (now > testEnd) {
      return res.status(400).json({ message: 'This test has already concluded' });
    }

    // Check submission status
    let submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
    if (submission && (submission.status === 'submitted' || submission.status === 'auto_submitted')) {
      return res.status(400).json({
        message: 'You have already submitted this test',
        submittedAt: submission.submittedAt,
        alreadySubmitted: true,
      });
    }

    // Sanitize questions for student view (do not expose correct options or hidden test cases)
    const sanitizedQuestions = test.questions.map((q) => {
      const base = {
        id: q.id,
        questionType: q.questionType,
        questionText: q.questionText,
        marks: q.marks,
      };

      if (q.questionType === 'mcq') {
        base.options = q.options;
      } else if (q.questionType === 'coding') {
        base.description = q.description;
        base.starterCode = q.starterCode;
        base.language = q.language;
        // Expose only non-hidden sample test cases for testing
        base.sampleTestCases = (q.testCases || [])
          .filter((tc) => !tc.isHidden)
          .map((tc) => ({ input: tc.input, expectedOutput: tc.expectedOutput }));
      }
      return base;
    });

    res.json({
      test: {
        _id: test._id,
        testId: test.testId,
        title: test.title,
        description: test.description,
        examiner: test.examinerId,
        startTime: test.startTime,
        endTime: test.endTime,
        totalMarks: test.totalMarks,
      },
      registration: {
        _id: registration._id,
        photoUrl: registration.photoUrl,
        formData: registration.formData,
      },
      questions: sanitizedQuestions,
      currentServerTime: new Date(),
    });
  } catch (error) {
    console.error('Get test for exam error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Delete a test permanently along with registrations and submissions
// @route   DELETE /api/tests/:testId
// @access  Private (Examiner only)
exports.deleteTest = async (req, res) => {
  try {
    const { testId } = req.params;
    const test = await Test.findOne({ testId });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    // Verify test belongs to examiner
    if (test.examinerId.toString() !== req.user._id.toString()) {
      return res.status(403).json({ message: 'Not authorized to delete this test' });
    }

    // Cascade delete associated registrations and submissions
    await Registration.deleteMany({ testId: test._id });
    await Submission.deleteMany({ testId: test._id });
    await Test.deleteOne({ _id: test._id });

    res.json({ message: 'Test and all associated records deleted permanently' });
  } catch (error) {
    console.error('Delete test error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

