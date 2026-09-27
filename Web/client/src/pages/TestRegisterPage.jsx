import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  ShieldCheck,
  Camera,
  Upload,
  Clock,
  Calendar,
  AlertCircle,
  CheckCircle2,
  Lock,
  ArrowRight,
} from 'lucide-react';

export default function TestRegisterPage() {
  const { testId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [test, setTest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isDeadlinePassed, setIsDeadlinePassed] = useState(false);

  // Form field answers
  const [fieldAnswers, setFieldAnswers] = useState({});
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);

  // Webcam snapshot state
  const [webcamActive, setWebcamActive] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  // Password verification if arriving via link
  const [passwordVerified, setPasswordVerified] = useState(false);
  const [enteredPassword, setEnteredPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchTestPublic();
  }, [testId]);

  const fetchTestPublic = async () => {
    try {
      setLoading(true);
      const res = await api.getPublicDetails(testId);
      setTest(res.test);

      // Check if deadline passed
      const deadline = new Date(res.test.registrationDeadline);
      if (new Date() > deadline) {
        setIsDeadlinePassed(true);
      }

      // If user already registered, navigate to pre-test panel
      if (res.isRegistered && !res.isRemoved) {
        navigate(`/exam/pre-test/${testId}`, { replace: true });
      }
    } catch (err) {
      setError(err.message || 'Unable to load test details');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyPassword = async (e) => {
    e.preventDefault();
    setPasswordError('');
    try {
      await api.verifyPassword(testId, enteredPassword);
      setPasswordVerified(true);
    } catch (err) {
      setPasswordError(err.message || 'Invalid test passcode');
    }
  };

  // Webcam methods
  const startWebcam = async () => {
    try {
      setWebcamActive(true);
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
    } catch (err) {
      alert('Could not access webcam: ' + err.message);
      setWebcamActive(false);
    }
  };

  const captureWebcamSnapshot = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg');
    setPhotoPreview(dataUrl);

    // Stop webcam tracks
    if (video.srcObject) {
      video.srcObject.getTracks().forEach((track) => track.stop());
    }
    setWebcamActive(false);
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setPhotoFile(file);
      setPhotoPreview(URL.createObjectURL(file));
      // Stop webcam if was running
      if (videoRef.current && videoRef.current.srcObject) {
        videoRef.current.srcObject.getTracks().forEach((t) => t.stop());
        setWebcamActive(false);
      }
    }
  };

  const handleSubmitRegistration = async (e) => {
    e.preventDefault();
    setError('');

    if (test.requirePhoto && !photoPreview && !photoFile) {
      setError('Please take a webcam snapshot or upload a student photo.');
      return;
    }

    setSubmitting(true);
    try {
      const data = new FormData();
      data.append('formData', JSON.stringify(fieldAnswers));
      if (photoFile) {
        data.append('photo', photoFile);
      } else if (photoPreview && photoPreview.startsWith('data:image')) {
        data.append('photoDataUrl', photoPreview);
      }

      await api.registerForTest(testId, data);
      navigate(`/exam/pre-test/${testId}`);
    } catch (err) {
      setError(err.message || 'Registration failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading examination details...</div>;
  }

  if (error && !test) {
    return (
      <div style={{ maxWidth: 500, margin: '40px auto' }}>
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
        <Link to="/student/dashboard" className="btn btn-secondary">
          Go to Student Portal
        </Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 680, margin: '0 auto', paddingBottom: 64 }}>
      {/* Test Header */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
          <div style={{ padding: 12, borderRadius: '50%', background: 'var(--primary-light)', color: 'var(--primary)' }}>
            <ShieldCheck size={30} />
          </div>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.01em' }}>{test.title}</h1>
            <span className="badge badge-slate" style={{ fontFamily: 'var(--font-mono)' }}>
              Test ID: {test.testId}
            </span>
          </div>
        </div>

        {test.description && (
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 16 }}>{test.description}</p>
        )}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
            background: 'var(--bg-subtle)',
            padding: 14,
            borderRadius: 'var(--radius-md)',
            fontSize: 13,
          }}
        >
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Start Time:</span>
            <div style={{ fontWeight: 600 }}>{new Date(test.startTime).toLocaleString()}</div>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>End Time:</span>
            <div style={{ fontWeight: 600 }}>{new Date(test.endTime).toLocaleString()}</div>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Registration Deadline:</span>
            <div style={{ fontWeight: 600, color: isDeadlinePassed ? 'var(--danger)' : 'var(--text-primary)' }}>
              {new Date(test.registrationDeadline).toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {isDeadlinePassed ? (
        <div className="card" style={{ textAlign: 'center', padding: 36 }}>
          <AlertCircle size={44} color="var(--danger)" style={{ marginBottom: 12 }} />
          <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--danger)', marginBottom: 8 }}>
            Registration Deadline Has Passed
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 20 }}>
            The registration deadline for this examination closed on{' '}
            <strong>{new Date(test.registrationDeadline).toLocaleString()}</strong>. Registrations are no longer accepted.
          </p>
          <Link to="/student/dashboard" className="btn btn-secondary">
            Return to Upcoming Tests
          </Link>
        </div>
      ) : !passwordVerified ? (
        /* Password Prompt */
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Test Password Verification</h2>
              <p className="card-subtitle">Enter the password provided by your examiner to unlock registration</p>
            </div>
          </div>

          {passwordError && (
            <div className="alert alert-danger">
              <AlertCircle size={16} />
              <span>{passwordError}</span>
            </div>
          )}

          <form onSubmit={handleVerifyPassword}>
            <div className="form-group">
              <label className="form-label" htmlFor="enter-pass">
                Test Password <span className="req">*</span>
              </label>
              <input
                id="enter-pass"
                type="password"
                className="form-control"
                placeholder="Enter password..."
                value={enteredPassword}
                onChange={(e) => setEnteredPassword(e.target.value)}
                required
                autoFocus
              />
            </div>

            <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%' }}>
              <Lock size={16} />
              <span>Unlock Registration Form</span>
            </button>
          </form>
        </div>
      ) : (
        /* Dynamic Registration Form */
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Candidate Registration Form</h2>
              <p className="card-subtitle">
                Please provide the required candidate information before the registration deadline
              </p>
            </div>
          </div>

          {error && (
            <div className="alert alert-danger">
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmitRegistration}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 18 }}>
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <input type="text" className="form-control" value={user?.name || ''} readOnly disabled />
              </div>
              <div className="form-group">
                <label className="form-label">Email Address</label>
                <input type="email" className="form-control" value={user?.email || ''} readOnly disabled />
              </div>
            </div>

            {/* Custom fields configured by Examiner */}
            {test.registrationFields && test.registrationFields.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>
                  Required Information Specified by Examiner
                </h3>
                {test.registrationFields.map((field) => (
                  <div key={field.id} className="form-group">
                    <label className="form-label" htmlFor={`field_${field.id}`}>
                      {field.label} {field.required && <span className="req">*</span>}
                    </label>
                    <input
                      id={`field_${field.id}`}
                      type={field.fieldType === 'number' ? 'number' : field.fieldType === 'email' ? 'email' : 'text'}
                      className="form-control"
                      placeholder={`Enter your ${field.label.toLowerCase()}`}
                      value={fieldAnswers[field.id] || ''}
                      onChange={(e) => setFieldAnswers({ ...fieldAnswers, [field.id]: e.target.value })}
                      required={field.required}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Student Photo Requirement */}
            {test.requirePhoto && (
              <div
                style={{
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: 18,
                  marginBottom: 24,
                  background: 'var(--bg-subtle)',
                }}
              >
                <label className="form-label" style={{ fontWeight: 600 }}>
                  Student Verification Photo <span className="req">*</span>
                </label>
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 14 }}>
                  This reference photo will be used for examiner review and future AI face-verification.
                </p>

                {/* Photo Preview */}
                {photoPreview && (
                  <div style={{ marginBottom: 14, textAlign: 'center' }}>
                    <img
                      src={photoPreview}
                      alt="Captured preview"
                      style={{
                        width: 180,
                        height: 180,
                        objectFit: 'cover',
                        borderRadius: 'var(--radius-md)',
                        border: '2px solid var(--primary)',
                      }}
                    />
                    <div style={{ marginTop: 6, fontSize: 12, color: 'var(--success)' }}>
                      ✓ Photo ready
                    </div>
                  </div>
                )}

                {/* Webcam Stream */}
                <div style={{ marginBottom: 14, textAlign: 'center', display: webcamActive ? 'block' : 'none' }}>
                  <video
                    ref={videoRef}
                    style={{ width: 320, height: 240, borderRadius: 'var(--radius-md)', background: '#000' }}
                    autoPlay
                    playsInline
                  />
                  <div style={{ marginTop: 10 }}>
                    <button type="button" onClick={captureWebcamSnapshot} className="btn btn-primary btn-sm">
                      <Camera size={14} /> Snap Photo
                    </button>
                  </div>
                </div>

                <canvas ref={canvasRef} style={{ display: 'none' }} />

                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {!webcamActive && (
                    <button type="button" onClick={startWebcam} className="btn btn-secondary btn-sm">
                      <Camera size={15} /> Capture via Webcam
                    </button>
                  )}
                  <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
                    <Upload size={15} /> Choose Photo File
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={handleFileChange}
                      style={{ display: 'none' }}
                    />
                  </label>
                </div>
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              style={{ width: '100%' }}
              disabled={submitting}
            >
              <CheckCircle2 size={18} />
              <span>{submitting ? 'Registering...' : 'Complete Registration & Go to Test Room'}</span>
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
