import React, { useEffect, useMemo, useState } from 'react'
import axios from 'axios'

const normalizedBaseUrl = new URL(
  window.location.pathname.endsWith('/') ? window.location.pathname : `${window.location.pathname}/`,
  window.location.origin,
)
const API_BASE = new URL('./api', normalizedBaseUrl).pathname.replace(/\/$/, '')

const shellStyle = {
  minHeight: '100vh',
  background: 'radial-gradient(circle at top, rgba(59, 130, 246, 0.18), transparent 22%), linear-gradient(180deg, #081126 0%, #0b1428 55%, #0f172a 100%)',
}

const pageStyle = {
  maxWidth: '1440px',
  margin: '0 auto',
  padding: '32px 20px 48px',
}

const panelStyle = {
  background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.98))',
  border: '1px solid rgba(148, 163, 184, 0.14)',
  borderRadius: '20px',
  boxShadow: '0 24px 80px rgba(2, 6, 23, 0.45)',
}

const sectionTitleStyle = {
  fontSize: '0.78rem',
  fontWeight: '700',
  letterSpacing: '0.16em',
  textTransform: 'uppercase',
  color: '#8ea8d5',
}

const App = () => {
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchState = async () => {
    try {
      const res = await axios.get(`${API_BASE}/state`)
      setState(res.data)
    } catch (err) {
      console.error('Error fetching state:', err)
    }
  }

  useEffect(() => {
    fetchState()
  }, [])

  const handleRunTurn = async () => {
    setLoading(true)
    try {
      const res = await axios.post(`${API_BASE}/run-turn`)
      setState(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleTriggerSpike = async () => {
    setLoading(true)
    try {
      await axios.post(`${API_BASE}/trigger-gpu-spike`)
      await fetchState()
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRunWorkload = async () => {
    setLoading(true)
    try {
      await axios.post(`${API_BASE}/run-current-workload`)
      await fetchState()
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = async () => {
    setLoading(true)
    try {
      const res = await axios.post(`${API_BASE}/refresh-telemetry`)
      setState(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    setLoading(true)
    try {
      const res = await axios.post(`${API_BASE}/reset`)
      setState(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const statusCards = useMemo(
    () => [
      {
        title: 'Current Workload',
        icon: '📦',
        value: state?.current_workload || 'Waiting for first run',
        tone: '#f8fafc',
        detail: 'Active request under evaluation by the placement workflow.',
      },
      {
        title: 'Placement Decision',
        icon: '🎯',
        value: state?.last_decision || 'Pending',
        tone: '#22c55e',
        detail: 'Latest target selected by the scheduling agent.',
      },
      {
        title: 'Risk Level',
        icon: '⚠️',
        value: state?.risk_level || 'Low',
        tone: riskColor(state?.risk_level),
        detail: state?.risk_details || 'Overall placement risk inferred from current telemetry.',
      },
      {
        title: 'Telemetry Source',
        icon: '🛰️',
        value: state?.telemetry_source || 'Initializing',
        tone: '#60a5fa',
        detail: 'Live source currently feeding the hybrid cluster snapshot.',
      },
    ],
    [state],
  )

  return (
    <div style={shellStyle}>
      <div style={pageStyle}>
        <div style={{ ...panelStyle, padding: '32px', marginBottom: '24px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              gap: '24px',
              flexWrap: 'wrap',
              alignItems: 'flex-end',
            }}
          >
            <div style={{ maxWidth: '720px' }}>
              <div style={{ ...sectionTitleStyle, marginBottom: '12px' }}>AMD Intelligent Placement Console</div>
              <h1
                style={{
                  fontSize: 'clamp(2.5rem, 7vw, 4.5rem)',
                  lineHeight: 1,
                  fontWeight: '800',
                  letterSpacing: '-0.04em',
                  background: 'linear-gradient(90deg, #7dd3fc, #6366f1 45%, #8b5cf6 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  marginBottom: '12px',
                }}
              >
                SOWA
              </h1>
              <p style={{ color: '#c7d2fe', fontSize: '1.125rem', lineHeight: 1.7, maxWidth: '700px' }}>
                Self-Optimizing Workload Agent for explainable AMD infrastructure scheduling, hybrid telemetry,
                and deployable workload placement recommendations.
              </p>
            </div>
            <div
              style={{
                minWidth: '240px',
                padding: '18px 20px',
                borderRadius: '18px',
                background: 'rgba(15, 23, 42, 0.7)',
                border: '1px solid rgba(96, 165, 250, 0.2)',
              }}
            >
              <div style={{ ...sectionTitleStyle, marginBottom: '10px' }}>Session Status</div>
              <div style={{ fontSize: '1.6rem', fontWeight: '700', color: '#f8fafc', marginBottom: '4px' }}>
                {loading ? 'Running' : 'Ready'}
              </div>
              <div style={{ color: '#94a3b8', lineHeight: 1.6 }}>
                {loading
                  ? 'Processing the current request and refreshing telemetry.'
                  : 'Use the control bar below to refresh metrics or run the next turn.'}
              </div>
            </div>
          </div>
        </div>

        <div style={{ ...panelStyle, padding: '20px', marginBottom: '24px' }}>
          <div style={{ ...sectionTitleStyle, marginBottom: '16px' }}>Control Center</div>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <Button onClick={handleRunTurn} variant="primary" loading={loading} icon="▶">
              Run Simulation Turn
            </Button>
            <Button onClick={handleRefresh} variant="secondary" loading={loading} icon="↻">
              Refresh Telemetry
            </Button>
            <Button onClick={handleTriggerSpike} variant="accent" loading={loading} icon="⚡">
              Trigger GPU Spike
            </Button>
            <Button onClick={handleRunWorkload} variant="secondary" loading={loading} disabled={!state?.current_workload} icon="⏵">
              Run Workload Locally
            </Button>
            <Button onClick={handleReset} variant="danger" loading={loading} icon="↺">
              Reset
            </Button>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '18px',
            marginBottom: '24px',
          }}
        >
          {statusCards.map((card) => (
            <SummaryCard key={card.title} {...card} />
          ))}
        </div>

        {state && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
              gap: '24px',
              alignItems: 'start',
            }}
          >
            <div style={{ display: 'grid', gap: '24px' }}>
              <Card
                eyebrow="Decision Engine"
                title="DevOps Reasoning"
                subtitle="Human-readable explanation of the current placement choice."
              >
                <ScrollPanel tone="#e0f2fe" minHeight="220px">
                  {state.devops_reasoning || 'No decision has been produced yet.'}
                </ScrollPanel>
              </Card>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '24px' }}>
                <Card
                  eyebrow="Impact"
                  title="Performance Summary"
                  subtitle="Expected trade-off versus the baseline placement strategy."
                >
                  <ScrollPanel tone="#dcfce7" minHeight="220px">
                    {state.performance_summary || 'Performance guidance will appear after the first turn.'}
                  </ScrollPanel>
                </Card>
                <Card
                  eyebrow="Visibility"
                  title="Tool Trace"
                  subtitle="Internal tool calls used to reach the current recommendation."
                >
                  <CodePanel minHeight="220px">{state.tool_trace || 'No tool activity recorded yet.'}</CodePanel>
                </Card>
              </div>

              <Card
                eyebrow="Deployment Artifact"
                title="Kubernetes Manifest"
                subtitle="Generated deployment YAML targeting the selected AMD hardware profile."
              >
                <CodePanel minHeight="420px">{state.k8s_manifest || 'Manifest output will appear after the first decision.'}</CodePanel>
              </Card>
            </div>

            <div style={{ display: 'grid', gap: '24px' }}>
              <Card
                eyebrow="Live Metrics"
                title="Local Telemetry"
                subtitle="Current notebook utilization and recent accelerator activity."
              >
                <CodePanel minHeight="360px">{state.local_telemetry || 'Telemetry will load shortly.'}</CodePanel>
              </Card>

              <Card
                eyebrow="Cluster Snapshot"
                title="Simulated Cluster Status"
                subtitle="Hybrid view combining the local node with simulated remote infrastructure."
              >
                <ScrollPanel tone="#dbeafe" minHeight="200px">
                  {state.simulated_cluster_snapshot || 'Cluster snapshot unavailable.'}
                </ScrollPanel>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const Button = ({ children, onClick, variant = 'secondary', loading = false, icon = '', disabled = false }) => {
  const variants = {
    primary: {
      bg: 'linear-gradient(135deg, #3b82f6, #2563eb)',
      bgHover: 'linear-gradient(135deg, #4f8ef7, #2a6ae6)',
      border: '1px solid rgba(96, 165, 250, 0.35)',
    },
    secondary: {
      bg: 'rgba(51, 65, 85, 0.78)',
      bgHover: 'rgba(71, 85, 105, 0.92)',
      border: '1px solid rgba(148, 163, 184, 0.18)',
    },
    accent: {
      bg: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
      bgHover: 'linear-gradient(135deg, #9b6cff, #8245ee)',
      border: '1px solid rgba(167, 139, 250, 0.35)',
    },
    danger: {
      bg: 'linear-gradient(135deg, #ef4444, #dc2626)',
      bgHover: 'linear-gradient(135deg, #f35a5a, #e13737)',
      border: '1px solid rgba(248, 113, 113, 0.35)',
    },
  }

  const [isHover, setIsHover] = useState(false)
  const palette = variants[variant]

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHover(true)}
      onMouseLeave={() => setIsHover(false)}
      disabled={loading || disabled}
      style={{
        padding: '13px 18px',
        minHeight: '50px',
        fontSize: '0.96rem',
        fontWeight: '700',
        letterSpacing: '0.01em',
        borderRadius: '14px',
        border: palette.border,
        background: isHover ? palette.bgHover : palette.bg,
        color: '#f8fafc',
        cursor: loading || disabled ? 'not-allowed' : 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '10px',
        transition: 'transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease',
        boxShadow: isHover && !(loading || disabled) ? '0 14px 30px rgba(15, 23, 42, 0.28)' : 'none',
        transform: isHover && !(loading || disabled) ? 'translateY(-1px)' : 'none',
      }}
    >
      <span style={{ opacity: 0.95 }}>{loading ? '⏳' : icon}</span>
      <span>{children}</span>
    </button>
  )
}

const SummaryCard = ({ title, icon, value, detail, tone }) => (
  <div
    style={{
      ...panelStyle,
      padding: '22px',
      minHeight: '180px',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
    }}
  >
    <div>
      <div style={{ ...sectionTitleStyle, display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '18px' }}>
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      <div
        style={{
          color: tone,
          fontSize: 'clamp(1.2rem, 2.6vw, 1.8rem)',
          lineHeight: 1.3,
          fontWeight: '800',
          wordBreak: 'break-word',
        }}
      >
        {value}
      </div>
    </div>
    <div style={{ color: '#94a3b8', lineHeight: 1.6, marginTop: '18px', fontSize: '0.92rem' }}>{detail}</div>
  </div>
)

const Card = ({ eyebrow, title, subtitle, children }) => (
  <div style={{ ...panelStyle, padding: '24px' }}>
    {eyebrow && <div style={{ ...sectionTitleStyle, marginBottom: '10px' }}>{eyebrow}</div>}
    <div style={{ fontSize: '1.35rem', fontWeight: '750', color: '#f8fafc', marginBottom: '8px' }}>{title}</div>
    {subtitle && <div style={{ color: '#94a3b8', lineHeight: 1.6, marginBottom: '18px' }}>{subtitle}</div>}
    {children}
  </div>
)

const ScrollPanel = ({ children, tone, minHeight }) => (
  <div
    style={{
      background: 'rgba(8, 15, 30, 0.72)',
      border: '1px solid rgba(96, 165, 250, 0.08)',
      borderRadius: '16px',
      padding: '18px',
      minHeight,
      whiteSpace: 'pre-wrap',
      color: tone,
      lineHeight: 1.75,
    }}
  >
    {children}
  </div>
)

const CodePanel = ({ children, minHeight }) => (
  <pre
    style={{
      background: '#08101f',
      border: '1px solid rgba(96, 165, 250, 0.08)',
      borderRadius: '16px',
      padding: '18px',
      overflow: 'auto',
      minHeight,
      maxHeight: '540px',
      fontSize: '0.875rem',
      lineHeight: 1.7,
      color: '#dbeafe',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace',
    }}
  >
    {children}
  </pre>
)

function riskColor(riskLevel) {
  if (riskLevel === 'High') return '#ef4444'
  if (riskLevel === 'Medium') return '#f59e0b'
  return '#22c55e'
}

export default App
