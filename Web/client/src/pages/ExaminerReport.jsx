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
  Maximize2,
  EyeOff,
} from 'lucide-react';

const resolveMediaUrl = (url) => {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
    return url;
  }
  return url.startsWith('/') ? url : `/${url}`;
};

const getViolationGroups = (violations = []) => {
  let lookingAwayCount = 0;
  const items = [];

  violations.forEach((v) => {
    const vtype = (v.type || '').toUpperCase();
    const msg = (v.message || '').toLowerCase();

    if (vtype === 'LOOKING_AWAY' || msg.includes('looking away')) {
      lookingAwayCount += 1;
    } else {
      const isFaceMismatch =
        vtype === 'IDENTITY_MISMATCH' ||
        vtype === 'FACE_MISMATCH' ||
        msg.includes('identity mismatch') ||
        msg.includes('face mismatch');

      let displayTitle = isFaceMismatch ? 'Face Mismatch' : (v.type || 'Violation');
      if (vtype === 'PHONE_DETECTED') displayTitle = 'Phone Detected';
      else if (vtype === 'BOOK_DETECTED') displayTitle = 'Book Detected';
      else if (vtype === 'MULTIPLE_PEOPLE') displayTitle = 'Multiple People Detected';
      else if (vtype === 'FACE_MISSING') displayTitle = 'Face Not Visible';
      else if (vtype === 'MULTIPLE_SPEAKERS') displayTitle = 'Multiple Voices Detected';
      else if (vtype === 'TAB_SWITCH') displayTitle = 'Tab Switch Alert';
      else if (vtype === 'FULLSCREEN_EXIT') displayTitle = 'Fullscreen Exit Alert';

      items.push({
        ...v,
        isFaceMismatch,
        displayTitle,
        hasScreenshot: Boolean(v.screenshotUrl && String(v.screenshotUrl).trim() !== ''),
      });
    }
  });

  return {
    lookingAwayCount,
    lookingAwayText: lookingAwayCount > 0 ? `Looking Away: ${lookingAwayCount} times` : null,
    items,
  };
};

export default function ExaminerReport() {
  const { testId } = useParams();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('all'); // 'all' | 'high' | 'medium' | 'low'
  const [selectedSubmission, setSelectedSubmission] = useState(null);
  const [previewImage, setPreviewImage] = useState(null);

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
                          {sub.proctoring?.violations && sub.proctoring.violations.length > 0 && (() => {
                            const { lookingAwayCount, items } = getViolationGroups(sub.proctoring.violations);
                            const faceMismatches = items.filter((x) => x.isFaceMismatch);
                            const screenshotsCount = items.filter((x) => x.hasScreenshot).length;

                            return (
                              <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                                {lookingAwayCount > 0 && (
                                  <div style={{ fontSize: 12, fontWeight: 600, color: '#b45309' }}>
                                    Looking Away: {lookingAwayCount} times
                                  </div>
                                )}
                                {faceMismatches.length > 0 && (
                                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <Camera size={13} />
                                    <span>Face Mismatch: {faceMismatches.length} incident{faceMismatches.length > 1 ? 's' : ''} (Screenshot attached)</span>
                                  </div>
                                )}
                                {screenshotsCount > 0 && (
                                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                    {screenshotsCount} violation screenshot{screenshotsCount > 1 ? 's' : ''} attached
                                  </div>
                                )}
                              </div>
                            );
                          })()}
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
          <div className="modal-card" style={{ maxWidth: 780 }}>
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
                {selectedSubmission.proctoring?.violations && selectedSubmission.proctoring.violations.length > 0 && (() => {
                  const { lookingAwayCount, lookingAwayText, items } = getViolationGroups(selectedSubmission.proctoring.violations);

                  return (
                    <div style={{ marginTop: 14 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--danger)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <AlertCircle size={15} />
                        <span>Logged Post-Test Violations & Evidence ({selectedSubmission.proctoring.violations.length} Total):</span>
                      </div>

                      <div style={{ maxHeight: 320, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingRight: 4 }}>
                        {/* 1. Looking Away Exception: count-only format without screenshot */}
                        {lookingAwayCount > 0 && (
                          <div
                            style={{
                              padding: '10px 14px',
                              background: '#fffbeb',
                              borderRadius: 'var(--radius-sm)',
                              border: '1px solid #fde68a',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: 12,
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <span style={{ color: '#d97706', display: 'flex', alignItems: 'center' }}>
                                <EyeOff size={18} />
                              </span>
                              <div>
                                <div style={{ fontWeight: 700, fontSize: 13.5, color: '#92400e' }}>
                                  {lookingAwayText}
                                </div>
                                <div style={{ fontSize: 11.5, color: '#b45309' }}>
                                  Candidate gaze deviation logged during test. No screenshot attached.
                                </div>
                              </div>
                            </div>
                            <span className="badge badge-amber" style={{ fontSize: 12, fontWeight: 700 }}>
                              {lookingAwayCount} times
                            </span>
                          </div>
                        )}

                        {/* 2. Other violations with screenshot attached (Face Mismatch, Phone, Book, etc.) */}
                        {items.map((v, i) => (
                          <div
                            key={i}
                            style={{
                              padding: '12px 14px',
                              background: v.isFaceMismatch ? '#fef2f2' : '#ffffff',
                              borderRadius: 'var(--radius-sm)',
                              border: v.isFaceMismatch ? '1.5px solid #fca5a5' : '1px solid var(--border-color)',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: 8,
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                              <div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                  <span
                                    className={`badge ${v.isFaceMismatch ? 'badge-red' : v.severity === 'critical' ? 'badge-red' : 'badge-amber'}`}
                                    style={{ fontSize: 11, fontWeight: 700 }}
                                  >
                                    {v.displayTitle}
                                  </span>
                                  <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {v.message || v.displayTitle}
                                  </span>
                                </div>
                              </div>
                              <span style={{ color: 'var(--text-muted)', fontSize: 11.5, whiteSpace: 'nowrap' }}>
                                {new Date(v.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                              </span>
                            </div>

                            {/* Attached screenshot */}
                            {v.hasScreenshot ? (
                              <div
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 14,
                                  background: v.isFaceMismatch ? '#fee2e2' : 'var(--bg-subtle)',
                                  padding: '8px 12px',
                                  borderRadius: 6,
                                  border: '1px solid ' + (v.isFaceMismatch ? '#fecaca' : 'var(--border-color)'),
                                }}
                              >
                                <div
                                  style={{
                                    position: 'relative',
                                    cursor: 'pointer',
                                    borderRadius: 6,
                                    overflow: 'hidden',
                                    border: '1px solid #94a3b8',
                                    width: 140,
                                    height: 80,
                                    flexShrink: 0,
                                    background: '#0f172a',
                                  }}
                                  onClick={() =>
                                    setPreviewImage({
                                      url: resolveMediaUrl(v.screenshotUrl),
                                      title: v.isFaceMismatch ? 'Face Mismatch Evidence Screenshot' : `${v.displayTitle} Evidence Screenshot`,
                                      timestamp: v.timestamp,
                                      message: v.message,
                                    })
                                  }
                                  title="Click to view full screenshot"
                                >
                                  <img
                                    src={resolveMediaUrl(v.screenshotUrl)}
                                    alt={v.isFaceMismatch ? 'Face Mismatch Screenshot' : `${v.displayTitle} Screenshot`}
                                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                    onError={(e) => {
                                      e.currentTarget.style.display = 'none';
                                    }}
                                  />
                                  <div
                                    style={{
                                      position: 'absolute',
                                      bottom: 3,
                                      right: 3,
                                      background: 'rgba(0,0,0,0.7)',
                                      color: '#fff',
                                      padding: '2px 5px',
                                      borderRadius: 4,
                                      fontSize: 10,
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 3,
                                    }}
                                  >
                                    <Maximize2 size={10} />
                                    <span>Zoom</span>
                                  </div>
                                </div>

                                <div style={{ flex: 1, fontSize: 12 }}>
                                  <div style={{ fontWeight: 700, color: v.isFaceMismatch ? '#991b1b' : 'var(--text-primary)', marginBottom: 2 }}>
                                    {v.isFaceMismatch ? 'Attached Face Mismatch Screenshot' : 'Attached Violation Screenshot'}
                                  </div>
                                  <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 6 }}>
                                    High-resolution evidence captured at {new Date(v.timestamp).toLocaleTimeString()}.
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setPreviewImage({
                                        url: resolveMediaUrl(v.screenshotUrl),
                                        title: v.isFaceMismatch ? 'Face Mismatch Evidence Screenshot' : `${v.displayTitle} Evidence Screenshot`,
                                        timestamp: v.timestamp,
                                        message: v.message,
                                      })
                                    }
                                    className="btn btn-secondary btn-sm"
                                    style={{ padding: '3px 8px', fontSize: 11, height: 'auto', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                  >
                                    <Camera size={12} />
                                    <span>View Evidence Screenshot</span>
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
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

      {/* Full Evidence Screenshot Preview Modal */}
      {previewImage && (
        <div
          className="modal-backdrop"
          style={{ zIndex: 1200 }}
          onClick={() => setPreviewImage(null)}
        >
          <div
            className="modal-card"
            style={{ maxWidth: 880, padding: 0, overflow: 'hidden' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '14px 20px',
                borderBottom: '1px solid var(--border-color)',
                background: 'var(--bg-subtle)',
              }}
            >
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{previewImage.title}</h3>
                {previewImage.timestamp && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    Recorded at: {new Date(previewImage.timestamp).toLocaleString()}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setPreviewImage(null)}
              >
                ✕
              </button>
            </div>

            <div style={{ padding: 18, background: '#0a0f1d', textAlign: 'center' }}>
              <img
                src={previewImage.url}
                alt={previewImage.title}
                style={{
                  maxWidth: '100%',
                  maxHeight: '68vh',
                  borderRadius: 6,
                  boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
                }}
              />
            </div>

            {previewImage.message && (
              <div style={{ padding: '12px 20px', fontSize: 13, background: 'var(--bg-surface)', borderTop: '1px solid var(--border-color)' }}>
                <strong>Details:</strong> {previewImage.message}
              </div>
            )}

            <div className="modal-footer" style={{ padding: '12px 20px' }}>
              <a
                href={previewImage.url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary btn-sm"
              >
                Open Original in New Tab
              </a>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setPreviewImage(null)}
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
