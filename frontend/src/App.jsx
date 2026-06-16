import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = '/api'

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

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px' }}>
      <header style={{ marginBottom: '40px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '3rem', fontWeight: '800', background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: '8px' }}>
          SOWA
        </h1>
        <p style={{ fontSize: '1.25rem', color: '#94a3b8' }}>
          Self-Optimizing Workload Agent
        </p>
      </header>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '32px', flexWrap: 'wrap' }}>
        <Button onClick={handleRunTurn} variant="primary" loading={loading} icon="▶">
          Run Simulation Turn
        </Button>
        <Button onClick={handleRefresh} variant="secondary" loading={loading}>
          Refresh Telemetry
        </Button>
        <Button onClick={handleTriggerSpike} variant="accent" loading={loading} icon="⚡">
          Trigger GPU Spike
        </Button>
        <Button onClick={handleRunWorkload} variant="secondary" loading={loading} disabled={!state?.current_workload}>
          Run Workload Locally
        </Button>
        <Button onClick={handleReset} variant="danger" loading={loading} icon="↺">
          Reset
        </Button>
      </div>

      {state && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
          <Card title="📦 Current Workload">
            <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#f8fafc' }}>
              {state.current_workload || 'Waiting for first run...'}
            </div>
          </Card>

          <Card title="🎯 Placement Decision">
            <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#22c55e' }}>
              {state.last_decision || '---'}
            </div>
          </Card>

          <Card title="⚠️ Risk Level">
            <div style={{ 
              fontSize: '1.5rem', fontWeight: '700', 
              color: state.risk_level === 'High' ? '#ef4444' : state.risk_level === 'Medium' ? '#eab308' : '#22c55e' 
            }}>
              {state.risk_level || 'Low'}
            </div>
            {state.risk_details && <div style={{ marginTop: '8px', color: '#94a3b8', fontSize: '0.875rem' }}>{state.risk_details}</div>}
          </Card>

          <Card title="📊 Local Telemetry">
            <pre style={{ 
              background: '#0f172a', padding: '16px', borderRadius: '8px', 
              overflow: 'auto', maxHeight: '300px', fontSize: '0.875rem', color: '#cbd5e1',
              whiteSpace: 'pre-wrap', wordBreak: 'break-all'
            }}>
              {state.local_telemetry}
            </pre>
          </Card>

          <Card title="🤖 DevOps Reasoning" colSpan="2">
            <div style={{ 
              background: '#0f172a', padding: '16px', borderRadius: '8px', 
              color: '#e0f2fe', fontSize: '0.95rem', lineHeight: '1.6'
            }}>
              {state.devops_reasoning || '---'}
            </div>
          </Card>

          <Card title="📈 Performance Summary">
            <div style={{ 
              background: '#0f172a', padding: '16px', borderRadius: '8px', 
              color: '#dcfce7', fontSize: '0.95rem', lineHeight: '1.6'
            }}>
              {state.performance_summary || '---'}
            </div>
          </Card>

          <Card title="📋 Kubernetes Manifest">
            <pre style={{ 
              background: '#0f172a', padding: '16px', borderRadius: '8px', 
              overflow: 'auto', maxHeight: '400px', fontSize: '0.875rem', color: '#f8fafc'
            }}>
              {state.k8s_manifest || '---'}
            </pre>
          </Card>

          <Card title="🔍 Tool Trace">
            <pre style={{ 
              background: '#0f172a', padding: '16px', borderRadius: '8px', 
              overflow: 'auto', maxHeight: '300px', fontSize: '0.875rem', color: '#94a3b8'
            }}>
              {state.tool_trace || '---'}
            </pre>
          </Card>
        </div>
      )}
    </div>
  )
}

const Button = ({ children, onClick, variant = 'secondary', loading = false, icon = '', disabled = false }) => {
  const variants = {
    primary: { bg: '#3b82f6', bgHover: '#2563eb', border: 'none' },
    secondary: { bg: '#334155', bgHover: '#475569', border: '1px solid #475569' },
    accent: { bg: '#8b5cf6', bgHover: '#7c3aed', border: 'none' },
    danger: { bg: '#ef4444', bgHover: '#dc2626', border: 'none' }
  }

  const [isHover, setIsHover] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHover(true)}
      onMouseLeave={() => setIsHover(false)}
      disabled={loading || disabled}
      style={{
        padding: '12px 24px',
        fontSize: '1rem',
        fontWeight: '600',
        borderRadius: '8px',
        border: variants[variant].border,
        backgroundColor: isHover ? variants[variant].bgHover : variants[variant].bg,
        color: '#f8fafc',
        cursor: (loading || disabled) ? 'not-allowed' : 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        transition: 'all 0.2s ease'
      }}
    >
      {loading ? '⏳' : icon}
      {children}
    </button>
  )
}

const Card = ({ title, children, colSpan = 1 }) => {
  return (
    <div style={{ 
      background: '#1e293b', 
      padding: '24px', 
      borderRadius: '12px', 
      border: '1px solid #334155',
      gridColumn: colSpan > 1 ? `span ${colSpan}` : 'auto'
    }}>
      <h3 style={{ 
        fontSize: '1rem', 
        fontWeight: '700', 
        textTransform: 'uppercase', 
        letterSpacing: '0.05em',
        color: '#94a3b8',
        marginBottom: '16px'
      }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

export default App
