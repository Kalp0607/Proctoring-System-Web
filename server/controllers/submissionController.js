const Submission = require('../models/Submission');
const Test = require('../models/Test');
const Registration = require('../models/Registration');
const { executeCode } = require('../services/judge0Service');

// @desc    Start exam / get existing session
// @route   POST /api/submissions/start
// @access  Private (Examinee)
exports.startExam = async (req, res) => {
  try {
    const { testId } = req.body;
    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    const reg = await Registration.findOne({ testId: test._id, studentId: req.user._id, isRemoved: false });
    if (!reg) {
      return res.status(403).json({ message: 'Valid test registration required' });
    }

    let submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
    if (!submission) {
      submission = await Submission.create({
        testId: test._id,
        studentId: req.user._id,
        registrationId: reg._id,
        startedAt: new Date(),
        totalTestMarks: test.totalMarks,
        answers: [],
        proctoring: {
          riskLevel: 'Low',
          tabSwitchCount: 0,
          fullscreenExitCount: 0,
          violations: [],
        },
      });
    }

    res.json({
      submissionId: submission._id,
      startedAt: submission.startedAt,
      status: submission.status,
      answers: submission.answers,
      proctoring: submission.proctoring,
    });
  } catch (error) {
    console.error('Start exam error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Autosave answer for a question
// @route   POST /api/submissions/save
// @access  Private (Examinee)
exports.saveAnswer = async (req, res) => {
  try {
    const { testId, questionId, questionType, selectedOption, code, language } = req.body;

    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    // Check if test deadline already passed
    const now = new Date();
    if (now > new Date(test.endTime)) {
      return res.status(400).json({ message: 'Test end time has passed', timeUp: true });
    }

    const submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
    if (!submission || submission.status !== 'in_progress') {
      return res.status(400).json({ message: 'No active exam submission found' });
    }

    const existingAnsIndex = submission.answers.findIndex((a) => a.questionId === questionId);
    const answerData = {
      questionId,
      questionType,
      selectedOption: questionType === 'mcq' ? selectedOption : undefined,
      code: questionType === 'coding' ? code : undefined,
      language: questionType === 'coding' ? language : undefined,
    };

    if (existingAnsIndex > -1) {
      submission.answers[existingAnsIndex] = {
        ...submission.answers[existingAnsIndex].toObject(),
        ...answerData,
      };
    } else {
      submission.answers.push(answerData);
    }

    await submission.save();

    res.json({ success: true, message: 'Answer saved' });
  } catch (error) {
    console.error('Save answer error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Run code against sample test cases (Judge0)
// @route   POST /api/submissions/code-run
// @access  Private (Examinee)
exports.runCode = async (req, res) => {
  try {
    const { sourceCode, language, input, expectedOutput } = req.body;

    if (!sourceCode) {
      return res.status(400).json({ message: 'Source code is required' });
    }

    const result = await executeCode({
      sourceCode,
      language: language || 'javascript',
      stdin: input || '',
      expectedOutput: expectedOutput || '',
    });

    res.json(result);
  } catch (error) {
    console.error('Code run error:', error);
    res.status(500).json({ message: error.message || 'Execution error' });
  }
};

// @desc    Submit coding question solution and test against ALL test cases (including hidden)
// @route   POST /api/submissions/code-submit
// @access  Private (Examinee)
exports.submitCodeQuestion = async (req, res) => {
  try {
    const { testId, questionId, sourceCode, language } = req.body;

    if (!sourceCode) {
      return res.status(400).json({ message: 'Source code is required' });
    }

    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    const submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
    if (!submission) {
      return res.status(404).json({ message: 'Active exam submission not found' });
    }

    const question = test.questions.find((q) => q.id === questionId);
    if (!question || question.questionType !== 'coding') {
      return res.status(404).json({ message: 'Coding question not found' });
    }

    const testCases = question.testCases || [];
    let passedCount = 0;
    const results = [];
    let overallStatus = 'Accepted';
    let totalTime = 0;

    for (let i = 0; i < testCases.length; i++) {
      const tc = testCases[i];
      const execRes = await executeCode({
        sourceCode,
        language: language || question.language || 'javascript',
        stdin: tc.input || '',
        expectedOutput: tc.expectedOutput || '',
      });

      const execTimeNum = parseFloat(execRes.executionTime) || 0.05;
      totalTime += execTimeNum;

      if (execRes.passed) {
        passedCount++;
      } else {
        if (overallStatus === 'Accepted') {
          overallStatus = execRes.status || 'Wrong Answer';
        }
      }

      results.push({
        caseIndex: i + 1,
        passed: execRes.passed,
        isHidden: Boolean(tc.isHidden),
        status: execRes.status,
        executionTime: execRes.executionTime,
        input: tc.isHidden ? '[Hidden Testcase]' : (tc.input || '[Empty stdin]'),
        expectedOutput: tc.isHidden ? '[Hidden Output]' : tc.expectedOutput,
        actualOutput: tc.isHidden && !execRes.passed ? '[Hidden on failure]' : execRes.stdout,
        stderr: execRes.stderr,
      });
    }

    if (testCases.length === 0) {
      overallStatus = 'Accepted';
      passedCount = 0;
    } else if (passedCount === testCases.length) {
      overallStatus = 'Accepted';
    }

    // Persist code in submission.answers immediately so it counts as answered
    const existingAnsIndex = submission.answers.findIndex((a) => a.questionId === questionId);
    const answerData = {
      questionId,
      questionType: 'coding',
      code: sourceCode,
      language: language || question.language || 'javascript',
    };

    if (existingAnsIndex > -1) {
      submission.answers[existingAnsIndex] = {
        ...submission.answers[existingAnsIndex].toObject(),
        ...answerData,
      };
    } else {
      submission.answers.push(answerData);
    }

    await submission.save();

    res.json({
      success: true,
      status: overallStatus,
      totalCases: testCases.length,
      passedCases: passedCount,
      results,
      executionTime: (totalTime / Math.max(1, testCases.length)).toFixed(2) + 's',
      saved: true,
    });
  } catch (error) {
    console.error('Code submit error:', error);
    res.status(500).json({ message: error.message || 'Execution error' });
  }
};

// @desc    Log proctoring violation (tab-switch, fullscreen exit)
// @route   POST /api/submissions/violation
// @access  Private (Examinee)
exports.logViolation = async (req, res) => {
  try {
    const { testId, type, message } = req.body;
    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    const submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
    if (!submission) {
      return res.status(404).json({ message: 'Active exam submission not found' });
    }

    if (type === 'TAB_SWITCH') {
      submission.proctoring.tabSwitchCount = (submission.proctoring.tabSwitchCount || 0) + 1;
    } else if (type === 'FULLSCREEN_EXIT') {
      submission.proctoring.fullscreenExitCount = (submission.proctoring.fullscreenExitCount || 0) + 1;
    }

    submission.proctoring.violations.push({
      id: `viol_${Date.now()}`,
      type: type || 'OTHER',
      message: message || 'Proctoring violation event detected',
      timestamp: new Date(),
      severity: 'warning',
    });

    const totalBrowserViolations =
      (submission.proctoring.tabSwitchCount || 0) + (submission.proctoring.fullscreenExitCount || 0);

    // Rule: One warning allowed. 2nd violation -> Automatic submission.
    let mustAutoSubmit = false;
    if (totalBrowserViolations >= 2 && submission.status === 'in_progress') {
      mustAutoSubmit = true;
    }

    await submission.save();

    res.json({
      success: true,
      totalViolations: totalBrowserViolations,
      tabSwitchCount: submission.proctoring.tabSwitchCount,
      fullscreenExitCount: submission.proctoring.fullscreenExitCount,
      isWarning: totalBrowserViolations === 1,
      mustAutoSubmit,
    });
  } catch (error) {
    console.error('Log violation error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Submit test (manual or auto-submitted)
// @route   POST /api/submissions/submit
// @access  Private (Examinee)
exports.submitExam = async (req, res) => {
  try {
    const { testId, answers, reason } = req.body;
    const test = await Test.findOne({ testId: testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    let submission = await Submission.findOne({ testId: test._id, studentId: req.user._id });
    if (!submission) {
      return res.status(404).json({ message: 'Active exam submission not found' });
    }

    if (submission.status === 'submitted' || submission.status === 'auto_submitted') {
      return res.json({
        success: true,
        message: 'Exam was already submitted',
        submittedAt: submission.submittedAt,
        totalMarksObtained: submission.totalMarksObtained,
      });
    }

    // Merge answers if passed in payload
    if (answers && Array.isArray(answers)) {
      answers.forEach((ans) => {
        const matchingQ = test.questions.find((q) => q.id === ans.questionId);
        const qType = ans.questionType || (matchingQ ? matchingQ.questionType : 'mcq');
        const completeAns = { ...ans, questionType: qType };

        const idx = submission.answers.findIndex((a) => a.questionId === ans.questionId);
        if (idx > -1) {
          submission.answers[idx] = { ...submission.answers[idx].toObject(), ...completeAns };
        } else {
          submission.answers.push(completeAns);
        }
      });
    }

    // Evaluate answers
    let totalMarks = 0;

    for (const q of test.questions) {
      const qAns = submission.answers.find((a) => a.questionId === q.id);
      if (!qAns) continue;

      if (q.questionType === 'mcq') {
        const isCorrect = Number(qAns.selectedOption) === Number(q.correctOption);
        const marks = isCorrect ? Number(q.marks) : 0;
        qAns.marksAwarded = marks;
        totalMarks += marks;
      } else if (q.questionType === 'coding') {
        // Evaluate code against test cases
        if (qAns.code && qAns.code.trim()) {
          const testCases = q.testCases || [];
          if (testCases.length === 0) {
            qAns.marksAwarded = Number(q.marks);
            totalMarks += Number(q.marks);
          } else {
            let passedCount = 0;
            const details = [];

            for (let i = 0; i < testCases.length; i++) {
              const tc = testCases[i];
              try {
                const execRes = await executeCode({
                  sourceCode: qAns.code,
                  language: qAns.language || q.language || 'javascript',
                  stdin: tc.input || '',
                  expectedOutput: tc.expectedOutput || '',
                });

                if (execRes.passed) passedCount++;
                details.push({
                  testCaseIndex: i + 1,
                  passed: execRes.passed,
                  input: tc.isHidden ? '[Hidden Test Case]' : tc.input,
                  expectedOutput: tc.isHidden ? '[Hidden]' : tc.expectedOutput,
                  actualOutput: tc.isHidden ? (execRes.passed ? '[Passed]' : '[Failed]') : execRes.stdout,
                  error: execRes.stderr,
                });
              } catch (e) {
                details.push({
                  testCaseIndex: i + 1,
                  passed: false,
                  error: e.message,
                });
              }
            }

            const ratio = passedCount / testCases.length;
            const marks = Math.round(ratio * Number(q.marks) * 10) / 10;
            qAns.marksAwarded = marks;
            qAns.evaluationDetails = {
              testCasesTotal: testCases.length,
              testCasesPassed: passedCount,
              details,
            };
            totalMarks += marks;
          }
        } else {
          qAns.marksAwarded = 0;
        }
      }
    }

    const finalReason = reason || 'manual';
    submission.submittedAt = new Date();
    submission.status = finalReason === 'manual' ? 'submitted' : 'auto_submitted';
    submission.submissionReason = finalReason;
    submission.totalMarksObtained = totalMarks;
    submission.totalTestMarks = test.totalMarks;

    // Determine initial proctoring risk level based on violations
    const totalViolations =
      (submission.proctoring?.violations?.length || 0) +
      (submission.proctoring?.tabSwitchCount || 0) +
      (submission.proctoring?.fullscreenExitCount || 0);

    if (totalViolations >= 3) {
      submission.proctoring.riskLevel = 'High';
    } else if (totalViolations >= 1) {
      submission.proctoring.riskLevel = 'Medium';
    } else {
      submission.proctoring.riskLevel = 'Low';
    }

    await Submission.findByIdAndUpdate(submission._id, {
      answers: submission.answers,
      submittedAt: submission.submittedAt,
      status: submission.status,
      submissionReason: submission.submissionReason,
      totalMarksObtained: submission.totalMarksObtained,
      totalTestMarks: test.totalMarks,
      proctoring: submission.proctoring,
    });

    res.json({
      success: true,
      message: 'Exam submitted successfully',
      submissionId: submission._id,
      submittedAt: submission.submittedAt,
      status: submission.status,
      submissionReason: submission.submissionReason,
      totalMarksObtained: totalMarks,
      totalTestMarks: test.totalMarks,
    });
  } catch (error) {
    console.error('Submit exam error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};
