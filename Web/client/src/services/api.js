const API_BASE = '/api';

export function getAiBaseUrl() {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'https:') {
      return '/ai-api';
    }
    if (window.location.hostname) {
      return `http://${window.location.hostname}:8000/api/ai`;
    }
  }
  return 'http://localhost:8000/api/ai';
}

async function aiRequest(endpoint, options = {}, timeoutMs = 2500) {
  const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
  // Under HTTPS, prioritize the local proxy to prevent Mixed-Content blocks
  const primaryUrl = isHttps ? `/ai-api${endpoint}` : `${getAiBaseUrl()}${endpoint}`;
  const proxyUrl = isHttps ? `${getAiBaseUrl()}${endpoint}` : `/ai-api${endpoint}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const fetchOptions = {
    ...options,
    signal: options.signal || controller.signal,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  };

  try {
    const res = await fetch(primaryUrl, fetchOptions);
    clearTimeout(timer);
    if (res.ok) return await res.json();
    const data = await res.json().catch(() => ({}));
    const err = new Error(data.message || `AI service returned ${res.status}`);
    err.status = res.status;
    err.data = data;
    throw err;
  } catch (primaryErr) {
    clearTimeout(timer);
    if (controller.signal.aborted) {
      throw new Error(`AI request ${endpoint} timed out after ${timeoutMs}ms`);
    }
    // If direct connection failed, fallback to Vite /ai-api proxy with 1.5s timeout
    try {
      const fbController = new AbortController();
      const fbTimer = setTimeout(() => fbController.abort(), 1500);
      const proxyRes = await fetch(proxyUrl, {
        ...fetchOptions,
        signal: fbController.signal,
      });
      clearTimeout(fbTimer);
      if (proxyRes.ok) return await proxyRes.json();
      const pData = await proxyRes.json().catch(() => ({}));
      const pErr = new Error(pData.message || `AI proxy returned ${proxyRes.status}`);
      pErr.status = proxyRes.status;
      throw pErr;
    } catch (_) {
      throw primaryErr;
    }
  }
}

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

  // Network info for Wi-Fi sharing
  getNetworkInfo: () => request('/network-info'),

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

  // Multimodal AI Proctoring Engine (FastAPI)
  aiHealth: async () => {
    try {
      return await aiRequest('/health');
    } catch (_) {
      return { status: 'offline' };
    }
  },

  aiVerifyPhoto: async (payload) => {
    return await aiRequest('/verify-photo', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  aiStartSession: async (payload) => {
    return await aiRequest('/start-session', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  aiSendFrame: async (payload) => {
    return await aiRequest('/session/frame', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  aiStopSession: async (payload = {}) => {
    try {
      return await aiRequest('/stop-session', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    } catch (_) {
      return { success: true };
    }
  },

  aiGetStatus: async (params = {}) => {
    try {
      const q = new URLSearchParams();
      if (params.testId) q.append('testId', params.testId);
      if (params.studentId) q.append('studentId', params.studentId);
      const queryStr = q.toString() ? `?${q.toString()}` : '';
      return await aiRequest(`/status${queryStr}`);
    } catch (_) {
      return { active: false, telemetry: null, events: [] };
    }
  },
};
