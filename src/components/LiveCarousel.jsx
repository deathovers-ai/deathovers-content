.carousel-track { display: flex; gap: 12px; overflow-x: auto; padding: 0 24px 12px; min-height: 160px; }
        
        .match-card { 
          background: var(--outfield); 
          border: 1px solid rgba(240,242,245,0.08); 
          border-radius: 4px; 
          width: 280px; 
          min-height: 135px; /* STOPS THE COLLAPSE */
          flex-shrink: 0; 
          padding: 16px; 
          position: relative; 
          cursor: pointer; 
          transition: border-color 0.15s ease, transform 0.2s ease; 
          display: flex; 
          flex-direction: column; 
          justify-content: space-between;
        }
