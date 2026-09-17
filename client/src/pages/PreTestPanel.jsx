import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';
import {
  ShieldCheck,
  Maximize,
  Camera,
  Clock,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  FileText,
  Play,
  ArrowLeft,
  Video,
} from 'lucide-react';

export default function PreTestPanel() {
  const { testId } = useParams();
  const navigate = useNavigate();

  const [examData, setExamData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [timeLeftToStart, setTimeLeftToStart] = useState(null); // seconds
  const [isTestStarted, setIsTestStarted] = useState(false);
  const [isFullscreenReady, setIsFullscreenReady] = useState(false);
  const [cameraPermission, setCameraPermission] = useState(false);

  const videoRef = useRef(null);

  useEffect(() => {
    fetchExam();
  }, [testId]);

  const fetchExam = async () => {
    try {
      setLoading(true);
      const data = await api.getTestForExam(testId);
      setExamData(data);
    } catch (err) {
      if (err.data && err.data.alreadySubmitted) {
        navigate(`/exam/submitted/${testId}`, { replace: true });
        return;
      }
      setError(err.message || 'Unable to access test panel');
    } finally {
      setLoading(false);
    }
  };

  // Timer countdown to start time
  useEffect(() => {
    if (!examData) return;

    const interval = setInterval(() => {
      const now = new Date().getTime();
      const start = new Date(examData.test.startTime).getTime();
      const diffSec = Math.floor((start - now) / 1000);

      if (diffSec <= 0) {
        setTimeLeftToStart(0);
        setIsTestStarted(true);
      } else {
        setTimeLeftToStart(diffSec);
        setIsTestStarted(false);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [examData]);

  // Fullscreen change listener
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreenReady(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const requestFullscreenSetup = async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
        setIsFullscreenReady(true);
      }
    } catch (err) {
      alert('Could not enter fullscreen: ' + err.message);
    }
  };

  const testCameraPreview = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      setCameraPermission(true);
    } catch (err) {
      alert('Camera access check: ' + err.message);
    }
  };

  const formatCountdown = (totalSec) => {
    if (totalSec === null) return '--:--';
    if (totalSec <= 0) return '00:00:00';
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  };

  const handleStartExam = async () => {
    try {
      // Prompt fullscreen
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      }
      navigate(`/exam/take/${testId}`);
    } catch (e) {
      navigate(`/exam/take/${testId}`);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
        Loading pre-test waiting room...
      </div>
    );
  }

  if (error || !examData) {
    return (
      <div style={{ maxWidth: 580, margin: '40px auto' }}>
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error || 'Cannot access pre-test waiting room'}</span>
        </div>
        <Link to="/student/dashboard" className="btn btn-secondary">
          <ArrowLeft size={16} /> Return to Upcoming Tests
        </Link>
      </div>
    );
  }

  const { test, questions, registration } = examData;

  return (
    <div style={{ maxWidth: 840, margin: '0 auto', paddingBottom: 64 }}>
      {/* Header Banner */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ padding: 12, borderRadius: '50%', background: 'var(--primary-light)', color: 'var(--primary)' }}>
              <ShieldCheck size={32} />
            </div>
            <div>
              <span className="badge badge-blue" style={{ marginBottom: 4 }}>
                Pre-Test Waiting Room (15-Min Setup)
              </span>
              <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.01em' }}>{test.title}</h1>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                Test ID: {test.testId} • Examiner: {test.examiner?.name || 'Instructor'} • Total Marks: {test.totalMarks}
              </p>
            </div>
          </div>

          {/* Live Countdown */}
          <div
            style={{
              textAlign: 'center',
              padding: '12px 20px',
              borderRadius: 'var(--radius-md)',
              background: isTestStarted ? 'var(--success-light)' : 'var(--bg-subtle)',
              border: `1px solid ${isTestStarted ? 'var(--success-border)' : 'var(--border-color)'}`,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
              {isTestStarted ? 'EXAM IS LIVE' : 'STARTS IN'}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 24,
                fontWeight: 700,
                color: isTestStarted ? 'var(--success)' : 'var(--primary)',
                letterSpacing: '0.05em',
              }}
            >
              {isTestStarted ? 'Ready to Start' : formatCountdown(timeLeftToStart)}
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Instructions + Preparation Checklist */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24 }}>
        {/* Left: Test Instructions */}
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Important Examination Rules</h2>
              <p className="card-subtitle">Please read carefully before entering the examination</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, fontSize: 14 }}>
            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ color: 'var(--danger)', flexShrink: 0 }}>
                <AlertTriangle size={18} />
              </div>
              <div>
                <strong>Full-Screen Enforcement:</strong> You must keep the examination in full-screen mode at all
                times. Exiting full-screen will trigger an anti-cheating violation alert.
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ color: 'var(--danger)', flexShrink: 0 }}>
                <AlertTriangle size={18} />
              </div>
              <div>
                <strong>Strict Tab-Switching Restriction:</strong> Switching browser tabs or minimizing the browser
                window is strictly monitored. You will receive <strong>exactly 1 warning</strong>. A 2nd violation will{' '}
                <strong>automatically submit your exam immediately</strong>.
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ color: 'var(--primary)', flexShrink: 0 }}>
                <Clock size={18} />
              </div>
              <div>
                <strong>Automatic Submission at End Time:</strong> The examination will automatically submit when the
                scheduled test end time ({new Date(test.endTime).toLocaleTimeString()}) is reached, regardless of when you
                started.
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ color: 'var(--success)', flexShrink: 0 }}>
                <CheckCircle2 size={18} />
              </div>
              <div>
                <strong>Question Navigation:</strong> You may navigate freely between questions using the question
                palette, save responses at any time, and click Final Submit when finished.
              </div>
            </div>

            {test.description && (
              <div
                style={{
                  background: 'var(--bg-subtle)',
                  padding: 14,
                  borderRadius: 'var(--radius-sm)',
                  marginTop: 6,
                }}
              >
                <strong>Examiner Notes:</strong>
                <p style={{ marginTop: 4, color: 'var(--text-secondary)' }}>{test.description}</p>
              </div>
            )}
          </div>
        </div>

        {/* Right: Setup & Readiness Checks */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Readiness Checklist */}
          <div className="card">
            <h3 className="card-title" style={{ fontSize: 16, marginBottom: 14 }}>
              Setup & Device Check
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Fullscreen setup */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 12px',
                  background: 'var(--bg-subtle)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                  <Maximize size={16} />
                  <span>Full-Screen Mode</span>
                </div>
                {isFullscreenReady ? (
                  <span className="badge badge-green">Ready</span>
                ) : (
                  <button type="button" onClick={requestFullscreenSetup} className="btn btn-secondary btn-sm">
                    Test Mode
                  </button>
                )}
              </div>

              {/* Camera Preview (Placeholder for AI face verification) */}
              <div
                style={{
                  padding: '10px 12px',
                  background: 'var(--bg-subtle)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                    <Camera size={16} />
                    <span>Webcam Readiness</span>
                  </div>
                  {cameraPermission ? (
                    <span className="badge badge-green">Connected</span>
                  ) : (
                    <button type="button" onClick={testCameraPreview} className="btn btn-secondary btn-sm">
                      Check Camera
                    </button>
                  )}
                </div>

                {cameraPermission && (
                  <div className="camera-preview-box" style={{ marginTop: 8, height: 130 }}>
                    <video ref={videoRef} autoPlay playsInline muted />
                  </div>
                )}
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                  Face verification will be evaluated automatically by the AI system.
                </div>
              </div>
            </div>

            {/* Launch Button */}
            <div style={{ marginTop: 24 }}>
              {isTestStarted ? (
                <button
                  type="button"
                  onClick={handleStartExam}
                  className="btn btn-primary btn-lg"
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  <Play size={18} />
                  <span>Start Examination Now</span>
                </button>
              ) : (
                <div>
                  <button
                    type="button"
                    disabled
                    className="btn btn-primary btn-lg"
                    style={{ width: '100%', justifyContent: 'center' }}
                  >
                    <Clock size={18} />
                    <span>Waiting for Start Time...</span>
                  </button>
                  <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                    Button will unlock automatically when start time arrives.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
