import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import { QRCodeSVG } from 'qrcode.react';
import {
  ArrowLeft,
  Copy,
  Check,
  KeyRound,
  Calendar,
  Clock,
  QrCode,
  Users,
  FileBarChart,
  Share2,
  AlertCircle,
  ExternalLink,
  Wifi,
  Laptop,
} from 'lucide-react';

export default function TestDetailsShare() {
  const { testId } = useParams();
  const [test, setTest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [networkInfo, setNetworkInfo] = useState(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedWifiLink, setCopiedWifiLink] = useState(false);
  const [copiedId, setCopiedId] = useState(false);
  const [copiedPass, setCopiedPass] = useState(false);

  useEffect(() => {
    fetchTestDetails();
  }, [testId]);

  const fetchTestDetails = async () => {
    try {
      setLoading(true);
      const res = await api.getPublicDetails(testId);
      // Retrieve testPassword from examiner tests
      const examinerTests = await api.getExaminerTests();
      const currentTest = examinerTests.find((t) => t.testId === testId.toUpperCase());
      setTest({
        ...res.test,
        testPassword: currentTest ? currentTest.testPassword : '••••••',
      });

      // Retrieve server Wi-Fi network info
      try {
        const net = await api.getNetworkInfo();
        setNetworkInfo(net);
      } catch (_) {}
    } catch (err) {
      setError(err.message || 'Failed to fetch test details');
    } finally {
      setLoading(false);
    }
  };

  const localTestLink = `${window.location.origin}/test/enter/${testId?.toUpperCase()}`;
  const wifiHost = networkInfo?.wifiClientUrl || (networkInfo?.localIp ? `https://${networkInfo.localIp}:5173` : '');
  const wifiTestLink = wifiHost ? `${wifiHost}/test/enter/${testId?.toUpperCase()}` : localTestLink;

  const copyToClipboard = (text, type) => {
    navigator.clipboard.writeText(text);
    if (type === 'link') {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    } else if (type === 'wifi') {
      setCopiedWifiLink(true);
      setTimeout(() => setCopiedWifiLink(false), 2000);
    } else if (type === 'id') {
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    } else if (type === 'pass') {
      setCopiedPass(true);
      setTimeout(() => setCopiedPass(false), 2000);
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading test share information...</div>;
  }

  if (error || !test) {
    return (
      <div style={{ maxWidth: 600, margin: '40px auto' }}>
        <div className="alert alert-danger">
          <AlertCircle size={18} />
          <span>{error || 'Test not found'}</span>
        </div>
        <Link to="/examiner/dashboard" className="btn btn-secondary">
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 880, margin: '0 auto', paddingBottom: 48 }}>
      <div style={{ marginBottom: 20 }}>
        <Link to="/examiner/dashboard" className="btn btn-secondary btn-sm" style={{ marginBottom: 14 }}>
          <ArrowLeft size={16} /> Back to Dashboard
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em' }}>Test Entry & Wi-Fi Share Hub</h1>
            <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              Share this entry information or QR code with candidates to register and enter the examination simultaneously over Wi-Fi.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Link to={`/examiner/test/${test.testId}/registrations`} className="btn btn-secondary btn-sm">
              <Users size={16} /> Registered Students
            </Link>
            <Link to={`/examiner/test/${test.testId}/report`} className="btn btn-primary btn-sm">
              <FileBarChart size={16} /> Test Report
            </Link>
          </div>
        </div>
      </div>

      {/* Wi-Fi Multi-Student Notice Banner */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '14px 18px',
          background: 'rgba(16, 185, 129, 0.08)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          borderRadius: 8,
          marginBottom: 20,
          color: '#10b981',
          fontSize: 13,
        }}
      >
        <Wifi size={20} />
        <div>
          <strong>Multi-Student Wi-Fi Proctoring Active:</strong> Multiple students connected to the same Wi-Fi can take this test simultaneously from their own laptops. Each candidate gets an independent proctored session with isolated violations and telemetry.
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <div>
            <h2 className="card-title">{test.title}</h2>
            <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
              <span>
                <strong>Start:</strong> {new Date(test.startTime).toLocaleString()}
              </span>
              <span>•</span>
              <span>
                <strong>End:</strong> {new Date(test.endTime).toLocaleString()}
              </span>
              <span>•</span>
              <span>
                <strong>Registration Closes:</strong> {new Date(test.registrationDeadline).toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 260px', gap: 32, alignItems: 'center' }}>
          {/* Share Credentials Details */}
          <div>
            {/* Test ID */}
            <div style={{ marginBottom: 18 }}>
              <label className="form-label" style={{ fontWeight: 600 }}>
                Unique Test ID
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  readOnly
                  value={test.testId}
                  className="form-control"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 18,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard(test.testId, 'id')}
                  className="btn btn-secondary"
                  title="Copy Test ID"
                >
                  {copiedId ? <Check size={16} color="var(--success)" /> : <Copy size={16} />}
                </button>
              </div>
            </div>

            {/* Test Password */}
            <div style={{ marginBottom: 18 }}>
              <label className="form-label" style={{ fontWeight: 600 }}>
                Test Entry Password
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  readOnly
                  value={test.testPassword}
                  className="form-control"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 16,
                    fontWeight: 600,
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard(test.testPassword, 'pass')}
                  className="btn btn-secondary"
                  title="Copy Password"
                >
                  {copiedPass ? <Check size={16} color="var(--success)" /> : <Copy size={16} />}
                </button>
              </div>
              <div className="form-hint">Candidates must provide this password to register and enter.</div>
            </div>

            {/* Wi-Fi Network Test Link for Students */}
            <div style={{ marginBottom: 18 }}>
              <label className="form-label" style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, color: '#10b981' }}>
                <Wifi size={15} /> Wi-Fi Test Entry Link (For Students on the same network)
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  readOnly
                  value={wifiTestLink}
                  className="form-control"
                  style={{ fontSize: 13, backgroundColor: 'var(--bg-subtle)', borderColor: 'rgba(16, 185, 129, 0.4)' }}
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard(wifiTestLink, 'wifi')}
                  className="btn btn-primary"
                  title="Copy Wi-Fi Network Link"
                >
                  {copiedWifiLink ? <Check size={16} /> : <Copy size={16} />}
                  <span>{copiedWifiLink ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <div className="form-hint" style={{ color: '#10b981' }}>
                Share this IP link so candidates on other devices connected to the Wi-Fi can join.
              </div>
            </div>

            {/* Direct Local Link */}
            <div>
              <label className="form-label" style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <Laptop size={14} /> Local Machine Link (For host laptop only)
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  readOnly
                  value={localTestLink}
                  className="form-control"
                  style={{ fontSize: 12, backgroundColor: 'var(--bg-subtle)' }}
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard(localTestLink, 'link')}
                  className="btn btn-secondary"
                  title="Copy Local Link"
                >
                  {copiedLink ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
            </div>
          </div>

          {/* QR Code */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: 20,
              backgroundColor: '#ffffff',
            }}
          >
            <QRCodeSVG value={wifiTestLink} size={180} level="H" includeMargin={false} />
            <div style={{ marginTop: 12, textAlign: 'center' }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#0f172a' }}>Scan QR to Enter Exam</div>
              <div style={{ fontSize: 11, color: '#64748b' }}>Connects directly over local Wi-Fi</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
