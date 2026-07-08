import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeMatchId, setActiveMatchId] = useState(null);
  const [activeData, setActiveData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('inn2');

  // API Config
  const API_HEADERS = {
    "x-rapidapi-host": "cricket-highlights-api.p.rapidapi.com",
    "x-rapidapi-key": "YOUR_RAPIDAPI_KEY_HERE" 
  };

  useEffect(() => {
    const fetchMatches = async () => {
      try {
        const res = await fetch('https://cricket-highlights-api.p.rapidapi.com/matches', { headers: API_HEADERS });
        const json = await res.json();
        // Highlightly returns paginated matches in json.data
        setMatches(json.data || []);
      } catch (err) { console.error(err); } finally { setLoading(false); }
    };
    fetchMatches();
  }, []);

  const openMatch = async (matchId) => {
    setActiveMatchId(matchId);
    setDetailLoading(true);
    try {
      const res = await fetch(`https://cricket-highlights-api.p.rapidapi.com/matches/${matchId}`, { headers: API_HEADERS });
      const json = await res.json();
      // API returns an array, take the first detailed match object
      setActiveData(json[0]); 
    } catch (err) { console.error(err); } finally { setDetailLoading(false); }
  };

  if (loading) return <div className="loading-state">SYNCHRONIZING WITH HIGHLIGHTLY...</div>;

  return (
    <div className="live-engine-wrapper">
      {!activeMatchId ? (
        <div className="carousel-track">
          {matches.map((m) => (
            <div key={m.id} className="match-card" onClick={() => openMatch(m.id)}>
              <div className="series-tag">{m.league.name}</div>
              <div className="team-code">{m.homeTeam.abbreviation} vs {m.awayTeam.abbreviation}</div>
              <div className="chase-line">{m.state.description}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="matchpage">
          <button onClick={() => setActiveMatchId(null)}>← BACK</button>
          {detailLoading ? <div>LOADING DATA...</div> : (
            <div className="mp-content-panoramic">
              {/* Column 1: 1st Innings Data from activeData.statistics[0] */}
              <div className="innings-col">
                <div className="inn-heading highlight-inn1">1ST INNINGS</div>
                <table className="stat-table">
                  <thead><tr><th>BATTER</th><th>R</th><th>B</th></tr></thead>
                  <tbody>
                    {activeData.statistics[0].inningBatsmen.map((b, i) => (
                      <tr key={i}><td>{b.player.name}</td><td>{b.runs}</td><td>{b.balls}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Column 2: 2nd Innings Data from activeData.statistics[1] */}
              <div className="innings-col border-left">
                <div className="inn-heading highlight-inn2">2ND INNINGS</div>
                {/* Map activeData.statistics[1] similarly */}
              </div>
              {/* Column 3: Highlights (Replacing Text Commentary) */}
              <div className="mp-commentary-rail border-left">
                 {/* Map activeData.highlights here if needed */}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
