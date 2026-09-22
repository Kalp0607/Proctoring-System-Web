import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import {
  PlusCircle,
  Share2,
  Users,
  FileBarChart,
  Calendar,
  Clock,
  KeyRound,
  FileText,
  AlertCircle,
  CheckCircle2,
  Trash2,
} from 'lucide-react';

export default function ExaminerDashboard() {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [testToDelete, setTestToDelete] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    fetchTests();
  }, []);

  const fetchTests = async () => {
    try {
      setLoading(true);
      const data = await api.getExaminerTests();
      setTests(data);
    } catch (err) {
      setError(err.message || 'Failed to load tests');
    } finally {
      setLoading(false);
    }
  };

  const confirmDeleteTest = async () => {
    if (!testToDelete) return;
    try {
      setIsDeleting(true);
      setError('');
      await api.deleteTest(testToDelete.testId);
      setSuccessMsg(`Test "${testToDelete.title}" (${testToDelete.testId}) deleted successfully.`);
      setTestToDelete(null);
      await fetchTests();
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err) {
      setError(err.message || 'Failed to delete test');
    } finally {
      setIsDeleting(false);
    }
  };

  const getTestStatusBadge = (test) => {
    const now = new Date();
    const start = new Date(test.startTime);
    const end = new Date(test.endTime);

    if (now < start) {
      return <span className="badge badge-blue">Scheduled</span>;
    } else if (now >= start && now <= end) {
      return <span className="badge badge-green">Live Active</span>;
    } else {
      return <span className="badge badge-slate">Concluded</span>;
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            Examiner Dashboard
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
            Create and manage AI-proctored examinations, student registrations, and test reports.
          </p>
        </div>
        <Link to="/examiner/create-test" className="btn btn-primary">
          <PlusCircle size={18} />
          <span>Create New Test</span>
        </Link>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: 20 }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {successMsg && (
        <div className="alert alert-success" style={{ marginBottom: 20 }}>
          <CheckCircle2 size={18} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Metrics Summary */}
      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Total Tests Created</div>
          <div className="stat-val">{tests.length}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Live Active Tests</div>
          <div className="stat-val">
            {tests.filter((t) => {
              const now = new Date();
              return now >= new Date(t.startTime) && now <= new Date(t.endTime);
            }).length}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Total Student Registrations</div>
          <div className="stat-val">{tests.reduce((sum, t) => sum + (t.registrationCount || 0), 0)}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Total Submissions Received</div>
          <div className="stat-val">{tests.reduce((sum, t) => sum + (t.submissionCount || 0), 0)}</div>
        </div>
      </div>

      {/* Test List Table */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">All Created Tests</h2>
            <p className="card-subtitle">Manage questions, share entry links, view enrolled students, and download reports</p>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading your examination tests...
          </div>
        ) : tests.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <FileText size={42} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>No tests created yet</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 20 }}>
              Get started by creating your first MCQ and Coding examination.
            </p>
            <Link to="/examiner/create-test" className="btn btn-primary">
              <PlusCircle size={16} />
              <span>Create Test</span>
            </Link>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Test Title & ID</th>
                  <th>Status</th>
                  <th>Schedule</th>
                  <th>Passcode</th>
                  <th>Questions</th>
                  <th>Registrations</th>
                  <th>Submissions</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tests.map((t) => (
                  <tr key={t._id}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{t.title}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3 }}>
                        <span className="badge badge-slate" style={{ fontFamily: 'var(--font-mono)' }}>
                          {t.testId}
                        </span>
                      </div>
                    </td>
                    <td>{getTestStatusBadge(t)}</td>
                    <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      <div>{new Date(t.startTime).toLocaleDateString()}</div>
                      <div style={{ color: 'var(--text-muted)' }}>
                        {new Date(t.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                        {new Date(t.endTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-slate" style={{ fontFamily: 'var(--font-mono)' }}>
                        <KeyRound size={12} /> {t.testPassword}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{t.questions.length} questions</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.totalMarks} marks</div>
                    </td>
                    <td>
                      <span className="badge badge-blue">
                        <Users size={12} /> {t.registrationCount || 0}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-green">
                        <CheckCircle2 size={12} /> {t.submissionCount || 0}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 8 }}>
                        <Link
                          to={`/examiner/test/${t.testId}/share`}
                          className="btn btn-secondary btn-sm"
                          title="Share Link & QR Code"
                        >
                          <Share2 size={14} />
                          <span>Share</span>
                        </Link>
                        <Link
                          to={`/examiner/test/${t.testId}/registrations`}
                          className="btn btn-secondary btn-sm"
                          title="View Registered Students"
                        >
                          <Users size={14} />
                          <span>Students</span>
                        </Link>
                        <Link
                          to={`/examiner/test/${t.testId}/report`}
                          className="btn btn-primary btn-sm"
                          title="View Report & Grading"
                        >
                          <FileBarChart size={14} />
                          <span>Report</span>
                        </Link>
                        <button
                          type="button"
                          onClick={() => setTestToDelete(t)}
                          className="btn btn-sm"
                          style={{
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            color: '#ef4444',
                            borderColor: 'rgba(239, 68, 68, 0.3)',
                          }}
                          title="Permanently Delete Test"
                        >
                          <Trash2 size={14} />
                          <span>Delete</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {testToDelete && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 20,
          }}
        >
          <div
            className="card"
            style={{
              maxWidth: 500,
              width: '100%',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: '50%',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ef4444',
                  flexShrink: 0,
                }}
              >
                <Trash2 size={22} />
              </div>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
                  Permanently Delete Test?
                </h3>
                <p style={{ color: 'var(--text-muted)', fontSize: 14, lineHeight: 1.5 }}>
                  Are you sure you want to permanently delete{' '}
                  <strong style={{ color: 'var(--text-primary)' }}>"{testToDelete.title}"</strong> (
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{testToDelete.testId}</span>)?
                </p>
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                borderRadius: 'var(--radius-md)',
                padding: '12px 16px',
                marginBottom: 24,
                fontSize: 13,
                color: '#f87171',
                lineHeight: 1.5,
              }}
            >
              ⚠️ <strong>Warning:</strong> This will permanently erase the test, all student registrations, answers,
              submissions, and AI proctoring infraction logs. This action cannot be undone.
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={isDeleting}
                onClick={() => setTestToDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={isDeleting}
                onClick={confirmDeleteTest}
                style={{
                  backgroundColor: '#ef4444',
                  color: '#fff',
                  border: 'none',
                }}
              >
                {isDeleting ? 'Deleting...' : 'Yes, Delete Permanently'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

