import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import {
  ArrowLeft,
  FileDown,
  AlertTriangle,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Eye,
  Camera,
  AlertCircle,
  Clock,
  Filter,
  Users,
} from 'lucide-react';

export default function ExaminerReport() {
  const { testId } = useParams();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('all'); // 'all' | 'high' | 'medium' | 'low'
  const [selectedSubmission, setSelectedSubmission] = useState(null);

  // Marks override modal state
  const [overrideModalOpen, setOverrideModalOpen] = useState(false);
  const [isDisqualified, setIsDisqualified] = useState(true);
  const [disqualificationReason, setDisqualificationReason] = useState('Confirmed cheating / proctoring violations');
  const [finalMarks, setFinalMarks] = useState(0);
  const [examinerNotes, setExaminerNotes] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  useEffect(() => {
    fetchReport();
  }, [testId]);

  const fetchReport = async () => {
    try {
      setLoading(true);
      const data = await api.getTestReport(testId);
      setReport(data);
    } catch (err) {
      setError(err.message || 'Failed to load test report');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    try {
      setDownloadingPdf(true);
      const blob = await api.downloadTestPDF(testId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Exam_Report_${testId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(err.message || 'Failed to download PDF report');
    } finally {
      setDownloadingPdf(false);
    }
  };

  const openOverrideModal = (sub) => {
    setSelectedSubmission(sub);
    setIsDisqualified(sub.examinerReview?.isDisqualified ?? false);
    setDisqualificationReason(sub.examinerReview?.disqualificationReason || 'Confirmed cheating violation');
    setFinalMarks(sub.examinerReview?.finalMarks ?? sub.totalMarksObtained ?? 0);
    setExaminerNotes(sub.examinerReview?.notes || '');
    setOverrideModalOpen(true);
  };

  const handleSaveMarksOverride = async () => {
    if (!selectedSubmission) return;
    setActionLoading(true);
    try {
      await api.overrideMarks(selectedSubmission._id, {
        isDisqualified,
        disqualificationReason,
        finalMarks: isDisqualified ? 0 : Number(finalMarks),
        notes: examinerNotes,
      });
      await fetchReport();
      setOverrideModalOpen(false);
    } catch (err) {
      alert(err.message || 'Failed to update candidate marks');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Generating comprehensive test report...</div>;
  }

  if (error || !report) {
    return (
      <div style={{ maxWidth: 600, margin: '40px auto' }}>
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error || 'Unable to generate report'}</span>
        </div>
        <Link to="/examiner/dashboard" className="btn btn-secondary">
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
      </div>
    );
  }

  const { test, summary, categorizedByRisk, allSubmissions } = report;

  const displayedSubmissions =
    activeTab === 'high'
      ? categorizedByRisk.highRisk
      : activeTab === 'medium'
      ? categorizedByRisk.mediumRisk
      : activeTab === 'low'
      ? categorizedByRisk.lowRisk
      : allSubmissions;

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Link to="/examiner/dashboard" className="btn btn-secondary btn-sm" style={{ marginBottom: 14 }}>
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em' }}>
              Test Report & Proctoring Analysis
            </h1>
            <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              {test.title} ({test.testId}) • Total Marks: {test.totalMarks}
            </p>
          </div>
          <button
            type="button"
            onClick={handleDownloadPDF}
            className="btn btn-primary btn-lg"
            disabled={downloadingPdf}
          >
            <FileDown size={18} />
            <span>{downloadingPdf ? 'Generating PDF...' : 'Download PDF Report'}</span>
          </button>
        </div>
      </div>

      {/* Summary Statistics */}
      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Registered Candidates</div>
          <div className="stat-val">{summary.totalRegistered}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Appeared / Submitted</div>
          <div className="stat-val">{summary.totalAppeared}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Average Score</div>
          <div className="stat-val">
            {summary.averageMarks} <span style={{ fontSize: 14, color: 'var(--text-muted)' }}>/ {test.totalMarks}</span>
          </div>
        </div>
        <div className="stat-box" style={{ borderColor: 'var(--danger-border)', background: 'var(--danger-light)' }}>
          <div className="stat-label" style={{ color: '#991b1b' }}>High Risk (AI / Cheating)</div>
          <div className="stat-val" style={{ color: 'var(--danger)' }}>{summary.highRiskCount}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Disqualified (0 Marks)</div>
          <div className="stat-val" style={{ color: 'var(--danger)' }}>{summary.disqualifiedCount}</div>
        </div>
      </div>

      {/* Categorized Risk Panels */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Candidate Evaluation & Violations</h2>
            <p className="card-subtitle">
              Filter candidates by AI proctoring risk level, inspect screenshot evidence, and apply marks penalties
            </p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="tab-list">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            <span>All Candidates</span>
            <span className="badge badge-slate">{allSubmissions.length}</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'high' ? 'active' : ''}`}
            onClick={() => setActiveTab('high')}
            style={activeTab === 'high' ? { color: 'var(--danger)', borderBottomColor: 'var(--danger)' } : {}}
          >
            <ShieldAlert size={15} color="var(--danger)" />
            <span>High Risk</span>
            <span className="badge badge-red">{categorizedByRisk.highRisk.length}</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'medium' ? 'active' : ''}`}
            onClick={() => setActiveTab('medium')}
          >
            <AlertTriangle size={15} color="var(--warning)" />
            <span>Medium Risk</span>
            <span className="badge badge-amber">{categorizedByRisk.mediumRisk.length}</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'low' ? 'active' : ''}`}
            onClick={() => setActiveTab('low')}
          >
            <CheckCircle2 size={15} color="var(--success)" />
            <span>Low Risk</span>
            <span className="badge badge-green">{categorizedByRisk.lowRisk.length}</span>
          </button>
        </div>

        {/* Candidates Table */}
        {displayedSubmissions.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No candidates in this risk category.
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Student & Photo</th>
                  <th>Risk Level</th>
                  <th>Violations Log</th>
                  <th>Raw Score</th>
                  <th>Final Examiner Score</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Examiner Review</th>
                </tr>
              </thead>
              <tbody>
                {displayedSubmissions.map((sub) => {
                  const risk = sub.proctoring?.riskLevel || 'Low';
                  const isDisq = sub.examinerReview?.isDisqualified;
                  const totalBrowserViolations =
                    (sub.proctoring?.tabSwitchCount || 0) + (sub.proctoring?.fullscreenExitCount || 0);

                  return (
                    <tr key={sub._id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          {sub.photoUrl ? (
                            <img src={sub.photoUrl} alt="Photo" className="evidence-thumb" style={{ width: 44, height: 44 }} />
                          ) : (
                            <div
                              style={{
                                width: 44,
                                height: 44,
                                borderRadius: 'var(--radius-sm)',
                                background: 'var(--bg-subtle)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: 11,
                                color: 'var(--text-muted)',
                              }}
                            >
                              No Photo
                            </div>
                          )}
                          <div>
                            <div style={{ fontWeight: 600 }}>{sub.studentId?.name || 'Unknown Student'}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub.studentId?.email}</div>
                          </div>
                        </div>
                      </td>

                      <td>
                        <span
                          className={`badge ${
                            risk === 'High' ? 'badge-red' : risk === 'Medium' ? 'badge-amber' : 'badge-green'
                          }`}
                        >
                          {risk} Risk
                        </span>
                      </td>

                      <td>
                        <div style={{ fontSize: 13 }}>
                          <div>
                            <strong>{totalBrowserViolations}</strong> browser alerts (Tab / Fullscreen)
                          </div>
                          {sub.proctoring?.violations && sub.proctoring.violations.length > 0 && (
                            <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 2 }}>
                              {sub.proctoring.violations.length} AI proctoring violations recorded
                            </div>
                          )}
                        </div>
                      </td>

                      <td>
                        <div style={{ fontWeight: 500 }}>
                          {sub.totalMarksObtained} / {test.totalMarks}
                        </div>
                      </td>

                      <td>
                        {isDisq ? (
                          <div>
                            <span style={{ fontWeight: 700, color: 'var(--danger)', fontSize: 15 }}>0 Marks</span>
                            <div style={{ fontSize: 11, color: 'var(--danger)' }}>Disqualified for Cheating</div>
                          </div>
                        ) : (
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            {sub.examinerReview?.finalMarks !== undefined
                              ? sub.examinerReview.finalMarks
                              : sub.totalMarksObtained}{' '}
                            / {test.totalMarks}
                          </div>
                        )}
                      </td>

                      <td>
                        <span className={`badge ${sub.status === 'submitted' ? 'badge-green' : 'badge-amber'}`}>
                          {sub.status === 'auto_submitted' ? 'Auto-Submitted' : 'Submitted'}
                        </span>
                      </td>

                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          onClick={() => openOverrideModal(sub)}
                          className={`btn ${isDisq ? 'btn-danger' : 'btn-secondary'} btn-sm`}
                        >
                          {isDisq ? 'Disqualified (0)' : 'Review & Mark'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Examiner Review & Disqualification Modal */}
      {overrideModalOpen && selectedSubmission && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: 620 }}>
            <div className="modal-header">
              <h3 className="card-title" style={{ fontSize: 17 }}>
                Review Candidate: {selectedSubmission.studentId?.name}
              </h3>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setOverrideModalOpen(false)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {/* Evidence and Violations Summary */}
              <div
                style={{
                  background: 'var(--bg-subtle)',
                  padding: 16,
                  borderRadius: 'var(--radius-md)',
                  marginBottom: 20,
                }}
              >
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Proctoring Telemetry & Violations</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 13 }}>
                  <div>
                    Tab Switches: <strong>{selectedSubmission.proctoring?.tabSwitchCount || 0}</strong>
                  </div>
                  <div>
                    Fullscreen Exits: <strong>{selectedSubmission.proctoring?.fullscreenExitCount || 0}</strong>
                  </div>
                  <div>
                    Calculated Risk Level: <strong>{selectedSubmission.proctoring?.riskLevel || 'Low'}</strong>
                  </div>
                  <div>
                    Submission Reason:{' '}
                    <strong>{selectedSubmission.submissionReason || selectedSubmission.status}</strong>
                  </div>
                </div>

                {/* Violation list */}
                {selectedSubmission.proctoring?.violations && selectedSubmission.proctoring.violations.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger)', marginBottom: 4 }}>
                      Logged Violations:
                    </div>
                    <div style={{ maxHeight: 120, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {selectedSubmission.proctoring.violations.map((v, i) => (
                        <div
                          key={i}
                          style={{
                            fontSize: 12,
                            padding: '4px 8px',
                            background: '#ffffff',
                            borderRadius: 4,
                            border: '1px solid var(--border-color)',
                            display: 'flex',
                            justifyContent: 'space-between',
                          }}
                        >
                          <span>
                            <strong>{v.type}:</strong> {v.message}
                          </span>
                          <span style={{ color: 'var(--text-muted)' }}>
                            {new Date(v.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Action 1: Disqualify student with 0 marks */}
              <div
                style={{
                  border: isDisqualified ? '2px solid var(--danger)' : '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                  marginBottom: 16,
                  backgroundColor: isDisqualified ? 'var(--danger-light)' : '#ffffff',
                }}
              >
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontWeight: 600 }}>
                  <input
                    type="checkbox"
                    checked={isDisqualified}
                    onChange={(e) => setIsDisqualified(e.target.checked)}
                    style={{ width: 18, height: 18, accentColor: 'var(--danger)' }}
                  />
                  <span style={{ color: isDisqualified ? 'var(--danger)' : 'var(--text-primary)' }}>
                    Award 0 Marks (Disqualify Candidate for Cheating / Violations)
                  </span>
                </label>

                {isDisqualified && (
                  <div style={{ marginTop: 12 }}>
                    <label className="form-label" style={{ fontSize: 13 }}>
                      Disqualification Reason (printed on official report)
                    </label>
                    <input
                      type="text"
                      className="form-control"
                      value={disqualificationReason}
                      onChange={(e) => setDisqualificationReason(e.target.value)}
                      placeholder="e.g. Tab switching violation / multiple people detected"
                      required
                    />
                  </div>
                )}
              </div>

              {/* Action 2: Manual score override if not disqualified */}
              {!isDisqualified && (
                <div className="form-group">
                  <label className="form-label">
                    Adjusted Final Marks (Total Possible: {test.totalMarks})
                  </label>
                  <input
                    type="number"
                    min="0"
                    max={test.totalMarks}
                    className="form-control"
                    value={finalMarks}
                    onChange={(e) => setFinalMarks(e.target.value)}
                  />
                </div>
              )}

              {/* Notes */}
              <div className="form-group">
                <label className="form-label">Examiner Feedback / Audit Notes</label>
                <textarea
                  className="form-control"
                  placeholder="Optional examiner audit remarks"
                  value={examinerNotes}
                  onChange={(e) => setExaminerNotes(e.target.value)}
                  style={{ minHeight: 70 }}
                />
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setOverrideModalOpen(false)}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`btn ${isDisqualified ? 'btn-danger' : 'btn-primary'}`}
                onClick={handleSaveMarksOverride}
                disabled={actionLoading}
              >
                {actionLoading ? 'Saving...' : 'Save Decision & Update Marks'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
