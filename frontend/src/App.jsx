import React, { useState, useEffect } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

const SUGGESTIONS = [
  'Spider-Man Miles Morales',
  'Demon Slayer',
  'Cyberpunk Neon Street',
  'Ghibli Landscape',
  'Retro Synthwave',
  'Aesthetic Space Nebula'
];

function App() {
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(10);
  const [upscale, setUpscale] = useState('none');
  const [localUpscale, setLocalUpscale] = useState('none');
  const [loading, setLoading] = useState(false);
  const [statusLogs, setStatusLogs] = useState([]);
  const [currentResult, setCurrentResult] = useState(null);
  const [selectedWallpaperIdx, setSelectedWallpaperIdx] = useState(0);
  const [history, setHistory] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');

  // Sync localUpscale selection with target wallpaper's upscale format
  useEffect(() => {
    if (currentResult && currentResult.wallpapers) {
      const activeWp = currentResult.wallpapers[selectedWallpaperIdx];
      if (activeWp) {
        setLocalUpscale(activeWp.upscale || 'none');
      }
    }
  }, [selectedWallpaperIdx, currentResult]);
  
  // Cache buster to force re-render
  const [cacheBuster, setCacheBuster] = useState(Date.now());

  // Preview Modal States
  const [previewImageUrl, setPreviewImageUrl] = useState(null);
  const [previewTitle, setPreviewTitle] = useState('');

  // Fetch history on load
  const fetchHistory = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/history`);
      if (response.ok) {
        const data = await response.json();
        setHistory(data);
      }
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  // Update query input box when current result changes
  useEffect(() => {
    if (currentResult) {
      setQuery(currentResult.query || '');
    }
  }, [currentResult]);

  const addLog = (text, type = 'pending') => {
    setStatusLogs((prev) => [...prev, { id: Date.now() + Math.random(), text, type }]);
  };

  const handleGenerate = async (searchQuery, isGenerateMore = false) => {
    const q = searchQuery || query;
    if (!q.trim()) return;

    setLoading(true);
    setErrorMsg('');
    
    // Reset active view if starting fresh
    if (!isGenerateMore) {
      setCurrentResult(null);
      setSelectedWallpaperIdx(0);
      setStatusLogs([]);
    } else {
      setStatusLogs([]);
    }

    const actionLabel = isGenerateMore ? 'appending new' : 'generating new';
    const desktopLimit = limit // 2;
    const mobileLimit = limit - desktopLimit;

    addLog(`Launching browser automation context (limit: ${limit}, split: ${desktopLimit} Desktop / ${mobileLimit} Mobile)...`, 'pending');
    
    const timer1 = setTimeout(() => {
      setStatusLogs((logs) => 
        logs.map((l, i) => i === 0 ? { ...l, type: 'done' } : l)
      );
      addLog(`Searching Pinterest directly for widescreen desktop and portrait mobile assets...`, 'pending');
    }, 2000);

    const timer2 = setTimeout(() => {
      setStatusLogs((logs) => 
        logs.map((l, i) => i === 1 ? { ...l, type: 'done' } : l)
      );
      addLog('Verifying high-res URLs and filtering out duplicates...', 'pending');
    }, 4500);

    const timer3 = setTimeout(() => {
      setStatusLogs((logs) => 
        logs.map((l, i) => i === 2 ? { ...l, type: 'done' } : l)
      );
      addLog(`Downloading original high-resolution wallpapers to local disk (no editing)...`, 'pending');
    }, 7000);

    try {
      const response = await fetch(`${BACKEND_URL}/api/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          query: q,
          limit: limit,
          session_id: isGenerateMore && currentResult ? currentResult.id : null,
          upscale: upscale
        }),
      });

      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);

      if (!response.ok) {
        const errData = await response.json();
        let errMsg = 'Failed to generate wallpapers';
        if (errData && errData.detail) {
          if (typeof errData.detail === 'string') {
            errMsg = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            errMsg = errData.detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join(', ');
          }
        }
        throw new Error(errMsg);
      }

      const data = await response.json();
      
      const totalNew = isGenerateMore && currentResult 
        ? (data.wallpapers.length - currentResult.wallpapers.length) 
        : data.wallpapers.length;

      // Update all logs to complete
      setStatusLogs([
        { id: 1, text: 'Browser automation context successfully launched.', type: 'done' },
        { id: 2, text: `Scraped high-quality Pinterest search results in native orientations.`, type: 'done' },
        { id: 3, text: 'Filtered duplicates and resolved original high-resolution assets.', type: 'done' },
        { id: 4, text: `Successfully downloaded ${totalNew} new original wallpapers directly.`, type: 'done' },
        { id: 5, text: `Saved directly to local PC directory: ${data.local_folder}`, type: 'done' },
      ]);

      if (isGenerateMore && currentResult) {
        const oldLength = currentResult.wallpapers.length;
        setCurrentResult(data);
        if (data.wallpapers.length > oldLength) {
          setSelectedWallpaperIdx(oldLength);
        }
      } else {
        setCurrentResult(data);
        setSelectedWallpaperIdx(0);
      }

      fetchHistory(); // Reload history gallery
    } catch (err) {
      console.error(err);
      setErrorMsg(err.message || 'An unexpected error occurred.');
      addLog(`Error: ${err.message || 'Server error'}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestionClick = (tag) => {
    setQuery(tag);
    handleGenerate(tag, false);
  };

  const handleHistoryClick = (item) => {
    if (!item.wallpapers && item.desktop_url) {
      const convertedItem = {
        ...item,
        wallpapers: [{
          index: 1,
          title: item.title || 'Pinterest Image',
          original_url: item.original_url,
          original_local: item.original_local,
          desktop_url: item.desktop_url,
          mobile_url: item.mobile_url,
          source_type: 'desktop'
        }]
      };
      setCurrentResult(convertedItem);
    } else {
      setCurrentResult(item);
    }
  };

  const handleDownload = async (fileUrl, fileName) => {
    try {
      const response = await fetch(fileUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Programmatic download failed, opening in new tab:', err);
      window.open(fileUrl, '_blank');
    }
  };

  const handleRotate = async (wpIndex, direction) => {
    if (!currentResult) return;
    setLoading(true);
    setErrorMsg('');
    
    try {
      const response = await fetch(`${BACKEND_URL}/api/rotate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: currentResult.id,
          index: wpIndex,
          direction: direction,
          upscale: localUpscale
        }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to rotate image');
      }
      
      const data = await response.json();
      setCurrentResult(data);
      setCacheBuster(Date.now());
      fetchHistory();
    } catch (err) {
      console.error(err);
      setErrorMsg(err.message || 'Failed to rotate image');
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async (wpIndex, targetUpscale) => {
    if (!currentResult) return;
    setLoading(true);
    setErrorMsg('');
    try {
      const response = await fetch(`${BACKEND_URL}/api/regenerate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: currentResult.id,
          index: wpIndex,
          upscale: targetUpscale
        }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to upscale wallpaper');
      }
      
      const data = await response.json();
      setCurrentResult(data);
      setCacheBuster(Date.now());
      fetchHistory();
    } catch (err) {
      console.error(err);
      setErrorMsg(err.message || 'Failed to upscale wallpaper');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="logo-container">
          <div className="logo-icon">7</div>
          <h1 className="logo-text">se7<span>ven</span></h1>
        </div>
        <p className="app-subtitle">Premium Portfolio Downloader</p>
      </header>

      {/* Input / Search Box */}
      <section className="input-section">
        <div className="search-box-wrapper">
          <input
            type="text"
            className="search-input"
            placeholder="Type wallpaper keyword (e.g. Spiderman, Cyberpunk, Demon Slayer)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleGenerate(null, false)}
            disabled={loading}
          />
          
          {/* Variable Count Dropdown */}
          <select
            className="limit-select"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            disabled={loading}
            style={{ minWidth: '140px' }}
          >
            {[10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map((num) => (
              <option key={num} value={num}>
                {num} Wallpapers
              </option>
            ))}
          </select>

          {/* Upscale Dropdown */}
          <select
            className="limit-select"
            value={upscale}
            onChange={(e) => setUpscale(e.target.value)}
            disabled={loading}
            style={{ minWidth: '150px' }}
          >
            <option value="none">Standard Res</option>
            <option value="4k">Ultra HD 4K ✨</option>
            <option value="8k">Extreme 8K 💎</option>
          </select>

          {/* Action Buttons */}
          <button 
            className="generate-button"
            onClick={() => handleGenerate(null, false)}
            disabled={loading || !query.trim()}
          >
            {loading && !currentResult ? <div className="spinner"></div> : 'Generate New'}
          </button>

          {currentResult && (
            <button 
              className="generate-more-button"
              onClick={() => handleGenerate(null, true)}
              disabled={loading}
            >
              {loading && currentResult ? <div className="spinner"></div> : 'Generate More'}
            </button>
          )}
        </div>

        <div className="quick-tags">
          {SUGGESTIONS.map((tag) => (
            <button
              key={tag}
              className="quick-tag"
              onClick={() => handleSuggestionClick(tag)}
              disabled={loading}
            >
              {tag}
            </button>
          ))}
        </div>
      </section>

      {/* Progress Logs */}
      {(statusLogs.length > 0 || errorMsg) && (
        <div className="logger-card">
          <div className="logger-header">
            <div className="logger-title">
              {loading && <div className="logger-dot"></div>}
              <span>{loading ? 'AGENT ACTIVITY LOG' : 'EXECUTION COMPLETE'}</span>
            </div>
            <span className="logger-status">
              {loading ? 'processing...' : errorMsg ? 'failed' : 'success'}
            </span>
          </div>
          <div className="logger-list">
            {statusLogs.map((log) => (
              <div key={log.id} className={`logger-item ${log.type}`}>
                {log.type === 'done' && '✓ '}
                {log.type === 'error' && '✗ '}
                {log.type === 'pending' && '⚡ '}
                {log.text}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Results Display */}
      {currentResult && currentResult.wallpapers && currentResult.wallpapers.length > 0 && (
        <section className="results-section">
          
          {/* Saved Folder Banner */}
          {currentResult.local_folder && (
            <div className="folder-banner">
              <div className="folder-banner-text">
                📁 Saved to local PC folder: <strong>{currentResult.local_folder}</strong>
              </div>
            </div>
          )}

          {/* Showcase Area for Selected Wallpaper */}
          {(() => {
            const activeWp = currentResult.wallpapers[selectedWallpaperIdx];
            if (!activeWp) return null;
            const isDesktop = activeWp.source_type === 'desktop';
            const activeUrl = activeWp.desktop_url || activeWp.mobile_url || activeWp.original_local;
            const imageUrl = `${BACKEND_URL}${activeUrl}?t=${cacheBuster}`;
            
            return (
              <div className="showcase-container" style={{ maxWidth: '800px', margin: '0 auto 3rem auto' }}>
                <div className="showcase-header">
                  <div className="showcase-title-area">
                    <span className="showcase-subtitle" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      Viewing Option {selectedWallpaperIdx + 1} of {currentResult.wallpapers.length}
                      <span className={`source-type-badge ${isDesktop ? 'desktop' : 'mobile'}`}>
                        {isDesktop ? '🖥️ Desktop Native (16:9)' : '📱 Mobile Native (9:16)'}
                      </span>
                    </span>
                    <h2 className="showcase-title">{activeWp.title || 'Pinterest Wallpaper'}</h2>
                  </div>
                </div>
                
                {/* Single preview card matching native aspect ratio */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.5rem', width: '100%' }}>
                  <div 
                    className="showcase-card" 
                    style={{ 
                      width: '100%', 
                      maxWidth: isDesktop ? '100%' : '400px', 
                      margin: '0 auto', 
                      background: 'rgba(0,0,0,0.4)', 
                      borderColor: isDesktop ? 'rgba(59,130,246,0.3)' : 'rgba(16,185,129,0.3)' 
                    }}
                  >
                    <div className="showcase-card-header">
                      <span className={`aspect-badge ${isDesktop ? 'original' : 'mobile'}`}>
                        {isDesktop ? 'Desktop 16:9' : 'Mobile 9:16'}
                      </span>
                      <span className="ratio-text">Prisinte High-Res Original</span>
                    </div>
                    
                    <div 
                      className="showcase-image-container" 
                      style={{ 
                        aspectRatio: isDesktop ? '16/9' : '9/16',
                        maxHeight: isDesktop ? '450px' : '550px',
                        overflow: 'hidden',
                        borderRadius: '8px',
                        background: '#07070a'
                      }}
                    >
                      <img
                        src={imageUrl}
                        alt="Wallpaper Preview"
                        className="showcase-img"
                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                      />
                    </div>
                    
                    <div className="showcase-actions">
                      <button
                        onClick={() => handleDownload(imageUrl, `${isDesktop ? 'desktop' : 'mobile'}_${currentResult.query}_${selectedWallpaperIdx + 1}.jpg`)}
                        className="showcase-btn primary-btn"
                        style={{ flex: 1 }}
                      >
                        Download Original
                      </button>
                      <button
                        onClick={() => {
                          setPreviewImageUrl(`${BACKEND_URL}${activeUrl}`);
                          setPreviewTitle(`${currentResult.query} - ${isDesktop ? 'Desktop (16:9)' : 'Mobile (9:16)'}`);
                        }}
                        className="showcase-btn"
                        style={{ flex: 1, background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)' }}
                      >
                        Preview Fullscreen
                      </button>
                    </div>
                    {/* Resolution / Upscale Selector */}
                    <div className="showcase-actions" style={{ paddingTop: '0.5rem', paddingBottom: '0.25rem', marginTop: '-0.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <span style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', whiteSpace: 'nowrap' }}>Resolution:</span>
                      <select
                        className="limit-select"
                        value={localUpscale}
                        onChange={(e) => {
                          const targetUpscale = e.target.value;
                          setLocalUpscale(targetUpscale);
                          handleRegenerate(activeWp.index, targetUpscale);
                        }}
                        disabled={loading}
                        style={{ flex: 1, padding: '0.35rem', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '4px', color: '#fff', fontSize: '0.85rem' }}
                      >
                        <option value="none">Standard Resolution</option>
                        <option value="4k">Upscale to 4K ✨</option>
                        <option value="8k">Upscale to 8K 💎</option>
                      </select>
                    </div>
                    {/* Rotate Buttons */}
                    <div className="showcase-actions" style={{ paddingTop: '0', marginTop: '-0.25rem' }}>
                      <button
                        onClick={() => handleRotate(activeWp.index, 'ccw')}
                        className="showcase-btn"
                        style={{ flex: 1, fontSize: '0.85rem' }}
                        disabled={loading}
                      >
                        Rotate ↺
                      </button>
                      <button
                        onClick={() => handleRotate(activeWp.index, 'cw')}
                        className="showcase-btn"
                        style={{ flex: 1, fontSize: '0.85rem' }}
                        disabled={loading}
                      >
                        Rotate ↻
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Gallery of Options */}
          <div className="gallery-section">
            <h2 className="results-title">Generated Options for <span>"{currentResult.query}"</span> (Total: {currentResult.wallpapers.length})</h2>
            <div className="gallery-grid">
              {currentResult.wallpapers.map((wp, index) => {
                const isDesktop = wp.source_type === 'desktop';
                return (
                  <div 
                    key={index} 
                    className={`gallery-card ${selectedWallpaperIdx === index ? 'active' : ''}`}
                    onClick={() => setSelectedWallpaperIdx(index)}
                    style={{ borderColor: selectedWallpaperIdx === index ? '' : isDesktop ? 'rgba(59,130,246,0.15)' : 'rgba(16,185,129,0.15)' }}
                  >
                    <div className={`gallery-badge ${isDesktop ? 'desktop' : 'mobile'}`}>
                      Option #{index + 1} {isDesktop ? '🖥️' : '📱'}
                    </div>
                    <div className="gallery-thumb-container" style={{ aspectRatio: isDesktop ? '16/10' : '10/16', maxHeight: '180px' }}>
                      <img
                        src={`${BACKEND_URL}${wp.original_local}?t=${cacheBuster}`}
                        alt={wp.title}
                        className="gallery-thumb"
                        style={{ objectFit: 'cover' }}
                      />
                    </div>
                    <div className="gallery-info">
                      <div className="gallery-name">{wp.title || `Wallpaper Option ${index + 1}`}</div>
                      <div className="gallery-index">Select to preview & download</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* History Section */}
      {history.length > 0 && (
        <section className="history-section">
          <h2 className="results-title">Past Generations Gallery</h2>
          <div className="history-grid">
            {history.map((item) => (
              <div 
                key={item.id} 
                className="history-card"
                onClick={() => handleHistoryClick(item)}
              >
                <div className="history-thumb-container">
                  <img
                    src={`${BACKEND_URL}${item.wallpapers && item.wallpapers[0] ? item.wallpapers[0].original_local : item.original_local}?t=${cacheBuster}`}
                    alt={item.query}
                    className="history-thumb"
                  />
                </div>
                <div className="history-info">
                  <div className="history-query">{item.query}</div>
                  <div className="history-date">
                    {new Date(item.timestamp * 1000).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </div>
                  <div className="history-count">
                    {item.wallpapers ? `${item.wallpapers.length} assets` : '1 asset'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Full-Screen Preview Modal */}
      {previewImageUrl && (
        <div className="preview-modal" onClick={() => setPreviewImageUrl(null)}>
          <div className="preview-modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="preview-modal-close" onClick={() => setPreviewImageUrl(null)}>×</button>
            <img 
              src={`${previewImageUrl}${previewImageUrl.includes('?') ? '&' : '?'}t=${cacheBuster}`} 
              alt="Full Preview" 
              className="preview-modal-img" 
              style={{ objectFit: 'contain' }}
            />
            <div className="preview-modal-footer">
              <span className="preview-modal-title">{previewTitle}</span>
              <button 
                onClick={() => handleDownload(`${previewImageUrl}${previewImageUrl.includes('?') ? '&' : '?'}t=${cacheBuster}`, 'preview.jpg')} 
                className="showcase-btn primary-btn"
                style={{ padding: '0.6rem 1.5rem', fontSize: '0.9rem', width: 'auto' }}
              >
                Download Image
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
