import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';
import {
  ArrowLeft,
  Plus,
  Trash2,
  CheckCircle2,
  Code2,
  HelpCircle,
  Clock,
  KeyRound,
  FileCheck,
  AlertCircle,
  Camera,
  Layers,
} from 'lucide-react';

export default function CreateTest() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Default dates: start tomorrow at 10:00 AM, end at 11:00 AM, registration deadline today 8:00 PM
  const now = new Date();
  const defaultStart = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  defaultStart.setHours(10, 0, 0, 0);
  const defaultEnd = new Date(defaultStart.getTime() + 60 * 60 * 1000);
  const defaultDeadline = new Date(now.getTime() + 12 * 60 * 60 * 1000);

  const formatDateForInput = (d) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    testPassword: Math.random().toString(36).substring(2, 8).toUpperCase(),
    startTime: formatDateForInput(defaultStart),
    endTime: formatDateForInput(defaultEnd),
    registrationDeadline: formatDateForInput(defaultDeadline),
    requirePhoto: true,
  });

  // Dynamic registration fields defined by Examiner
  const [regFields, setRegFields] = useState([
    { id: 'roll_number', label: 'Roll Number / Student ID', fieldType: 'text', required: true },
    { id: 'department', label: 'Department / Branch', fieldType: 'text', required: true },
  ]);

  // Questions
  const [questions, setQuestions] = useState([
    {
      id: `q_1`,
      questionType: 'mcq',
      questionText: 'What is the time complexity of binary search on a sorted array of length n?',
      marks: 2,
      options: ['O(n)', 'O(log n)', 'O(n log n)', 'O(1)'],
      correctOption: 1,
      description: '',
      starterCode: '',
      language: 'javascript',
      testCases: [],
    },
    {
      id: `q_2`,
      questionType: 'coding',
      questionText: 'Two Sum Problem',
      marks: 10,
      options: [],
      correctOption: 0,
      description: 'Given an array of integers and an integer target, write a script that reads two space-separated numbers and prints their sum.',
      starterCode: '// JavaScript Node environment\nconst readline = require("readline");\nconst rl = readline.createInterface({ input: process.stdin });\nrl.on("line", (line) => {\n  const [a, b] = line.trim().split(" ").map(Number);\n  console.log(a + b);\n});\n',
      language: 'javascript',
      testCases: [
        { input: '3 5\n', expectedOutput: '8', isHidden: false },
        { input: '10 25\n', expectedOutput: '35', isHidden: false },
        { input: '-4 9\n', expectedOutput: '5', isHidden: true },
      ],
    },
  ]);

  const addRegField = () => {
    const id = `field_${Date.now()}`;
    setRegFields([...regFields, { id, label: '', fieldType: 'text', required: true }]);
  };

  const updateRegField = (index, key, val) => {
    const updated = [...regFields];
    updated[index][key] = val;
    setRegFields(updated);
  };

  const removeRegField = (index) => {
    setRegFields(regFields.filter((_, i) => i !== index));
  };

  const addQuestion = (type) => {
    const id = `q_${Date.now()}`;
    if (type === 'mcq') {
      setQuestions([
        ...questions,
        {
          id,
          questionType: 'mcq',
          questionText: '',
          marks: 1,
          options: ['', '', '', ''],
          correctOption: 0,
          description: '',
          starterCode: '',
          language: 'javascript',
          testCases: [],
        },
      ]);
    } else {
      setQuestions([
        ...questions,
        {
          id,
          questionType: 'coding',
          questionText: '',
          marks: 5,
          options: [],
          correctOption: 0,
          description: '',
          starterCode: '// Write your solution here\n',
          language: 'javascript',
          testCases: [{ input: '', expectedOutput: '', isHidden: false }],
        },
      ]);
    }
  };

  const updateQuestion = (index, key, val) => {
    const updated = [...questions];
    updated[index][key] = val;
    setQuestions(updated);
  };

  const updateMcqOption = (qIndex, optIndex, val) => {
    const updated = [...questions];
    updated[qIndex].options[optIndex] = val;
    setQuestions(updated);
  };

  const addTestCase = (qIndex) => {
    const updated = [...questions];
    updated[qIndex].testCases.push({ input: '', expectedOutput: '', isHidden: false });
    setQuestions(updated);
  };

  const updateTestCase = (qIndex, tcIndex, key, val) => {
    const updated = [...questions];
    updated[qIndex].testCases[tcIndex][key] = val;
    setQuestions(updated);
  };

  const removeTestCase = (qIndex, tcIndex) => {
    const updated = [...questions];
    updated[qIndex].testCases = updated[qIndex].testCases.filter((_, i) => i !== tcIndex);
    setQuestions(updated);
  };

  const removeQuestion = (index) => {
    setQuestions(questions.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!formData.title.trim()) {
      setError('Please enter a test title');
      return;
    }

    if (new Date(formData.startTime) >= new Date(formData.endTime)) {
      setError('Test end time must be after start time');
      return;
    }

    if (new Date(formData.registrationDeadline) > new Date(formData.startTime)) {
      setError('Registration deadline must be before or equal to test start time');
      return;
    }

    if (questions.length === 0) {
      setError('Please add at least one question (MCQ or Coding)');
      return;
    }

    // Validate questions
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      if (!q.questionText.trim()) {
        setError(`Question #${i + 1} prompt cannot be empty`);
        return;
      }
      if (q.questionType === 'mcq') {
        if (q.options.some((opt) => !opt.trim())) {
          setError(`Please fill in all options for MCQ Question #${i + 1}`);
          return;
        }
      }
    }

    setLoading(true);

    try {
      const payload = {
        ...formData,
        registrationFields: regFields,
        questions,
      };

      const created = await api.createTest(payload);
      navigate(`/examiner/test/${created.testId}/share`);
    } catch (err) {
      setError(err.message || 'Failed to create test');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', paddingBottom: 64 }}>
      <div style={{ marginBottom: 24 }}>
        <Link to="/examiner/dashboard" className="btn btn-secondary btn-sm" style={{ marginBottom: 16 }}>
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em' }}>Create New Examination</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
          Configure test timings, custom registration requirements, and author question papers.
        </p>
      </div>

      {error && (
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {/* Section 1: Basic Information */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <div>
              <h2 className="card-title">1. Test Information & Access</h2>
              <p className="card-subtitle">Title, description, and test passcode</p>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="title">
              Test Title <span className="req">*</span>
            </label>
            <input
              id="title"
              type="text"
              className="form-control"
              placeholder="e.g. Data Structures & Algorithms Mid-Term Exam"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="description">
              Instructions & Overview
            </label>
            <textarea
              id="description"
              className="form-control"
              placeholder="Provide instructions regarding permitted reference materials, full-screen rules, etc."
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="testPassword">
                Test Entry Password <span className="req">*</span>
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  id="testPassword"
                  type="text"
                  className="form-control"
                  value={formData.testPassword}
                  onChange={(e) => setFormData({ ...formData, testPassword: e.target.value })}
                  style={{ fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}
                  required
                />
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() =>
                    setFormData({
                      ...formData,
                      testPassword: Math.random().toString(36).substring(2, 8).toUpperCase(),
                    })
                  }
                >
                  Regenerate
                </button>
              </div>
              <div className="form-hint">Students must enter this password to unlock test registration and entry.</div>
            </div>
          </div>
        </div>

        {/* Section 2: Timing & Deadlines */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <div>
              <h2 className="card-title">2. Test Timing & Deadlines</h2>
              <p className="card-subtitle">Pre-test room opens 15 minutes before Start Time; auto-submits strictly at End Time</p>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="startTime">
                Test Start Time <span className="req">*</span>
              </label>
              <input
                id="startTime"
                type="datetime-local"
                className="form-control"
                value={formData.startTime}
                onChange={(e) => setFormData({ ...formData, startTime: e.target.value })}
                required
              />
              <div className="form-hint">Late entry allowed, but end time remains fixed.</div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="endTime">
                Test End Time (Strict Cutoff) <span className="req">*</span>
              </label>
              <input
                id="endTime"
                type="datetime-local"
                className="form-control"
                value={formData.endTime}
                onChange={(e) => setFormData({ ...formData, endTime: e.target.value })}
                required
              />
              <div className="form-hint">All active exams will be auto-submitted at this moment.</div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="registrationDeadline">
                Registration Deadline <span className="req">*</span>
              </label>
              <input
                id="registrationDeadline"
                type="datetime-local"
                className="form-control"
                value={formData.registrationDeadline}
                onChange={(e) => setFormData({ ...formData, registrationDeadline: e.target.value })}
                required
              />
              <div className="form-hint">Students cannot enroll after this deadline.</div>
            </div>
          </div>
        </div>

        {/* Section 3: Student Registration Specification */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <div>
              <h2 className="card-title">3. Student Registration Requirements</h2>
              <p className="card-subtitle">Define what information students must provide when registering for this test</p>
            </div>
            <button type="button" onClick={addRegField} className="btn btn-secondary btn-sm">
              <Plus size={14} /> Add Custom Field
            </button>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 14.5 }}>
              <input
                type="checkbox"
                checked={formData.requirePhoto}
                onChange={(e) => setFormData({ ...formData, requirePhoto: e.target.checked })}
                style={{ width: 18, height: 18, accentColor: 'var(--primary)' }}
              />
              <span style={{ fontWeight: 500 }}>
                Request Student Photo during registration (Required for future AI face-verification)
              </span>
            </label>
            <div className="form-hint" style={{ marginLeft: 28 }}>
              Students will take a live webcam snapshot or upload their student ID photo.
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {regFields.map((field, index) => (
              <div
                key={field.id || index}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 140px 100px 40px',
                  gap: 12,
                  alignItems: 'center',
                  background: 'var(--bg-subtle)',
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                <div>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Field label e.g. College Enrollment Number"
                    value={field.label}
                    onChange={(e) => updateRegField(index, 'label', e.target.value)}
                    required
                  />
                </div>
                <div>
                  <select
                    className="form-control"
                    value={field.fieldType}
                    onChange={(e) => updateRegField(index, 'fieldType', e.target.value)}
                  >
                    <option value="text">Text</option>
                    <option value="number">Number</option>
                    <option value="email">Email</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={(e) => updateRegField(index, 'required', e.target.checked)}
                      style={{ accentColor: 'var(--primary)' }}
                    />
                    Required
                  </label>
                </div>
                <div>
                  <button
                    type="button"
                    onClick={() => removeRegField(index)}
                    className="btn btn-secondary btn-sm"
                    style={{ color: 'var(--danger)', padding: 6 }}
                    title="Remove field"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Section 4: Question Paper */}
        <div className="card" style={{ marginBottom: 32 }}>
          <div className="card-header">
            <div>
              <h2 className="card-title">4. Question Paper</h2>
              <p className="card-subtitle">
                Total Questions: {questions.length} | Total Marks:{' '}
                {questions.reduce((sum, q) => sum + (Number(q.marks) || 0), 0)}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={() => addQuestion('mcq')}
                className="btn btn-secondary btn-sm"
              >
                <Plus size={14} /> Add MCQ
              </button>
              <button
                type="button"
                onClick={() => addQuestion('coding')}
                className="btn btn-primary btn-sm"
              >
                <Code2 size={14} /> Add Coding Question (Judge0)
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {questions.map((q, qIndex) => (
              <div
                key={q.id || qIndex}
                style={{
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: 20,
                  backgroundColor: '#ffffff',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className="badge badge-slate" style={{ fontWeight: 600 }}>
                      Q{qIndex + 1}
                    </span>
                    <span className={`badge ${q.questionType === 'mcq' ? 'badge-blue' : 'badge-green'}`}>
                      {q.questionType === 'mcq' ? 'Multiple Choice (MCQ)' : 'Coding Challenge (Judge0)'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Marks:</label>
                      <input
                        type="number"
                        min="1"
                        style={{ width: 64 }}
                        className="form-control"
                        value={q.marks}
                        onChange={(e) => updateQuestion(qIndex, 'marks', e.target.value)}
                        required
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => removeQuestion(qIndex)}
                      className="btn btn-outline-danger btn-sm"
                      title="Delete Question"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">
                    Question Prompt <span className="req">*</span>
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder={q.questionType === 'mcq' ? 'Enter the question statement' : 'Problem Title / Headline'}
                    value={q.questionText}
                    onChange={(e) => updateQuestion(qIndex, 'questionText', e.target.value)}
                    required
                  />
                </div>

                {/* MCQ Question Editor */}
                {q.questionType === 'mcq' && (
                  <div>
                    <label className="form-label">
                      Options & Correct Answer <span className="req">*</span>
                    </label>
                    <div className="form-hint" style={{ marginBottom: 8 }}>
                      Select the radio button next to the correct answer.
                    </div>
                    {q.options.map((opt, optIndex) => (
                      <div
                        key={optIndex}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 12,
                          marginBottom: 8,
                        }}
                      >
                        <input
                          type="radio"
                          name={`correct_${q.id || qIndex}`}
                          checked={Number(q.correctOption) === optIndex}
                          onChange={() => updateQuestion(qIndex, 'correctOption', optIndex)}
                          title="Set as correct answer"
                          style={{ width: 18, height: 18, accentColor: 'var(--primary)' }}
                        />
                        <input
                          type="text"
                          className="form-control"
                          placeholder={`Option ${optIndex + 1}`}
                          value={opt}
                          onChange={(e) => updateMcqOption(qIndex, optIndex, e.target.value)}
                          required
                        />
                      </div>
                    ))}
                  </div>
                )}

                {/* Coding Question Editor */}
                {q.questionType === 'coding' && (
                  <div>
                    <div className="form-group">
                      <label className="form-label">Problem Description & Constraints</label>
                      <textarea
                        className="form-control"
                        placeholder="Detailed problem statement, input/output formats, constraints, and examples"
                        value={q.description}
                        onChange={(e) => updateQuestion(qIndex, 'description', e.target.value)}
                      />
                    </div>

                    <div className="form-row" style={{ marginBottom: 14 }}>
                      <div className="form-group">
                        <label className="form-label">Target Language</label>
                        <select
                          className="form-control"
                          value={q.language}
                          onChange={(e) => updateQuestion(qIndex, 'language', e.target.value)}
                        >
                          <option value="javascript">JavaScript (Node.js)</option>
                          <option value="python">Python 3</option>
                          <option value="cpp">C++ (GCC)</option>
                          <option value="java">Java (OpenJDK)</option>
                        </select>
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Default Starter Code Template</label>
                      <textarea
                        className="form-control"
                        style={{ fontFamily: 'var(--font-mono)', fontSize: 13, minHeight: 110 }}
                        value={q.starterCode}
                        onChange={(e) => updateQuestion(qIndex, 'starterCode', e.target.value)}
                      />
                    </div>

                    {/* Test Cases for Judge0 evaluation */}
                    <div style={{ marginTop: 14 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <label className="form-label" style={{ marginBottom: 0 }}>
                          Test Cases (Evaluated with Judge0 API)
                        </label>
                        <button
                          type="button"
                          onClick={() => addTestCase(qIndex)}
                          className="btn btn-secondary btn-sm"
                        >
                          <Plus size={12} /> Add Test Case
                        </button>
                      </div>

                      {q.testCases.map((tc, tcIndex) => (
                        <div
                          key={tcIndex}
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1fr 90px 40px',
                            gap: 10,
                            alignItems: 'center',
                            background: 'var(--bg-subtle)',
                            padding: '8px 12px',
                            borderRadius: 'var(--radius-sm)',
                            marginBottom: 8,
                          }}
                        >
                          <input
                            type="text"
                            className="form-control"
                            placeholder="Input (stdin)"
                            value={tc.input}
                            onChange={(e) => updateTestCase(qIndex, tcIndex, 'input', e.target.value)}
                          />
                          <input
                            type="text"
                            className="form-control"
                            placeholder="Expected Output (stdout)"
                            value={tc.expectedOutput}
                            onChange={(e) => updateTestCase(qIndex, tcIndex, 'expectedOutput', e.target.value)}
                            required
                          />
                          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={tc.isHidden}
                              onChange={(e) => updateTestCase(qIndex, tcIndex, 'isHidden', e.target.checked)}
                              style={{ accentColor: 'var(--primary)' }}
                            />
                            Hidden
                          </label>
                          <button
                            type="button"
                            onClick={() => removeTestCase(qIndex, tcIndex)}
                            className="btn btn-secondary btn-sm"
                            style={{ color: 'var(--danger)', padding: 4 }}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Final Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 14 }}>
          <Link to="/examiner/dashboard" className="btn btn-secondary btn-lg">
            Cancel
          </Link>
          <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
            <FileCheck size={18} />
            <span>{loading ? 'Publishing Test...' : 'Publish Test & Generate QR Code'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
