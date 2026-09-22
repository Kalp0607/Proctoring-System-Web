import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldCheck, LogOut, PlusCircle, LayoutDashboard, Calendar, KeyRound } from 'lucide-react';

export default function Navbar({ onOpenEnterModal }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Do not render navbar inside active exam environment
  if (location.pathname.startsWith('/exam/take/')) {
    return null;
  }

  return (
    <nav className="navbar">
      <Link to="/" className="nav-brand">
        <ShieldCheck size={24} />
        <span>ProctorSecure</span>
      </Link>

      <div className="nav-links">
        {user ? (
          <>
            {user.role === 'examiner' ? (
              <>
                <Link to="/examiner/dashboard" className="btn btn-secondary btn-sm">
                  <LayoutDashboard size={16} />
                  <span>Dashboard</span>
                </Link>
                <Link to="/examiner/create-test" className="btn btn-primary btn-sm">
                  <PlusCircle size={16} />
                  <span>Create Test</span>
                </Link>
              </>
            ) : (
              <>
                <Link to="/student/dashboard" className="btn btn-secondary btn-sm">
                  <Calendar size={16} />
                  <span>Upcoming Tests</span>
                </Link>
                <button
                  type="button"
                  onClick={onOpenEnterModal}
                  className="btn btn-primary btn-sm"
                >
                  <KeyRound size={16} />
                  <span>Enter Test</span>
                </button>
              </>
            )}

            <div className="nav-user-info" style={{ marginLeft: 12 }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{user.name}</span>
              <span className={`badge ${user.role === 'examiner' ? 'badge-blue' : 'badge-slate'}`}>
                {user.role === 'examiner' ? 'Examiner' : 'Student'}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                className="btn btn-secondary btn-sm"
                title="Log out"
                style={{ padding: '6px 10px' }}
              >
                <LogOut size={16} />
              </button>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', gap: 10 }}>
            <Link to="/login" className="btn btn-secondary btn-sm">
              Sign In
            </Link>
            <Link to="/register" className="btn btn-primary btn-sm">
              Create Account
            </Link>
          </div>
        )}
      </div>
    </nav>
  );
}
