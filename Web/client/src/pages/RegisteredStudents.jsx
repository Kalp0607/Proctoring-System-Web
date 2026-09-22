import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import {
  ArrowLeft,
  Users,
  UserX,
  AlertCircle,
  CheckCircle2,
  Share2,
  FileBarChart,
  Search,
} from 'lucide-react';

export default function RegisteredStudents() {
  const { testId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPhoto, setSelectedPhoto] = useState(null);

  // Removal modal state
  const [removingReg, setRemovingReg] = useState(null);
  const [removalReason, setRemovalReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    fetchRegistrations();
  }, [testId]);

  const fetchRegistrations = async () => {
    try {
      setLoading(true);
      const res = await api.getTestRegistrations(testId);
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load registrations');
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveStudent = async () => {
    if (!removingReg) return;
    setActionLoading(true);
    try {
      await api.removeStudent(testId, removingReg._id, removalReason);
      await fetchRegistrations();
      setRemovingReg(null);
      setRemovalReason('');
    } catch (err) {
      alert(err.message || 'Failed to remove student');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading registered candidates...</div>;
  }

  if (error || !data) {
    return (
      <div style={{ maxWidth: 600, margin: '40px auto' }}>
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error || 'Unable to fetch registrations'}</span>
        </div>
        <Link to="/examiner/dashboard" className="btn btn-secondary">
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
      </div>
    );
  }

  const registrations = data.registrations || [];
  const testInfo = data.test;

  const filteredRegistrations = registrations.filter((r) => {
    const name = r.studentId?.name || '';
    const email = r.studentId?.email || '';
    const query = searchQuery.toLowerCase();
    return name.toLowerCase().includes(query) || email.toLowerCase().includes(query);
  });

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Link to="/examiner/dashboard" className="btn btn-secondary btn-sm" style={{ marginBottom: 14 }}>
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em' }}>
              Registered Students: {testInfo.title}
            </h1>
            <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              Review candidate registration details, submitted photos, and manage exam eligibility.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Link to={`/examiner/test/${testId}/share`} className="btn btn-secondary btn-sm">
              <Share2 size={16} /> Share Hub
            </Link>
            <Link to={`/examiner/test/${testId}/report`} className="btn btn-primary btn-sm">
              <FileBarChart size={16} /> Test Report
            </Link>
          </div>
        </div>
      </div>

      {/* Summary Card & Search */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div className="stat-box" style={{ padding: '10px 16px', background: 'var(--bg-subtle)' }}>
              <span className="stat-label">Total Registered</span>
              <span className="stat-val" style={{ fontSize: 20, marginLeft: 10 }}>
                {registrations.length}
              </span>
            </div>
            <div className="stat-box" style={{ padding: '10px 16px', background: 'var(--bg-subtle)' }}>
              <span className="stat-label">Active / Valid</span>
              <span className="stat-val" style={{ fontSize: 20, marginLeft: 10, color: 'var(--success)' }}>
                {registrations.filter((r) => !r.isRemoved).length}
              </span>
            </div>
            <div className="stat-box" style={{ padding: '10px 16px', background: 'var(--bg-subtle)' }}>
              <span className="stat-label">Removed by Examiner</span>
              <span className="stat-val" style={{ fontSize: 20, marginLeft: 10, color: 'var(--danger)' }}>
                {registrations.filter((r) => r.isRemoved).length}
              </span>
            </div>
          </div>

          <div style={{ position: 'relative', width: 280 }}>
            <Search
              size={16}
              style={{ position: 'absolute', left: 10, top: 11, color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              placeholder="Search by student name or email..."
              className="form-control"
              style={{ paddingLeft: 34 }}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Registered Students Table */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Enrolled Candidates</h2>
            <p className="card-subtitle">Click photo thumbnail to view high-resolution student identity photo</p>
          </div>
        </div>

        {filteredRegistrations.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No registered students match your search or have enrolled yet.
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Student Photo</th>
                  <th>Student Name & Email</th>
                  <th>Submitted Registration Fields</th>
                  <th>Registration Date</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRegistrations.map((reg) => (
                  <tr key={reg._id}>
                    <td>
                      {reg.photoUrl ? (
                        <img
                          src={reg.photoUrl}
                          alt="Student"
                          className="evidence-thumb"
                          onClick={() => setSelectedPhoto(reg.photoUrl)}
                          title="Click to view full photo"
                        />
                      ) : (
                        <div
                          style={{
                            width: 60,
                            height: 60,
                            borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'var(--bg-subtle)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'var(--text-muted)',
                            fontSize: 11,
                          }}
                        >
                          No Photo
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{reg.studentId?.name || 'Unknown'}</div>
                      <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{reg.studentId?.email}</div>
                    </td>
                    <td>
                      {reg.formData && Object.keys(reg.formData).length > 0 ? (
                        <div style={{ fontSize: 13, display: 'flex', flexDirection: 'column', gap: 3 }}>
                          {testInfo.registrationFields?.map((f) => {
                            const val = reg.formData[f.id];
                            if (!val) return null;
                            return (
                              <div key={f.id}>
                                <span style={{ color: 'var(--text-muted)' }}>{f.label}:</span>{' '}
                                <strong style={{ color: 'var(--text-primary)' }}>{val}</strong>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>None provided</span>
                      )}
                    </td>
                    <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      {new Date(reg.registeredAt).toLocaleString()}
                    </td>
                    <td>
                      {reg.isRemoved ? (
                        <div>
                          <span className="badge badge-red">Removed</span>
                          {reg.removalReason && (
                            <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 3 }}>
                              {reg.removalReason}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="badge badge-green">Valid / Enrolled</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {!reg.isRemoved && (
                        <button
                          type="button"
                          onClick={() => setRemovingReg(reg)}
                          className="btn btn-outline-danger btn-sm"
                        >
                          <UserX size={14} />
                          <span>Remove</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Full Photo Modal */}
      {selectedPhoto && (
        <div className="modal-backdrop" onClick={() => setSelectedPhoto(null)}>
          <div className="modal-card" style={{ maxWidth: 500 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="card-title" style={{ fontSize: 16 }}>
                Candidate Registration Photo
              </h3>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setSelectedPhoto(null)}
              >
                Close
              </button>
            </div>
            <div className="modal-body" style={{ textAlign: 'center', padding: 16 }}>
              <img
                src={selectedPhoto}
                alt="Student Verification"
                style={{ maxWidth: '100%', maxHeight: 420, borderRadius: 'var(--radius-md)' }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Remove Student Confirmation Modal */}
      {removingReg && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: 460 }}>
            <div className="modal-header">
              <h3 className="card-title" style={{ fontSize: 17, color: 'var(--danger)' }}>
                Remove Student from Test
              </h3>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: 14.5, marginBottom: 16 }}>
                Are you sure you want to remove <strong>{removingReg.studentId?.name}</strong> from this test?
                They will not be allowed to enter the exam room.
              </p>
              <div className="form-group">
                <label className="form-label">Reason for removal</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Invalid student credentials / unauthorized"
                  value={removalReason}
                  onChange={(e) => setRemovalReason(e.target.value)}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setRemovingReg(null);
                  setRemovalReason('');
                }}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleRemoveStudent}
                disabled={actionLoading}
              >
                {actionLoading ? 'Removing...' : 'Confirm Remove'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
