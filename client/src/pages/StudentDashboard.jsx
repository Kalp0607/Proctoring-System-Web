import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import {
  Calendar,
  Clock,
  KeyRound,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  QrCode,
  Lock,
  UserCheck,
} from 'lucide-react';

export default function StudentDashboard({ enterModalOpen, setEnterModalOpen }) {
  const [upcomingTests, setUpcomingTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Enter test modal form state
  const [enterTestId, setEnterTestId] = useState('');
  const [enterPassword, setEnterPassword] = useState('');
  const [modalError, setModalError] = useState('');
  const [modalLoading, setModalLoading] = useState(false);

  const navigate = useNavigate();

  useEffect(() => {
    fetchUpcoming();
  }, []);

  const fetchUpcoming = async () => {
    try {
      setLoading(true);
      const data = await api.getUpcomingTests();
      setUpcomingTests(data);
    } catch (err) {
      setError(err.message || 'Failed to load upcoming tests');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyAndEnter = async (e) => {
    e.preventDefault();
    setModalError('');

    if (!enterTestId.trim() || !enterPassword.trim()) {
      setModalError('Please enter both Test ID and Test Password');
      return;
    }

    setModalLoading(true);
    const cleanId = enterTestId.trim().toUpperCase();

    try {
      // 1. Verify password
      await api.verifyPassword(cleanId, enterPassword.trim());

      // 2. Fetch test public metadata
      const details = await api.getPublicDetails(cleanId);

      setEnterModalOpen(false);
      setEnterTestId('');
      setEnterPassword('');

      if (!details.isRegistered) {
        // Redirect to registration form
        navigate(`/test/register/${cleanId}`);
      } else {
        // Already registered, go to pre-test panel
        navigate(`/exam/pre-test/${cleanId}`);
      }
    } catch (err) {
      setModalError(err.message || 'Invalid Test ID or Password');
    } finally {
      setModalLoading(false);
    }
  };

  const getStatusAction = (item) => {
    const { status, hasSubmitted, test } = item;
    const now = new Date();

    if (hasSubmitted) {
      return (
        <span className="badge badge-green" style={{ padding: '6px 12px' }}>
          <CheckCircle2 size={14} /> Completed
        </span>
      );
    }

    if (status === 'pre_test_open') {
      return (
        <Link to={`/exam/pre-test/${test.testId}`} className="btn btn-primary btn-sm">
          <span>Pre-Test Waiting Room</span>
          <ArrowRight size={14} />
        </Link>
      );
    }

    if (status === 'active') {
      return (
        <Link to={`/exam/pre-test/${test.testId}`} className="btn btn-primary btn-sm">
          <span>Enter Active Exam</span>
          <ArrowRight size={14} />
        </Link>
      );
    }

    if (status === 'ended') {
      return <span className="badge badge-slate">Concluded</span>;
    }

    // upcoming before 15 min pre-test window
    return (
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => navigate(`/exam/pre-test/${test.testId}`)}
      >
        <span>View Details</span>
      </button>
    );
  };

  return (
    <div>
      {/* Header Banner */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            Examinee Portal
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
            View your upcoming proctored tests, enter waiting rooms, or register with a Test ID and password.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEnterModalOpen(true)}
          className="btn btn-primary btn-lg"
        >
          <KeyRound size={18} />
          <span>Enter / Register for Test</span>
        </button>
      </div>

      {error && (
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Upcoming Tests Section */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">My Registered & Upcoming Tests</h2>
            <p className="card-subtitle">Pre-test rooms unlock 15 minutes before the scheduled start time</p>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading your registered examinations...
          </div>
        ) : upcomingTests.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <Calendar size={42} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>No upcoming tests found</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 20 }}>
              Have a Test ID and Password from your instructor? Enter it now to register.
            </p>
            <button
              type="button"
              onClick={() => setEnterModalOpen(true)}
              className="btn btn-primary"
            >
              <KeyRound size={16} />
              <span>Enter Test ID</span>
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {upcomingTests.map((item) => {
              const { test, status, hasSubmitted, submission } = item;
              const isPreTestReady = status === 'pre_test_open' || status === 'active';

              return (
                <div
                  key={item.registrationId}
                  style={{
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-md)',
                    padding: '18px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 20,
                    background: isPreTestReady && !hasSubmitted ? 'var(--primary-light)' : '#ffffff',
                    borderColor: isPreTestReady && !hasSubmitted ? '#93c5fd' : 'var(--border-color)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 'var(--radius-md)',
                        backgroundColor: isPreTestReady && !hasSubmitted ? 'var(--primary)' : 'var(--bg-subtle)',
                        color: isPreTestReady && !hasSubmitted ? '#ffffff' : 'var(--text-secondary)',
                      }}
                    >
                      <ShieldCheck size={26} />
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                          {test.title}
                        </h3>
                        <span className="badge badge-slate" style={{ fontFamily: 'var(--font-mono)' }}>
                          {test.testId}
                        </span>
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 16,
                          fontSize: 13,
                          color: 'var(--text-muted)',
                          marginTop: 4,
                        }}
                      >
                        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                          <Clock size={14} />
                          {new Date(test.startTime).toLocaleString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}{' '}
                          -{' '}
                          {new Date(test.endTime).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                        <span>•</span>
                        <span>Examiner: {test.examiner?.name || 'Instructor'}</span>
                        <span>•</span>
                        <span>{test.totalMarks} Marks</span>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    {hasSubmitted && submission && (
                      <div style={{ textAlign: 'right', marginRight: 8 }}>
                        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Score</div>
                        <div style={{ fontWeight: 700, fontSize: 16, color: submission.isDisqualified ? 'var(--danger)' : 'var(--text-primary)' }}>
                          {submission.isDisqualified ? '0 (Disqualified)' : `${submission.marks} / ${test.totalMarks}`}
                        </div>
                      </div>
                    )}
                    {getStatusAction(item)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Enter Test Modal */}
      {enterModalOpen && (
        <div className="modal-backdrop" onClick={() => setEnterModalOpen(false)}>
          <div className="modal-card" style={{ maxWidth: 440 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="card-title" style={{ fontSize: 17 }}>
                Enter Examination
              </h3>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setEnterModalOpen(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleVerifyAndEnter}>
              <div className="modal-body">
                {modalError && (
                  <div className="alert alert-danger" style={{ marginBottom: 14 }}>
                    <AlertCircle size={16} />
                    <span>{modalError}</span>
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label" htmlFor="modal-testid">
                    Test ID <span className="req">*</span>
                  </label>
                  <input
                    id="modal-testid"
                    type="text"
                    className="form-control"
                    placeholder="e.g. TEST-ABC123"
                    value={enterTestId}
                    onChange={(e) => setEnterTestId(e.target.value.toUpperCase())}
                    style={{ fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}
                    required
                    autoFocus
                  />
                  <div className="form-hint">Provided by your teacher or from the test link/QR code.</div>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="modal-pass">
                    Test Password <span className="req">*</span>
                  </label>
                  <input
                    id="modal-pass"
                    type="password"
                    className="form-control"
                    placeholder="••••••••"
                    value={enterPassword}
                    onChange={(e) => setEnterPassword(e.target.value)}
                    required
                  />
                  <div className="form-hint">Passcode will be validated before test access is granted.</div>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setEnterModalOpen(false)}
                  disabled={modalLoading}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={modalLoading}>
                  <Lock size={15} />
                  <span>{modalLoading ? 'Validating...' : 'Verify & Proceed'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
