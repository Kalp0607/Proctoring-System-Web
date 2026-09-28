const API_BASE = '/api';

export async function request(endpoint, options = {}) {
  const token = localStorage.getItem('token');
  const headers = {
    ...(options.headers || {}),
  };

  // Only set Content-Type to application/json if not FormData
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get('content-type');
  let data;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else if (contentType && contentType.includes('application/pdf')) {
    data = await response.blob();
    return data;
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMsg = (data && data.message) || response.statusText || 'An error occurred';
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

export const api = {
  // Auth
  register: (body) => request('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) => request('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  getMe: () => request('/auth/me'),

  // Examiner Tests
  createTest: (body) => request('/tests', { method: 'POST', body: JSON.stringify(body) }),
  getExaminerTests: () => request('/tests/examiner'),
  deleteTest: (testId) => request(`/tests/${testId}`, { method: 'DELETE' }),
  getTestRegistrations: (testId) => request(`/registrations/${testId}/registrations`),
  removeStudent: (testId, regId, reason) =>
    request(`/registrations/${testId}/registrations/${regId}`, {
      method: 'DELETE',
      body: JSON.stringify({ reason }),
    }),

  // Student / Shared Tests
  getPublicDetails: (testId) => request(`/tests/${testId}/details`),
  verifyPassword: (testId, password) =>
    request(`/tests/${testId}/verify-password`, { method: 'POST', body: JSON.stringify({ password }) }),
  registerForTest: (testId, formData) =>
    request(`/tests/${testId}/register`, { method: 'POST', body: formData }),
  getUpcomingTests: () => request('/tests/student/upcoming'),
  getTestForExam: (testId) => request(`/tests/${testId}/take`),

  // Submissions & Active Exam
  startExam: (testId) => request('/submissions/start', { method: 'POST', body: JSON.stringify({ testId }) }),
  saveAnswer: (payload) => request('/submissions/save', { method: 'POST', body: JSON.stringify(payload) }),
  runCode: (payload) => request('/submissions/code-run', { method: 'POST', body: JSON.stringify(payload) }),
  submitCodeQuestion: (payload) => request('/submissions/code-submit', { method: 'POST', body: JSON.stringify(payload) }),
  logViolation: (payload) => request('/submissions/violation', { method: 'POST', body: JSON.stringify(payload) }),
  submitExam: (payload) => request('/submissions/submit', { method: 'POST', body: JSON.stringify(payload) }),

  // Reports
  getTestReport: (testId) => request(`/reports/test/${testId}`),
  overrideMarks: (submissionId, payload) =>
    request(`/reports/submission/${submissionId}/override-marks`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  downloadTestPDF: async (testId) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_BASE}/reports/test/${testId}/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to download PDF report');
    return await res.blob();
  },

  // AI Proctoring Service (proxied via /api/ai to FastAPI engine on port 8000)
  aiHealth: async () => {
    try {
      const res = await fetch('/api/ai/health');
      return await res.json();
    } catch (_) {
      return { status: 'offline' };
    }
  },
  aiVerifyPhoto: async (payload) => {
    const res = await fetch('/api/ai/verify-photo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await res.json();
  },
  aiStartSession: async (payload) => {
    const res = await fetch('/api/ai/start-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await res.json();
  },
  aiProcessFrame: async (payload) => {
    try {
      const res = await fetch('/api/ai/process-frame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return await res.json();
    } catch (_) {
      return { success: false };
    }
  },
  aiStopSession: async (payload = {}) => {
    try {
      const res = await fetch('/api/ai/stop-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return await res.json();
    } catch (_) {
      return { success: true };
    }
  },
  aiGetStatus: async (testId, studentId) => {
    try {
      const query = testId && studentId ? `?testId=${encodeURIComponent(testId)}&studentId=${encodeURIComponent(studentId)}` : '';
      const res = await fetch(`/api/ai/status${query}`);
      return await res.json();
    } catch (_) {
      return { active: false, telemetry: null, events: [] };
    }
  },
};

