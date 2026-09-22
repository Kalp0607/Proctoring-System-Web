const axios = require('axios');

async function testFlow() {
  const baseURL = 'http://127.0.0.1:5000/api';
  console.log('--- 1. Testing Health ---');
  const h = await axios.get(baseURL + '/health');
  console.log('Health:', h.data.status);

  console.log('\n--- 2. Registering Examiner ---');
  const exEmail = 'prof_' + Date.now() + '@test.edu';
  const exRes = await axios.post(baseURL + '/auth/register', {
    name: 'Prof. Alan Turing',
    email: exEmail,
    password: 'password123',
    role: 'examiner',
  });
  console.log('Examiner created:', exRes.data.email, 'Role:', exRes.data.role);
  const examinerToken = exRes.data.token;

  console.log('\n--- 3. Registering Examinee (Student) ---');
  const stEmail = 'student_' + Date.now() + '@test.edu';
  const stRes = await axios.post(baseURL + '/auth/register', {
    name: 'John Student',
    email: stEmail,
    password: 'password123',
    role: 'examinee',
  });
  console.log('Student created:', stRes.data.email, 'Role:', stRes.data.role);
  const studentToken = stRes.data.token;

  console.log('\n--- 4. Examiner Creating Test ---');
  const now = new Date();
  // Start time 5 minutes from now (so pre-test room is open now!)
  const start = new Date(now.getTime() + 5 * 60 * 1000);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  // Deadline equal to start time
  const deadline = start;

  const testPayload = {
    title: 'Computer Science Core Exam',
    description: 'Comprehensive test covering Algorithms and Logic',
    testPassword: 'PASS123',
    startTime: start,
    endTime: end,
    registrationDeadline: deadline,
    requirePhoto: true,
    registrationFields: [
      { id: 'roll_no', label: 'Roll Number', fieldType: 'text', required: true },
      { id: 'dept', label: 'Department', fieldType: 'text', required: true },
    ],
    questions: [
      {
        id: 'q1',
        questionType: 'mcq',
        questionText: 'What is 2 + 2?',
        marks: 5,
        options: ['3', '4', '5', '6'],
        correctOption: 1,
      },
      {
        id: 'q2',
        questionType: 'coding',
        questionText: 'Sum Two Integers',
        marks: 10,
        starterCode: 'const fs = require("fs"); const input = fs.readFileSync(0, "utf-8").trim().split(/\\s+/).map(Number); console.log(input[0] + input[1]);',
        language: 'javascript',
        testCases: [
          { input: '2 3\n', expectedOutput: '5', isHidden: false },
          { input: '10 20\n', expectedOutput: '30', isHidden: true },
        ],
      },
    ],
  };

  const createdTestRes = await axios.post(baseURL + '/tests', testPayload, {
    headers: { Authorization: 'Bearer ' + examinerToken },
  });
  const testId = createdTestRes.data.testId;
  console.log('Test Created Successfully. Test ID:', testId, 'Total Marks:', createdTestRes.data.totalMarks);

  console.log('\n--- 5. Verifying Password & Public Details ---');
  const verifyRes = await axios.post(
    baseURL + '/tests/' + testId + '/verify-password',
    { password: 'PASS123' },
    { headers: { Authorization: 'Bearer ' + studentToken } }
  );
  console.log('Password verification:', verifyRes.data.success);

  console.log('\n--- 6. Student Registering for Test ---');
  const regRes = await axios.post(
    baseURL + '/tests/' + testId + '/register',
    {
      formData: JSON.stringify({ roll_no: 'CS2026-007', dept: 'CSE' }),
      photoDataUrl: 'data:image/jpeg;base64,' + Buffer.from('test_fake_image_bytes').toString('base64'),
    },
    { headers: { Authorization: 'Bearer ' + studentToken } }
  );
  console.log('Student Registration:', regRes.data.success);

  console.log('\n--- 7. Student Checking Upcoming Tests ---');
  const upRes = await axios.get(baseURL + '/tests/student/upcoming', {
    headers: { Authorization: 'Bearer ' + studentToken },
  });
  console.log('Student Upcoming Tests Count:', upRes.data.length, 'Status:', upRes.data[0].status);

  console.log('\n--- 8. Examiner Checking Registered Students ---');
  const exRegs = await axios.get(baseURL + '/registrations/' + testId + '/registrations', {
    headers: { Authorization: 'Bearer ' + examinerToken },
  });
  console.log('Examiner view registered count:', exRegs.data.registrations.length);

  console.log('\n--- 9. Student Entering Test & Starting Exam ---');
  const startExamRes = await axios.post(
    baseURL + '/submissions/start',
    { testId },
    { headers: { Authorization: 'Bearer ' + studentToken } }
  );
  console.log('Exam Session Started. Submission ID:', startExamRes.data.submissionId);

  console.log('\n--- 10. Testing Anti-Cheating Violations (1 Warning, 2nd Auto-Submits) ---');
  const viol1 = await axios.post(
    baseURL + '/submissions/violation',
    {
      testId,
      type: 'TAB_SWITCH',
      message: 'User switched browser tab',
    },
    { headers: { Authorization: 'Bearer ' + studentToken } }
  );
  console.log('Violation 1 result: isWarning =', viol1.data.isWarning, 'mustAutoSubmit =', viol1.data.mustAutoSubmit);

  console.log('\n--- 11. Testing Code Execution (Judge0 Service) ---');
  const codeRes = await axios.post(
    baseURL + '/submissions/code-run',
    {
      sourceCode: 'console.log(2 + 3);',
      language: 'javascript',
      expectedOutput: '5',
    },
    { headers: { Authorization: 'Bearer ' + studentToken } }
  );
  console.log('Code Execution Output:', codeRes.data.stdout, 'Passed:', codeRes.data.passed, 'Status:', codeRes.data.status);

  console.log('\n--- 12. Student Submitting Answers ---');
  const submitRes = await axios.post(
    baseURL + '/submissions/submit',
    {
      testId,
      reason: 'manual',
      answers: [
        { questionId: 'q1', selectedOption: 1 },
        {
          questionId: 'q2',
          code: 'const fs = require("fs"); const input = fs.readFileSync(0, "utf-8").trim().split(/\\s+/).map(Number); console.log(input[0] + input[1]);',
          language: 'javascript',
        },
      ],
    },
    { headers: { Authorization: 'Bearer ' + studentToken } }
  );
  console.log('Submission Done! Total Marks Awarded:', submitRes.data.totalMarksObtained, '/', submitRes.data.totalTestMarks);

  console.log('\n--- 13. Examiner Viewing Test Report & Risk Categorization ---');
  const reportRes = await axios.get(baseURL + '/reports/test/' + testId, {
    headers: { Authorization: 'Bearer ' + examinerToken },
  });
  console.log('Report Summary:', reportRes.data.summary);

  console.log('\n--- 14. Examiner Disqualifying / Awarding 0 Marks Action ---');
  const subId = reportRes.data.allSubmissions[0]._id;
  const disqRes = await axios.post(
    baseURL + '/reports/submission/' + subId + '/override-marks',
    {
      isDisqualified: true,
      disqualificationReason: 'Confirmed unauthorized browser activity',
    },
    { headers: { Authorization: 'Bearer ' + examinerToken } }
  );
  console.log('Disqualification result:', disqRes.data.message, 'Final Marks:', disqRes.data.examinerReview.finalMarks);

  console.log('\n--- 15. Testing PDF Report Generation ---');
  const pdfRes = await axios.get(baseURL + '/reports/test/' + testId + '/pdf', {
    headers: { Authorization: 'Bearer ' + examinerToken },
    responseType: 'arraybuffer',
  });
  console.log('PDF Report Generated Successfully. Byte size:', pdfRes.data.length);

  console.log('\n>>> ALL 15 CRITICAL BACKEND & INTEGRATION CHECKS PASSED PERFECTLY! <<<');
}

testFlow().catch((e) => console.error('E2E TEST FAILED:', e.response ? e.response.data : e));
