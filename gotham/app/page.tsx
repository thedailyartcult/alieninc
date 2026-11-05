'use client';

import { useState } from 'react';

interface SanctionEntry {
  id: string;
  schema: string;
  name: string;
  aliases: string[];
  countries: string[];
  programs: string[];
  sanctions: string;
}

interface ReconResult {
  type: 'ip' | 'domain' | 'wallet';
  query: string;
  timestamp: string;
  geo?: any;
  reputation?: any;
  rdap?: any;
  http?: any;
  sanctions_match?: {
    source: string;
    hits: Array<{ matched_value: string; entries: SanctionEntry[] }>;
  } | null;
  otx?: any;
  tor_exit_node?: boolean;
  threat_level?: string;
  security_score?: { score: number; max: number; grade: string };
}

export default function LinkAnalysisPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ReconResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detectQueryType = (q: string): 'ip' | 'domain' | 'wallet' => {
    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(q)) return 'ip';
    if (/^(0x)?[0-9a-fA-F]{40}$/.test(q)) return 'wallet';
    return 'domain';
  };

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const type = detectQueryType(query);
      let endpoint = '';
      let params = '';

      if (type === 'ip') {
        endpoint = '/api/gotham/ip';
        params = `?ip=${encodeURIComponent(query)}`;
      } else if (type === 'domain') {
        endpoint = '/api/gotham/whois';
        params = `?domain=${encodeURIComponent(query)}`;
      } else {
        setError('Wallet tracing not yet implemented');
        setLoading(false);
        return;
      }

      const res = await fetch(`${endpoint}${params}`);
      if (!res.ok) {
        throw new Error(`Lookup failed: ${res.statusText}`);
      }

      const data = await res.json();
      setResults(prev => [{ ...data, type, query, timestamp: new Date().toISOString() }, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const hasSanctionsHit = (result: ReconResult) => {
    return result.sanctions_match && result.sanctions_match.hits.length > 0;
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: '#050507',
      color: '#ffffff',
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
      padding: '32px',
    }}>
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: '48px' }}>
          <h1 style={{
            fontSize: '32px',
            fontWeight: 600,
            marginBottom: '8px',
            background: 'linear-gradient(135deg, #00f0ff, #7c3aed)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
            Link Analysis Toolkit
          </h1>
          <p style={{ color: '#83858c', fontSize: '14px' }}>
            Intelligence gathering and sanctions screening for IPs, domains, and entities
          </p>
        </div>

        {/* Search Input */}
        <div style={{
          background: '#0b0c10',
          border: '1px solid rgba(124, 58, 237, 0.12)',
          borderRadius: '8px',
          padding: '24px',
          marginBottom: '32px',
        }}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Enter IP address, domain, or entity name..."
              style={{
                flex: 1,
                padding: '12px 16px',
                background: '#121318',
                border: '1px solid rgba(124, 58, 237, 0.12)',
                borderRadius: '6px',
                color: '#ffffff',
                fontSize: '14px',
                outline: 'none',
              }}
            />
            <button
              onClick={handleSearch}
              disabled={loading}
              style={{
                padding: '12px 24px',
                background: '#00f0ff',
                color: '#000000',
                border: 'none',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>
          <div style={{ fontSize: '12px', color: '#83858c' }}>
            Accepts: IPv4 addresses (8.8.8.8), domains (example.com), or entity names for sanctions screening
          </div>
        </div>

        {error && (
          <div style={{
            background: 'rgba(244, 63, 94, 0.1)',
            border: '1px solid rgba(244, 63, 94, 0.3)',
            borderRadius: '6px',
            padding: '16px',
            marginBottom: '24px',
            color: '#f43f5e',
            fontSize: '14px',
          }}>
            {error}
          </div>
        )}

        {/* Results Grid */}
        {results.length > 0 && (
          <div style={{ display: 'grid', gap: '24px' }}>
            {results.map((result, idx) => (
              <div
                key={idx}
                style={{
                  background: '#0b0c10',
                  border: hasSanctionsHit(result)
                    ? '2px solid #f43f5e'
                    : '1px solid rgba(124, 58, 237, 0.12)',
                  borderRadius: '8px',
                  padding: '24px',
                  boxShadow: hasSanctionsHit(result)
                    ? '0 0 20px rgba(244, 63, 94, 0.3)'
                    : 'none',
                }}
              >
                {/* Result Header */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '20px',
                  paddingBottom: '16px',
                  borderBottom: '1px solid rgba(124, 58, 237, 0.12)',
                }}>
                  <div>
                    <div style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      color: '#83858c',
                      marginBottom: '4px',
                    }}>
                      {result.type} Lookup
                    </div>
                    <div style={{
                      fontSize: '18px',
                      fontWeight: 600,
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                    }}>
                      {result.query}
                    </div>
                  </div>
                  {hasSanctionsHit(result) && (
                    <div style={{
                      background: 'rgba(244, 63, 94, 0.15)',
                      border: '1px solid #f43f5e',
                      borderRadius: '6px',
                      padding: '8px 16px',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#f43f5e',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}>
                      <span style={{ fontSize: '16px' }}>⚠</span>
                      OFAC SANCTIONED
                    </div>
                  )}
                  {result.threat_level && (
                    <div style={{
                      background: result.threat_level === 'HIGH'
                        ? 'rgba(244, 63, 94, 0.15)'
                        : result.threat_level === 'MEDIUM'
                        ? 'rgba(245, 158, 11, 0.15)'
                        : 'rgba(16, 185, 129, 0.15)',
                      border: `1px solid ${
                        result.threat_level === 'HIGH'
                          ? '#f43f5e'
                          : result.threat_level === 'MEDIUM'
                          ? '#f59e0b'
                          : '#10b981'
                      }`,
                      borderRadius: '6px',
                      padding: '8px 16px',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: result.threat_level === 'HIGH'
                        ? '#f43f5e'
                        : result.threat_level === 'MEDIUM'
                        ? '#f59e0b'
                        : '#10b981',
                    }}>
                      THREAT: {result.threat_level}
                    </div>
                  )}
                </div>

                {/* Geolocation Data */}
                {result.geo && (
                  <div style={{ marginBottom: '20px' }}>
                    <div style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      color: '#83858c',
                      marginBottom: '12px',
                    }}>
                      Geolocation
                    </div>
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                      gap: '12px',
                    }}>
                      <div style={{
                        background: '#121318',
                        padding: '12px',
                        borderRadius: '6px',
                      }}>
                        <div style={{ fontSize: '11px', color: '#83858c', marginBottom: '4px' }}>Country</div>
                        <div style={{ fontSize: '14px', fontWeight: 500 }}>{result.geo.country}</div>
                      </div>
                      <div style={{
                        background: '#121318',
                        padding: '12px',
                        borderRadius: '6px',
                      }}>
                        <div style={{ fontSize: '11px', color: '#83858c', marginBottom: '4px' }}>City</div>
                        <div style={{ fontSize: '14px', fontWeight: 500 }}>{result.geo.city}</div>
                      </div>
                      <div style={{
                        background: '#121318',
                        padding: '12px',
                        borderRadius: '6px',
                      }}>
                        <div style={{ fontSize: '11px', color: '#83858c', marginBottom: '4px' }}>ISP</div>
                        <div style={{ fontSize: '14px', fontWeight: 500 }}>{result.geo.isp}</div>
                      </div>
                      <div style={{
                        background: '#121318',
                        padding: '12px',
                        borderRadius: '6px',
                      }}>
                        <div style={{ fontSize: '11px', color: '#83858c', marginBottom: '4px' }}>Organization</div>
                        <div style={{ fontSize: '14px', fontWeight: 500 }}>{result.geo.org}</div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Reputation */}
                {result.reputation && (
                  <div style={{ marginBottom: '20px' }}>
                    <div style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      color: '#83858c',
                      marginBottom: '12px',
                    }}>
                      Reputation
                    </div>
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                      {result.reputation.is_proxy && (
                        <div style={{
                          background: 'rgba(244, 63, 94, 0.1)',
                          border: '1px solid rgba(244, 63, 94, 0.3)',
                          borderRadius: '4px',
                          padding: '6px 12px',
                          fontSize: '12px',
                          color: '#f43f5e',
                        }}>
                          Proxy Detected
                        </div>
                      )}
                      {result.reputation.is_hosting && (
                        <div style={{
                          background: 'rgba(245, 158, 11, 0.1)',
                          border: '1px solid rgba(245, 158, 11, 0.3)',
                          borderRadius: '4px',
                          padding: '6px 12px',
                          fontSize: '12px',
                          color: '#f59e0b',
                        }}>
                          Hosting Provider
                        </div>
                      )}
                      {result.tor_exit_node && (
                        <div style={{
                          background: 'rgba(244, 63, 94, 0.1)',
                          border: '1px solid rgba(244, 63, 94, 0.3)',
                          borderRadius: '4px',
                          padding: '6px 12px',
                          fontSize: '12px',
                          color: '#f43f5e',
                        }}>
                          Tor Exit Node
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Security Score */}
                {result.security_score && (
                  <div style={{ marginBottom: '20px' }}>
                    <div style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      color: '#83858c',
                      marginBottom: '12px',
                    }}>
                      Security Score
                    </div>
                    <div style={{
                      background: '#121318',
                      padding: '16px',
                      borderRadius: '6px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '16px',
                    }}>
                      <div style={{
                        fontSize: '32px',
                        fontWeight: 700,
                        color: result.security_score.grade === 'A'
                          ? '#10b981'
                          : result.security_score.grade === 'B'
                          ? '#00f0ff'
                          : result.security_score.grade === 'C'
                          ? '#f59e0b'
                          : '#f43f5e',
                      }}>
                        {result.security_score.grade}
                      </div>
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: 500 }}>
                          {result.security_score.score} / {result.security_score.max}
                        </div>
                        <div style={{ fontSize: '12px', color: '#83858c' }}>
                          Security headers implemented
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Sanctions Match Details */}
                {hasSanctionsHit(result) && result.sanctions_match && (
                  <div style={{
                    background: 'rgba(244, 63, 94, 0.05)',
                    border: '1px solid rgba(244, 63, 94, 0.3)',
                    borderRadius: '6px',
                    padding: '16px',
                    marginBottom: '20px',
                  }}>
                    <div style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      color: '#f43f5e',
                      marginBottom: '12px',
                    }}>
                      ⚠ OFAC Sanctions Match Detected
                    </div>
                    {result.sanctions_match.hits.map((hit, hitIdx) => (
                      <div key={hitIdx} style={{ marginBottom: '12px' }}>
                        <div style={{
                          fontSize: '12px',
                          color: '#83858c',
                          marginBottom: '8px',
                        }}>
                          Matched: <span style={{ color: '#f43f5e', fontWeight: 600 }}>{hit.matched_value}</span>
                        </div>
                        {hit.entries.map((entry, entryIdx) => (
                          <div
                            key={entryIdx}
                            style={{
                              background: '#121318',
                              padding: '12px',
                              borderRadius: '4px',
                              marginBottom: '8px',
                            }}
                          >
                            <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>
                              {entry.name}
                            </div>
                            <div style={{ fontSize: '12px', color: '#83858c', marginBottom: '4px' }}>
                              Type: {entry.schema} | Countries: {entry.countries.join(', ')}
                            </div>
                            <div style={{ fontSize: '11px', color: '#83858c' }}>
                              Programs: {entry.programs.join(', ')}
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* Timestamp */}
                <div style={{
                  fontSize: '11px',
                  color: '#45474f',
                  marginTop: '16px',
                  paddingTop: '16px',
                  borderTop: '1px solid rgba(124, 58, 237, 0.12)',
                }}>
                  Queried: {new Date(result.timestamp).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}

        {results.length === 0 && !loading && (
          <div style={{
            textAlign: 'center',
            padding: '64px 24px',
            color: '#45474f',
          }}>
            <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.3 }}>⌕</div>
            <div style={{ fontSize: '14px' }}>
              Enter a query above to begin intelligence gathering
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
