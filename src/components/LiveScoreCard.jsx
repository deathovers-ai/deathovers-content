import React, { useState, useEffect } from 'react';
import './LiveScoreCard.css';

export default function LiveScoreCard() {
  const [matchData, setMatchData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;

    const fetchLiveScores = async () => {
      try {
        const response = await fetch('https://deathovers-ai-engine.onrender.com/api/live-scores', { signal });
        const json = await response.json();
        
        if (json.mode === 'live') {
          setMatchData(json.data);
        } else {
          setMatchData(null); 
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Pipeline Error:', error);
        }
      } finally {
        setLoading(false);
      }
    };

    fetchLiveScores();
    const interval = setInterval(fetchLiveScores, 30000);

    return () => {
      clearInterval(interval);
      controller.abort();
    };
  }, []);

  if (loading) return <div className="do-card-wrapper text-white text-center py-10 font-mono">INITIALIZING PIPELINE...</div>;
  if (!matchData) return <div className="do-card-wrapper text-white text-center py-10 font-mono">NO LIVE MATCHES</div>;

  const matchName = matchData.match || "Match";
  const homeScoreData = matchData.score?.home?.score || "-";
  const homeOversData = matchData.score?.home?.info || "";
  const awayScoreData = matchData.score?.away?.score || "-";
  const awayOversData = matchData.score?.away?.info || "";
  
  // Extracting short team codes (e.g., 'ENG' or 'SA')
  const teams = matchData.match.split(' vs ');
  const homeCode = teams[0] ? teams[0].substring(0, 3).toUpperCase() : "TBD";
  const awayCode = teams[1] ? teams[1].substring(0, 3).toUpperCase() : "TBD";

  return (
    <div className="do-card-wrapper">
      <div className="card">
        <div className="accent-bar"></div>

        <div className="header">
          <div className="header-top">
            <span className="series">{matchName}</span>
            <div className="live-indicator">
              <div className="live-dot"></div>
              <span className="live-label">LIVE</span>
            </div>
          </div>
          <div className="venue">DeathOvers Live Feed</div>
        </div>

        <div className="score-block">
          <div className="team-row dim">
            <div className="team-left">
              <span className="team-code">{homeCode}</span>
            </div>
            <div className="team-score dim">
              {homeScoreData} <span className="overs">({homeOversData})</span>
            </div>
          </div>
          
          <div className="team-row">
            <div className="team-left">
              <span className="team-code">{awayCode}</span>
              <span className="bat-arrow">▸</span>
            </div>
            <div className="team-score">
              {awayScoreData} <span className="overs">({awayOversData})</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
