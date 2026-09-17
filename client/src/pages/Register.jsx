import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldCheck, UserPlus, AlertCircle } from 'lucide-react';

export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('examinee'); // 'examinee' | 'examiner'
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const user = await register(name, email, password, role);
      navigate(user.role === 'examiner' ? '/examiner/dashboard' : '/student/dashboard', { replace: true });
    } catch (err) {
      setError(err.message || 'Registration failed. Please check your details.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(85vh - 64px)' }}>
      <div className="card" style={{ width: '100%', maxWidth: 480 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ display: 'inline-flex', padding: 10, borderRadius: '50%', backgroundColor: 'var(--primary-light)', color: 'var(--primary)', marginBottom: 12 }}>
            <ShieldCheck size={32} />
          </div>
          <h1 className="card-title" style={{ fontSize: 22 }}>Create Your Account</h1>
          <p className="card-subtitle">Get started with ProctorSecure</p>
        </div>

        {error && (
          <div className="alert alert-danger">
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="reg-role">
              I am registering as <span className="req">*</span>
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <button
                type="button"
                className={`btn ${role === 'examinee' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '10px 12px', justifyContent: 'center' }}
                onClick={() => setRole('examinee')}
              >
                Student / Examinee
              </button>
              <button
                type="button"
                className={`btn ${role === 'examiner' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '10px 12px', justifyContent: 'center' }}
                onClick={() => setRole('examiner')}
              >
                Examiner / Teacher
              </button>
            </div>
            <div className="form-hint" style={{ marginTop: 6 }}>
              {role === 'examiner'
                ? 'Examiners can create tests, manage registrations, review violations, and export reports.'
                : 'Examinees can register for upcoming tests, enter the pre-test waiting room, and take exams.'}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reg-name">
              Full Name <span className="req">*</span>
            </label>
            <input
              id="reg-name"
              type="text"
              className="form-control"
              placeholder="e.g. John Doe"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reg-email">
              Email Address <span className="req">*</span>
            </label>
            <input
              id="reg-email"
              type="email"
              className="form-control"
              placeholder="name@institution.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reg-password">
              Password <span className="req">*</span>
            </label>
            <input
              id="reg-password"
              type="password"
              className="form-control"
              placeholder="Minimum 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={6}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            style={{ width: '100%', marginTop: 8 }}
            disabled={loading}
          >
            <UserPlus size={18} />
            <span>{loading ? 'Creating Account...' : 'Register'}</span>
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 24, fontSize: 14, color: 'var(--text-secondary)' }}>
          Already have an account?{' '}
          <Link to="/login" style={{ fontWeight: 600 }}>
            Sign in here
          </Link>
        </div>
      </div>
    </div>
  );
}
