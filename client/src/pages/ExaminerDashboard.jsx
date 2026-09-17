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
} from 'lucide-react';

export default function ExaminerDashboard() {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error}</span>
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
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
