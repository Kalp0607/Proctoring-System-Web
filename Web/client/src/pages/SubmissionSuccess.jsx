import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import { CheckCircle2, Clock, Calendar, ArrowRight, ShieldCheck } from 'lucide-react';

export default function SubmissionSuccess() {
  const { testId } = useParams();
  const [test, setTest] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadTest = async () => {
      try {
        const res = await api.getPublicDetails(testId);
        setTest(res.test);
      } catch (_) {}
      setLoading(false);
    };
    loadTest();
  }, [testId]);

  return (
    <div style={{ maxWidth: 540, margin: '60px auto', textAlign: 'center' }}>
      <div className="card" style={{ padding: 40 }}>
        <div
          style={{
            display: 'inline-flex',
            padding: 16,
            borderRadius: '50%',
            backgroundColor: 'var(--success-light)',
            color: 'var(--success)',
            marginBottom: 20,
          }}
        >
          <CheckCircle2 size={48} />
        </div>

        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8, letterSpacing: '-0.02em' }}>
          Exam Submitted Successfully
        </h1>

        <p style={{ color: 'var(--text-secondary)', fontSize: 15, marginBottom: 24, lineHeight: 1.5 }}>
          Your examination answers and anti-cheating telemetry have been safely recorded and submitted to your examiner.
        </p>

        {test && (
          <div
            style={{
              background: 'var(--bg-subtle)',
              padding: 16,
              borderRadius: 'var(--radius-md)',
              textAlign: 'left',
              marginBottom: 28,
              fontSize: 13.5,
            }}
          >
            <div style={{ marginBottom: 6 }}>
              <span style={{ color: 'var(--text-muted)' }}>Test:</span>{' '}
              <strong>{test.title}</strong> ({test.testId})
            </div>
            <div style={{ marginBottom: 6 }}>
              <span style={{ color: 'var(--text-muted)' }}>Examiner:</span>{' '}
              <strong>{test.examinerId?.name || 'Instructor'}</strong>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Submitted at:</span>{' '}
              <strong>{new Date().toLocaleString()}</strong>
            </div>
          </div>
        )}

        <Link to="/student/dashboard" className="btn btn-primary btn-lg" style={{ width: '100%' }}>
          <span>Return to Student Portal</span>
          <ArrowRight size={18} />
        </Link>
      </div>
    </div>
  );
}
