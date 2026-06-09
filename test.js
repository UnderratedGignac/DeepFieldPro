
        function showToast(msg, type='success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            const bg = type === 'success' ? 'rgba(0,255,100,0.15)' : (type === 'error' ? 'rgba(255,77,77,0.15)' : 'rgba(229,193,88,0.15)');
            const border = type === 'success' ? '#00ff88' : (type === 'error' ? '#ff4d4d' : 'var(--primary)');
            toast.style.cssText = `background:var(--surface-color); border-left:4px solid ${border}; padding:15px 20px; border-radius:8px; color:var(--text-main); display:flex; align-items:center; gap:10px; box-shadow:0 10px 30px rgba(0,0,0,0.3); animation: slideInRight 0.3s ease forwards; z-index:9999;`;
            toast.innerHTML = `<i class="fa-solid ${type==='success'?'fa-check-circle':(type==='error'?'fa-circle-xmark':'fa-info-circle')}" style="color:${border}; font-size: 1.2rem;"></i> <span>${msg}</span>`;
            container.appendChild(toast);
            setTimeout(() => { toast.style.animation = 'slideOutRight 0.3s ease forwards'; setTimeout(()=>toast.remove(), 300); }, 4000);
        }

        // Desktop Notifications
        if ("Notification" in window) {
            if (Notification.permission !== "granted" && Notification.permission !== "denied") {
                Notification.requestPermission();
            }
        }

        function sendDesktopNotification(title, body) {
            if ("Notification" in window && Notification.permission === "granted") {
                new Notification(title, { body: body });
            }
        }

        // Bet Slip Logic
        let betSlip = [];

        function toggleBetSlip(open) {
            const drawer = document.getElementById('bet-slip-drawer');
            if (open) {
                drawer.classList.add('open');
            } else {
                drawer.classList.remove('open');
            }
        }

        function addToSlip(match, market, selection, prob, odds, recommended) {
            const existingId = betSlip.findIndex(b => b.match === match && b.selection === selection);
            if (existingId > -1) {
                showToast("Selection already in Bet Slip.", "error");
                toggleBetSlip(true);
                return;
            }
            betSlip.push({ id: Date.now(), match, market, selection, prob, odds, recommended, stake: 100 });
            renderBetSlip();
            toggleBetSlip(true);
            showToast("Added to Bet Slip", "success");
        }

        function removeFromSlip(id) {
            betSlip = betSlip.filter(b => b.id !== id);
            renderBetSlip();
        }

        function updateStake(id, value) {
            const bet = betSlip.find(b => b.id === id);
            if (bet) {
                bet.stake = parseFloat(value) || 0;
                updateSlipTotal();
            }
        }

        function updateSlipTotal() {
            const total = betSlip.reduce((sum, b) => sum + b.stake, 0);
            document.getElementById('slip-total-stake').innerText = `$${total.toFixed(2)}`;
            document.getElementById('slip-count').innerText = betSlip.length;
        }

        function renderBetSlip() {
            const body = document.getElementById('slip-body');
            if (betSlip.length === 0) {
                body.innerHTML = `<div style="text-align:center; color:var(--text-muted); margin-top:50px;">Your bet slip is empty.<br><br><i class="fa-solid fa-box-open" style="font-size:2rem; opacity:0.5;"></i></div>`;
                updateSlipTotal();
                return;
            }

            body.innerHTML = betSlip.map(b => `
                <div class="slip-item">
                    <button class="remove-btn" onclick="removeFromSlip(${b.id})"><i class="fa-solid fa-trash"></i></button>
                    <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:5px;">${b.match}</div>
                    <div style="font-weight:700; color:var(--text-main); margin-bottom:5px;">${b.selection} <span style="color:var(--primary);">@ ${b.odds.toFixed(2)}</span></div>
                    <div style="font-size:0.7rem; color:var(--secondary); margin-bottom:10px;">Market: ${b.market} | AI Prob: ${b.prob}%</div>
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="font-size:0.8rem; font-weight:700;">Stake ($):</span>
                        <input type="number" class="slip-input" value="${b.stake}" onchange="updateStake(${b.id}, this.value)" onkeyup="updateStake(${b.id}, this.value)" style="margin:0; flex:1;">
                    </div>
                </div>
            `).join('');
            updateSlipTotal();
        }

        async function submitBetSlip() {
            if (betSlip.length === 0) return;
            const totalStake = betSlip.reduce((sum, b) => sum + b.stake, 0);
            if (!confirm(`Are you sure you want to place ${betSlip.length} bets for a total of $${totalStake.toFixed(2)}?`)) return;
            
            const btn = document.querySelector('#bet-slip-drawer .btn-primary');
            btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Placing...';
            btn.disabled = true;

            let successCount = 0;
            for (const bet of betSlip) {
                try {
                    const res = await fetch('/api/place_bet', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({match: bet.match, market: bet.market, selection: bet.selection, prob: bet.prob, odds: bet.odds, recommended: bet.recommended, stake: bet.stake})
                    });
                    if (res.ok) successCount++;
                } catch(e) {
                    console.error("Failed to place", bet);
                }
            }

            btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Place All Bets';
            btn.disabled = false;

            if (successCount > 0) {
                showToast(`Successfully placed ${successCount}/${betSlip.length} bets!`, 'success');
                betSlip = [];
                renderBetSlip();
                toggleBetSlip(false);
                loadBankroll();
                loadTracker();
            } else {
                showToast('Failed to place bets. Check ledger.', 'error');
            }
        }
        function switchView(viewId, element) {
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            document.getElementById(viewId).classList.add('active');
            
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            element.classList.add('active');

            const titles = {
                'live-view': 'Live Match Radar',
                'bankroll-view': 'Capital Overview',
                'tracker-view': 'Execution Ledger',
                'settings-view': 'Engine Configuration',
                'performance-view': 'User vs AI Performance',
                'comparison-view': 'AI vs Reality Comparisons',
                'stair-view': 'Stair AI API Bets',
                'parlay-view': 'Parlay Intelligence'
            };
            document.getElementById('page-title').innerText = titles[viewId] || 'DeepFieldPro';
            
            const paths = {
                'live-view': '/',
                'bankroll-view': '/bankroll',
                'tracker-view': '/tracker',
                'settings-view': '/settings',
                'performance-view': '/performance',
                'comparison-view': '/comparison',
                'stair-view': '/stair',
                'parlay-view': '/parlays'
            };
            if(paths[viewId] && window.location.pathname !== paths[viewId]) {
                history.pushState(null, '', paths[viewId]);
            }
            
            if(viewId === 'performance-view') {
                loadPerformance();
            } else if(viewId === 'tracker-view') {
                loadTracker();
            } else if(viewId === 'bankroll-view') {
                loadBankroll();
            } else if(viewId === 'comparison-view') {
                loadComparisonList();
            } else if(viewId === 'stair-view') {
                loadStairBets();
            } else if(viewId === 'parlay-view') {
                loadParlays();
            } else if(viewId === 'settled-view') {
                loadSettledLedger();
            }
        }

        async function loadSettledLedger() {
            try {
                const res = await fetch('/api/settled_ledger');
                const data = await res.json();
                
                const parlayBody = document.getElementById('ledger-parlay-body');
                const singleBody = document.getElementById('ledger-single-body');
                
                let totalPnL = 0;
                let wins = 0;
                let losses = 0;
                let turnover = 0;

                // Render Parlays
                if(data.parlays.length === 0) {
                    parlayBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No settled parlays found.</td></tr>';
                } else {
                    parlayBody.innerHTML = data.parlays.map(p => {
                        totalPnL += p.pnl || 0;
                        turnover += p.stake || 0;
                        if(p.result === 'W') wins++; else losses++;
                        
                        const legs = JSON.parse(p.legs_json);
                        const legsList = legs.map(l => `<div style="font-size:0.7rem;">• ${l.match}: ${l.selection}</div>`).join('');
                        
                        return `<tr>
                            <td>${new Date(p.placed_at).toLocaleString()}</td>
                            <td>${legsList}</td>
                            <td>@ ${p.total_odds}</td>
                            <td>$${p.stake.toFixed(2)}</td>
                            <td><span class="${p.result === 'W' ? 'tag-win' : 'tag-loss'}">${p.result}</span></td>
                            <td style="color:${p.pnl >= 0 ? '#00ff88' : '#ff4d4d'}; font-weight:700;">$${(p.pnl || 0).toFixed(2)}</td>
                        </tr>`;
                    }).join('');
                }

                // Render Singles
                if(data.singles.length === 0) {
                    singleBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No settled bets found.</td></tr>';
                } else {
                    singleBody.innerHTML = data.singles.map(s => {
                        totalPnL += s.pnl || 0;
                        turnover += s.stake || 0;
                        if(s.result === 'W') wins++; else losses++;
                        
                        return `<tr>
                            <td>${new Date(s.placed_at).toLocaleString()}</td>
                            <td><strong>${s.match_id}</strong><br><span style="font-size:0.75rem;">${s.player_id || s.market_type}</span></td>
                            <td>@ ${s.entry_odds}</td>
                            <td>$${s.stake.toFixed(2)}</td>
                            <td><span class="${s.result === 'W' ? 'tag-win' : 'tag-loss'}">${s.result}</span></td>
                            <td style="color:${s.pnl >= 0 ? '#00ff88' : '#ff4d4d'}; font-weight:700;">$${(s.pnl || 0).toFixed(2)}</td>
                        </tr>`;
                    }).join('');
                }

                document.getElementById('ledger-total-pnl').innerText = `$${totalPnL.toFixed(2)}`;
                document.getElementById('ledger-total-pnl').style.color = totalPnL >= 0 ? '#00ff88' : '#ff4d4d';
                document.getElementById('ledger-total-wins').innerText = wins;
                document.getElementById('ledger-total-losses').innerText = losses;
                document.getElementById('ledger-total-turnover').innerText = `$${turnover.toFixed(2)}`;

            } catch(e) {
                console.error(e);
            }
        }

        async function doPlaceParlay(parlayData) {
            if(!confirm(`Confirm placement of this ${parlayData.size}-leg parlay with $${parlayData.recommended_stake} stake?`)) return;
            try {
                const res = await fetch('/api/place_parlay', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(parlayData)
                });
                if(res.ok) {
                    showToast("Parlay successfully logged to P&L Ledger!", "success");
                    loadParlays();
                }
            } catch(e) {
                showToast("Failed to log parlay.", "error");
            }
        }

        let parlayPnLChartInstance = null;
        let parlayTrustChartInstance = null;

        async function loadParlays() {
            const grid = document.getElementById('parlay-grid');
            try {
                const res = await fetch('/api/smart_parlays');
                const data = await res.json();
                
                if (!data.top_parlays || data.top_parlays.length === 0) {
                    grid.innerHTML = '<div class="placeholder-box" style="width:100%;"><h3>No parlays found</h3><p>Run the parlay intelligence model to generate new combinations.</p></div>';
                    return;
                }

                grid.innerHTML = '';
                
                // Real KPI Updates
                const totalStaked = data.top_parlays.reduce((acc, p) => acc + (p.recommended_stake || 0), 0);
                const potentialReturn = data.top_parlays.reduce((acc, p) => acc + (p.recommended_stake * p.total_odds), 0);
                
                document.getElementById('parlay-kpi-staked').innerText = `$${totalStaked.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('parlay-kpi-pending').innerText = data.top_parlays.length;
                document.getElementById('parlay-kpi-return').innerText = `$${potentialReturn.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

                data.top_parlays.forEach((p, idx) => {
                    const card = document.createElement('div');
                    card.className = 'match-card';
                    card.style.borderLeft = `5px solid ${p.parlay_trust_score > 70 ? '#00ff88' : 'var(--primary)'}`;
                    
                    let legsHTML = p.legs.map(l => `
                        <div style="margin-bottom:10px; padding-bottom:10px; border-bottom:1px solid var(--border-color);">
                            <div style="font-size:0.75rem; color:var(--text-muted);">${l.match}</div>
                            <div style="font-weight:700; display:flex; justify-content:space-between;">
                                <span>${l.selection} (${l.market})</span>
                                <span style="color:var(--primary);">@ ${l.odds.toFixed(2)}</span>
                            </div>
                            <div style="font-size:0.65rem; color:var(--secondary);">Trust: ${l.trust}%</div>
                        </div>
                    `).join('');

                    card.innerHTML = `
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:15px;">
                            <span style="background:var(--primary); color:var(--bg-color); padding:4px 10px; border-radius:4px; font-weight:800; font-size:0.75rem;">${p.size}-LEG SMART PARLAY</span>
                            <span style="color:var(--primary); font-weight:900; font-size:1.2rem;">@ ${p.total_odds}</span>
                        </div>
                        ${legsHTML}
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:15px;">
                            <div class="stat-item" style="background:rgba(0,0,0,0.2);">
                                <div class="stat-label">Trust Score</div>
                                <div class="stat-value" style="color:#00ff88;">${p.parlay_trust_score}%</div>
                            </div>
                            <div class="stat-item" style="background:rgba(0,0,0,0.2);">
                                <div class="stat-label">Expected EV</div>
                                <div class="stat-value" style="color:var(--primary);">${p.combined_ev}%</div>
                            </div>
                        </div>
                        <div style="margin-top:15px; font-weight:700; color:var(--text-muted); font-size:0.8rem; display: flex; justify-content: space-between; align-items: center;">
                            <span>Recommended Stake: <span style="color:var(--text-main); font-size:1rem;">$${p.recommended_stake}</span></span>
                            <span style="color:#00ff88;">Pot. Payout: $${(p.recommended_stake * p.total_odds).toFixed(2)}</span>
                        </div>
                        <button class="btn-primary" style="width:100%; margin-top:15px; padding:10px;" onclick='doPlaceParlay(${JSON.stringify(p)})'>
                            <i class="fa-solid fa-bolt"></i> PLACE PARLAY
                        </button>
                    `;
                    grid.appendChild(card);
                });

                // Charts
                const ctxPnL = document.getElementById('parlayPnLChart').getContext('2d');
                if(parlayPnLChartInstance) parlayPnLChartInstance.destroy();
                parlayPnLChartInstance = new Chart(ctxPnL, {
                    type: 'line',
                    data: {
                        labels: ['Start', ...data.top_parlays.map((_, i) => `P${i+1}`)],
                        datasets: [{
                            label: 'Equity Curve (Simulated)',
                            data: [0, ...data.top_parlays.map((p, i) => (i + 1) * 25)], // Still simulated until we have history, but labeled as such
                            borderColor: '#00ff88',
                            backgroundColor: 'rgba(0, 255, 136, 0.1)',
                            fill: true,
                            tension: 0.4
                        }]
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
                });

                const ctxTrust = document.getElementById('parlayTrustChart').getContext('2d');
                if(parlayTrustChartInstance) parlayTrustChartInstance.destroy();
                parlayTrustChartInstance = new Chart(ctxTrust, {
                    type: 'bar',
                    data: {
                        labels: data.top_parlays.map((_, i) => `P${i+1}`),
                        datasets: [
                            { label: 'Trust', data: data.top_parlays.map(p => p.parlay_trust_score), backgroundColor: '#E5C158' },
                            { label: 'EV %', data: data.top_parlays.map(p => p.combined_ev), backgroundColor: '#1B3B2B' }
                        ]
                    },
                    options: { responsive: true, maintainAspectRatio: false }
                });

            } catch(e) {
                console.error(e);
                grid.innerHTML = '<div style="color:#ff4d4d; padding:20px;">Failed to load parlays.</div>';
            }
        }

        // Live Dashboard Logic
        const dashboard = document.getElementById('dashboard');
        const loader = document.getElementById('loader');
        const countdownEl = document.getElementById('countdown');
        let refreshTimer = 30;
        let currentMatchFilter = 'all';
        let cachedMatches = [];
        let previousMatches = {};

        function renderSkeletons() {
            dashboard.innerHTML = Array(6).fill(`
                <div class="skel-card">
                    <div class="skeleton skel-title"></div>
                    <div class="skeleton skel-time"></div>
                    <div class="skeleton skel-box"></div>
                    <div class="skeleton skel-time" style="width: 80%;"></div>
                </div>
            `).join('');
        }

        // Real-Time Streaming via Server-Sent Events
        let eventSource = null;

        function connectSSE() {
            if (cachedMatches.length === 0) {
                loader.style.display = 'none';
                renderSkeletons();
            }
            if (eventSource) {
                eventSource.close();
            }
            eventSource = new EventSource('/api/stream');
            
            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    processNewData(data);
                } catch (e) {
                    console.error("SSE Parse Error", e);
                }
            };
            
            eventSource.onerror = function(err) {
                console.error("SSE Connection Error. Attempting to reconnect...", err);
                eventSource.close();
                setTimeout(connectSSE, 5000);
            };
        }

        async function fetchState() {
            // Manual refresh fallback
            try {
                const res = await fetch('/api/state');
                if (!res.ok) throw new Error("State not found");
                const data = await res.json();
                processNewData(data);
            } catch (err) {
                console.error(err);
            }
        }

        function processNewData(data) {
            let needsRender = false;
            
            data.forEach(m => {
                const matchId = m.match;
                const prev = previousMatches[matchId];
                
                if (prev) {
                    // Check for goals
                    const prevGoals = prev.goals ? prev.goals.length : 0;
                    const currGoals = m.goals ? m.goals.length : 0;
                    if (currGoals > prevGoals) {
                        sendDesktopNotification('⚽ GOAL!', `Goal scored in ${matchId}`);
                        showToast(`Goal scored in ${matchId}!`, 'success');
                    }
                    
                    // Mark odds differences for flashing
                    if (m.prematch_markets && prev.prematch_markets) {
                        for (const market in m.prematch_markets) {
                            if (prev.prematch_markets[market]) {
                                m.prematch_markets[market].forEach((sel, idx) => {
                                    const prevSel = prev.prematch_markets[market][idx];
                                    if (prevSel && sel.odds > prevSel.odds) {
                                        sel.flashClass = 'flash-up';
                                        needsRender = true;
                                    } else if (prevSel && sel.odds < prevSel.odds) {
                                        sel.flashClass = 'flash-down';
                                        needsRender = true;
                                    }
                                });
                            }
                        }
                    }
                } else {
                    // New match
                    if (m.prediction && m.prediction.detailed_prediction && m.prediction.detailed_prediction.confidence >= 8) {
                        sendDesktopNotification('🚀 High Confidence Bet', `AI found edge in ${matchId}`);
                        showToast(`High Confidence AI Edge found in ${matchId}`, 'success');
                    }
                    needsRender = true;
                }
                previousMatches[matchId] = m;
            });
            
            cachedMatches = data;
            renderDashboard(cachedMatches);
        }

        function setMatchFilter(filterType, element) {
            currentMatchFilter = filterType;
            document.querySelectorAll('.filter-pill').forEach(el => el.classList.remove('active'));
            if (element) {
                element.classList.add('active');
            } else {
                const buttons = document.querySelectorAll('.filter-pill');
                if (filterType === 'all' && buttons.length > 0) buttons[0].classList.add('active');
                else if (filterType === 'live' && buttons.length > 1) buttons[1].classList.add('active');
                else if (filterType === 'upcoming' && buttons.length > 2) buttons[2].classList.add('active');
                else if (filterType === 'finished' && buttons.length > 3) buttons[3].classList.add('active');
            }
            renderDashboard(cachedMatches);
        }

        function formatTime(isoStr) {
            const date = new Date(isoStr);
            return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }

        function renderDashboard(matches) {
            dashboard.innerHTML = '';

            const searchInput = document.getElementById('search-input')?.value.toLowerCase() || '';
            const sortSelect = document.getElementById('sort-select')?.value || 'time';
            
            let filteredMatches = matches;

            if (currentMatchFilter === 'live') {
                filteredMatches = filteredMatches.filter(m => {
                    const status = (m.status_code || '').toLowerCase();
                    return ['1h', '2h', 'ht', 'live', 'inprogress', 'in_progress', 'live-now'].includes(status) || status.includes('progress');
                });
            } else if (currentMatchFilter === 'upcoming') {
                filteredMatches = filteredMatches.filter(m => {
                    const status = (m.status_code || '').toLowerCase();
                    return ['ns', 'upcoming', 'not_started', 'not started'].includes(status) || status.includes('upcoming') || status.includes('start');
                });
            } else if (currentMatchFilter === 'finished') {
                filteredMatches = filteredMatches.filter(m => {
                    const status = (m.status_code || '').toLowerCase();
                    return ['ft', 'finished', 'completed', 'aet', 'pen'].includes(status) || status.includes('finish') || status.includes('complete');
                });
            }

            if (searchInput) {
                filteredMatches = filteredMatches.filter(m => 
                    m.match.toLowerCase().includes(searchInput) || 
                    (m.league && m.league.toLowerCase().includes(searchInput))
                );
            }

            if (filteredMatches.length === 0) {
                dashboard.innerHTML = `
                    <div class="placeholder-box" style="grid-column: 1 / -1; width: 100%; box-sizing: border-box; animation: fadeIn 0.4s ease-out;">
                        <i class="fa-solid fa-gamepad" style="font-size: 3rem; color: var(--border-color); margin-bottom: 20px;"></i>
                        <h3 style="color: var(--text-main); font-size: 1.5rem; margin-bottom: 10px;">No Matches Found</h3>
                        <p style="color: var(--text-muted); font-size: 0.9rem;">There are no games matching the "${currentMatchFilter}" filter at the moment.</p>
                    </div>
                `;
                return;
            }

            if (sortSelect === 'confidence') {
                filteredMatches.sort((a, b) => {
                    const confA = a.prediction?.detailed_prediction?.confidence || 0;
                    const confB = b.prediction?.detailed_prediction?.confidence || 0;
                    if (confA !== confB) return confB - confA;
                    
                    const evA = a.prediction?.markets?.['Match Result']?.[0]?.prob || 0;
                    const evB = b.prediction?.markets?.['Match Result']?.[0]?.prob || 0;
                    return evB - evA;
                });
            } else if (sortSelect === 'league') {
                filteredMatches.sort((a, b) => (a.league || '').localeCompare(b.league || ''));
            } else {
                // Default: Sort by Time (and Lineup presence)
                filteredMatches.sort((a, b) => {
                    const aHasLineup = a.has_lineup ? 1 : 0;
                    const bHasLineup = b.has_lineup ? 1 : 0;
                    if (aHasLineup !== bHasLineup) return bHasLineup - aHasLineup;
                    
                    const aHasPred = a.prediction ? 1 : 0;
                    const bHasPred = b.prediction ? 1 : 0;
                    if (aHasPred !== bHasPred) return bHasPred - aHasPred;
                    
                    return new Date(a.kickoff) - new Date(b.kickoff);
                });
            }

            filteredMatches.forEach((match, index) => {
                const card = document.createElement('div');
                card.className = 'match-card';
                card.style.animationDelay = `${index * 0.03}s`;

                let lineupBadge = '';
                if (match.prediction) {
                    if (match.has_lineup) {
                        lineupBadge = `<span style="background:rgba(0,255,100,0.12); color:#00ff88; font-size:0.65rem; font-weight:700; padding:3px 8px; border-radius:12px; border:1px solid rgba(0,255,100,0.25); display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-circle-check"></i> OFFICIAL XI</span>`;
                    } else {
                        lineupBadge = `<span style="background:rgba(229,193,88,0.12); color:var(--primary); font-size:0.65rem; font-weight:700; padding:3px 8px; border-radius:12px; border:1px solid rgba(229,193,88,0.25); display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-hourglass-half"></i> ESTIMATED XI</span>`;
                    }
                } else {
                    lineupBadge = `<span style="background:rgba(255,255,255,0.05); color:var(--text-muted); font-size:0.65rem; font-weight:700; padding:3px 8px; border-radius:12px; border:1px solid var(--border-color); display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-lock"></i> NO XI</span>`;
                }

                let contentHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <div class="league-badge" style="margin:0;">${match.league}</div>
                        ${lineupBadge}
                    </div>
                    <h2 class="match-title">${match.match}</h2>
                    <div class="kickoff"><i class="fa-solid fa-clock"></i> Kickoff: ${formatTime(match.kickoff)}</div>
                `;

                if (match.prediction) {
                    const p = match.prediction;
                    const formatPlayers = (players) => players.map(pl => `${pl.name} (${pl.impact})`).join(', ');

                    contentHTML += `
                        <div class="prediction-box">
                            <div class="pred-winner"><i class="fa-solid fa-crown"></i> ${p.prediction}</div>
                            <div class="pred-score">Score Target: ${p.expected_score}</div>
                            
                            <div class="stat-grid">
                                <div class="stat-item">
                                    <div class="stat-label">Impact Agg.</div>
                                    <div class="stat-value">${p.team_impacts}</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">Exp. Corners</div>
                                    <div class="stat-value">${p.corners}</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">Exp. Fouls</div>
                                    <div class="stat-value">${p.fouls}</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">Yellow Cards</div>
                                    <div class="stat-value">${p.cards}</div>
                                </div>
                            </div>

                            <div class="impact-players">
                                <div class="player-row"><strong><i class="fa-solid fa-arrow-trend-up"></i> Home Alphas:</strong> ${formatPlayers(p.home_players)}</div>
                                <div class="player-row"><strong><i class="fa-solid fa-arrow-trend-up"></i> Away Alphas:</strong> ${formatPlayers(p.away_players)}</div>
                            </div>
                        </div>
                    `;

                    if(p.markets) {
                        contentHTML += `<div class="market-section"><h4 style="color:var(--secondary);margin-bottom:10px;"><i class="fa-solid fa-store"></i> Betarabia Markets</h4>`;
                        for(const [marketName, selections] of Object.entries(p.markets)) {
                            contentHTML += `<div style="font-size:0.75rem; color:var(--text-muted); margin-top:8px; margin-bottom:4px;">${marketName}</div>`;
                            selections.forEach(sel => {
                                let recBadge = '';
                                if(sel.recommended) {
                                    recBadge = `<span style="background:linear-gradient(135deg, var(--primary), var(--secondary)); color:var(--bg-color); font-weight:700; padding:2px 6px; border-radius:4px; font-size:0.65rem; text-transform:uppercase; margin-left:8px;">RECOMMENDED</span>`;
                                } else if (sel.is_top_pick) {
                                    recBadge = `<span style="background:rgba(255,255,255,0.1); color:var(--text-muted); font-weight:600; padding:2px 6px; border-radius:4px; font-size:0.65rem; text-transform:uppercase; margin-left:8px; border:1px solid rgba(255,255,255,0.2);">AI PICK</span>`;
                                }
                                let skipReasonHTML = '';
                                if(!sel.recommended && sel.skip_reason) {
                                    skipReasonHTML = `<div style="font-size: 0.65rem; color: #ff4d4d; margin-top: 2px; text-align: right; padding-right: 5px; opacity: 0.8;"><i class="fa-solid fa-triangle-exclamation"></i> AI Skipped: ${sel.skip_reason}</div>`;
                                }
                                contentHTML += `
                                <div class="market-row ${sel.flashClass || ''}" style="margin-bottom: 6px; display: flex; flex-direction: column; width: 100%;">
                                    <button class="market-btn" onclick="addToSlip('${p.match}', '${marketName}', '${sel.selection}', ${sel.prob}, ${sel.odds || 0}, ${sel.recommended ? 1 : 0})" style="display:flex; justify-content:space-between; align-items:center; width: 100%;">
                                        <span style="display:flex; align-items:center;">${sel.selection} ${recBadge}</span>
                                        <span style="font-family:'Outfit',sans-serif; font-weight:700;">
                                            <span style="color:var(--text-muted); font-size:0.8rem; margin-right:8px;">${sel.prob}%</span>
                                            <span style="color:var(--primary);">@ ${(sel.odds || 0).toFixed(2)}</span>
                                        </span>
                                    </button>
                                    ${skipReasonHTML}
                                </div>`;
                            });
                        }
                        contentHTML += `</div>`;
                    }
                } else {
                    contentHTML += `
                        <div class="status-pending">
                            <span><i class="fa-solid fa-lock"></i> Awaiting Prediction</span>
                            Daemon is generating expected outcome based on historical performance...
                        </div>
                    `;
                    
                    if (match.prematch_markets) {
                        contentHTML += `<div class="market-section"><h4 style="color:var(--secondary);margin-bottom:10px;"><i class="fa-solid fa-store"></i> Live Betarabia Odds</h4>`;
                        for(const [marketName, selections] of Object.entries(match.prematch_markets)) {
                            if (selections && selections.length > 0) {
                                contentHTML += `<div style="font-size:0.75rem; color:var(--text-muted); margin-top:8px; margin-bottom:4px;">${marketName}</div>`;
                                selections.forEach(sel => {
                                    contentHTML += `
                                    <div class="market-row ${sel.flashClass || ''}" style="margin-bottom: 6px;">
                                        <button class="market-btn" onclick="addToSlip('${match.match}', '${marketName}', '${sel.selection}', 0.0, ${sel.odds}, 0)" style="display:flex; justify-content:space-between; align-items:center;">
                                            <span>${sel.selection}</span>
                                            <span style="font-family:'Outfit',sans-serif; font-weight:700; color:var(--primary);">@ ${sel.odds.toFixed(2)}</span>
                                        </button>
                                    </div>`;
                                });
                            }
                        }
                        contentHTML += `</div>`;
                    }
                }

                card.innerHTML = contentHTML;
                
                card.addEventListener('click', (e) => {
                    if (e.target.closest('button')) return;
                    if (match.prediction && match.prediction.detailed_prediction) {
                        openPredictionModal(match);
                    }
                });

                dashboard.appendChild(card);
            });
        }

        async function placeBet(match, market, selection, prob, odds, recommended) {
            let stake = prompt(`Place Bet on [${match}] - ${market}: ${selection}\n\nLive Odds: @ ${odds.toFixed(2)}\nAI Probability: ${prob}%\n\nEnter Stake ($):`, "100");
            if(stake !== null && stake !== "") {
                try {
                    const res = await fetch('/api/place_bet', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({match, market, selection, prob, odds, recommended, stake})
                    });
                    if(!res.ok) throw new Error("Bet failed");
                    showToast("Bet Transmitted Successfully to Ledger!", "success");
                    loadBankroll();
                    loadTracker();
                } catch(e) {
                    showToast("Failed to place bet.", "error");
                }
            }
        }


        async function loadPerformance() {
            try {
                const res = await fetch('/api/performance');
                const data = await res.json();
                
                document.getElementById('perf-ai-pnl').innerText = `$${data.ai.pnl.toLocaleString()}`;
                document.getElementById('perf-ai-pnl').style.color = data.ai.pnl >= 0 ? 'var(--primary)' : '#ff4d4d';
                document.getElementById('perf-ai-winrate').innerText = `Win Rate: ${data.ai.win_rate}% (${data.ai.wins}W - ${data.ai.losses}L)`;
                
                document.getElementById('perf-user-pnl').innerText = `$${data.user.pnl.toLocaleString()}`;
                document.getElementById('perf-user-pnl').style.color = data.user.pnl >= 0 ? 'var(--primary)' : '#ff4d4d';
                document.getElementById('perf-user-winrate').innerText = `Win Rate: ${data.user.win_rate}% (${data.user.wins}W - ${data.user.losses}L)`;
                
                document.getElementById('perf-user-rec-pnl').innerText = `$${data.user_rec.pnl.toLocaleString()}`;
                document.getElementById('perf-user-rec-pnl').style.color = data.user_rec.pnl >= 0 ? '#00ff88' : '#ff4d4d';
                document.getElementById('perf-user-rec-stats').innerText = `Win Rate: ${data.user_rec.win_rate}% | Total: ${data.user_rec.total} bets`;
                
                document.getElementById('perf-user-own-pnl').innerText = `$${data.user_own.pnl.toLocaleString()}`;
                document.getElementById('perf-user-own-pnl').style.color = data.user_own.pnl >= 0 ? '#00ff88' : '#ff4d4d';
                document.getElementById('perf-user-own-stats').innerText = `Win Rate: ${data.user_own.win_rate}% | Total: ${data.user_own.total} bets`;
                
                const aiBody = document.querySelector('#perf-ai-table tbody');
                if (data.raw_ai_bets.length === 0) {
                    aiBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No AI recommended bets yet.</td></tr>';
                } else {
                    aiBody.innerHTML = data.raw_ai_bets.map(b => {
                        let tag = `<span class="tag-open">OPEN</span>`;
                        let actionButtons = '';
                        if (b.result === 'W') tag = `<span class="tag-win">WIN</span>`;
                        else if (b.result === 'L') tag = `<span class="tag-loss">LOSS</span>`;
                        else if (b.result === 'VOID') tag = `<span class="tag-loss" style="background:rgba(255,255,255,0.1); color:#aaa;">VOID</span>`;
                        else {
                            actionButtons = '';
                        }
                        let pnlVal = b.pnl ? (b.pnl >= 0 ? `+$${b.pnl.toFixed(2)}` : `-$${Math.abs(b.pnl).toFixed(2)}`) : '-';
                        return `<tr>
                            <td><strong>${b.player_id}</strong><br><span style="font-size:0.75rem; color:var(--text-muted)">${b.market_type}</span></td>
                            <td>${b.entry_odds}</td>
                            <td>$${b.stake}</td>
                            <td style="color: ${b.pnl >= 0 ? '#00ff88' : '#ff4d4d'}">${pnlVal}</td>
                            <td>${tag}${actionButtons}</td>
                        </tr>`;
                    }).join('');
                }
                
                const userBody = document.querySelector('#perf-user-table tbody');
                if (data.raw_user_bets.length === 0) {
                    userBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No bets placed by you yet.</td></tr>';
                } else {
                    userBody.innerHTML = data.raw_user_bets.map(b => {
                        let tag = `<span class="tag-open">OPEN</span>`;
                        let actionButtons = '';
                        if (b.result === 'W') tag = `<span class="tag-win">WIN</span>`;
                        else if (b.result === 'L') tag = `<span class="tag-loss">LOSS</span>`;
                        else if (b.result === 'VOID') tag = `<span class="tag-loss" style="background:rgba(255,255,255,0.1); color:#aaa;">VOID</span>`;
                        else {
                            actionButtons = '';
                        }
                        let pnlVal = b.pnl ? (b.pnl >= 0 ? `+$${b.pnl.toFixed(2)}` : `-$${Math.abs(b.pnl).toFixed(2)}`) : '-';
                        let followTag = b.is_recommended ? `<span style="background:rgba(229,193,88,0.15); color:var(--primary); font-size:0.65rem; padding:1px 4px; border-radius:3px; font-weight:600; margin-left:5px; border: 1px solid rgba(229,193,88,0.3)">AI RECOMMENDED</span>` : `<span style="background:rgba(255,77,77,0.1); color:#ff4d4d; font-size:0.65rem; padding:1px 4px; border-radius:3px; font-weight:600; margin-left:5px; border: 1px solid rgba(255,77,77,0.2)">MY CHOICE</span>`;
                        return `<tr>
                            <td><strong>${b.player_id}</strong> ${followTag}<br><span style="font-size:0.75rem; color:var(--text-muted)">${b.market_type}</span></td>
                            <td>${b.entry_odds}</td>
                            <td>$${b.stake}</td>
                            <td style="color: ${b.pnl >= 0 ? '#00ff88' : '#ff4d4d'}">${pnlVal}</td>
                            <td>${tag}${actionButtons}</td>
                        </tr>`;
                    }).join('');
                }
            } catch (e) {
                console.error("Error loading performance stats:", e);
            }
        }

        setInterval(() => {
            if(document.getElementById('live-view').classList.contains('active')) {
                refreshTimer--;
                if (refreshTimer <= 0) {
                    refreshTimer = 30;
                    fetchState();
                }
                countdownEl.innerText = refreshTimer;
            }
        }, 1000);

        let bankrollChartInstance = null;
        let winLossChartInstance = null;

        // Fetch Bankroll
        async function loadBankroll() {
            try {
                const res = await fetch('/api/bankroll');
                const data = await res.json();
                document.getElementById('kpi-capital').innerText = `$${data.current.toLocaleString()}`;
                document.getElementById('kpi-roi').innerText = `${data.roi > 0 ? '+' : ''}${data.roi}%`;
                document.getElementById('kpi-pnl').innerText = `$${data.pnl.toLocaleString()}`;
                
                try {
                    const stairRes = await fetch('/api/stair_balance');
                    if (stairRes.ok) {
                        const sData = await stairRes.json();
                        document.getElementById('kpi-stair-wallet').innerText = `$${parseFloat(sData.available).toLocaleString()}`;
                        document.getElementById('kpi-stair-locked').innerText = `$${parseFloat(sData.locked).toLocaleString()}`;
                    }
                } catch(e) {}

                // Draw Chart
                if(data.chart_dates && data.chart_balances) {
                    const ctx = document.getElementById('bankrollChart').getContext('2d');
                    if(bankrollChartInstance) bankrollChartInstance.destroy();
                    
                    let gradient = ctx.createLinearGradient(0, 0, 0, 400);
                    gradient.addColorStop(0, 'rgba(229, 193, 88, 0.4)'); // Gold
                    gradient.addColorStop(1, 'rgba(10, 25, 16, 0)'); // BG

                    bankrollChartInstance = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.chart_dates,
                            datasets: [{
                                label: 'Capital',
                                data: data.chart_balances,
                                borderColor: '#E5C158',
                                backgroundColor: gradient,
                                borderWidth: 3,
                                pointBackgroundColor: '#0A1910',
                                pointBorderColor: '#E5C158',
                                pointBorderWidth: 2,
                                fill: true,
                                tension: 0.4
                            }]
                        },
                        options: {
                            responsive: true,
                            plugins: { legend: { display: false } },
                            scales: {
                                y: { grid: { color: '#1B3B2B' }, ticks: { color: '#8E9B93' } },
                                x: { grid: { display: false }, ticks: { color: '#8E9B93', maxTicksLimit: 7 } }
                            }
                        }
                    });
                }
            } catch(e) {}
        }

        // Fetch Tracker
        async function loadTracker() {
            try {
                const res = await fetch('/api/tracker');
                const data = await res.json();
                const tbody = document.querySelector('#tracker-table tbody');
                
                if(data.financials) {
                    document.getElementById('kpi-tracker-staked').innerText = `$${data.financials.total_staked.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    document.getElementById('kpi-tracker-won').innerText = `$${data.financials.total_won.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    document.getElementById('kpi-tracker-lost').innerText = `$${data.financials.total_lost.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    document.getElementById('kpi-tracker-pending').innerText = `$${data.financials.total_pending.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                }

                if(data.stats) {
                    const ctxDonut = document.getElementById('winLossChart').getContext('2d');
                    if(winLossChartInstance) winLossChartInstance.destroy();
                    winLossChartInstance = new Chart(ctxDonut, {
                        type: 'doughnut',
                        data: {
                            labels: ['Wins', 'Losses', 'Open'],
                            datasets: [{
                                data: [data.stats.W, data.stats.L, data.stats.OPEN],
                                backgroundColor: ['#E5C158', '#1B3B2B', '#C5A03A'],
                                borderWidth: 0,
                                hoverOffset: 4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            cutout: '75%',
                            plugins: {
                                legend: { position: 'bottom', labels: { color: '#F4F6F5', padding: 20 } }
                            }
                        }
                    });
                }

                if(data.bets.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No bets recorded in SQLite yet.</td></tr>';
                    return;
                }
                tbody.innerHTML = data.bets.map(b => {
                    let statusTag = `<span class="tag-open">OPEN</span>`;
                    if(b.result === 'W') statusTag = `<span class="tag-win">WIN</span>`;
                    else if(b.result === 'L') statusTag = `<span class="tag-loss">LOSS</span>`;
                    else if(b.result === 'VOID') statusTag = `<span class="tag-loss" style="background:rgba(255,255,255,0.1); color:#aaa;">VOID</span>`;
                    
                    let pnlColor = 'inherit';
                    let pnlStr = '-';
                    if (b.pnl !== null && b.pnl !== undefined && b.result !== 'OPEN') {
                        if (b.pnl >= 0) {
                            pnlStr = `+$${b.pnl.toFixed(2)}`;
                            pnlColor = '#00ff88';
                        } else {
                            pnlStr = `-$${Math.abs(b.pnl).toFixed(2)}`;
                            pnlColor = '#ff4d4d';
                        }
                    }
                    let edgeStr = `<span style="color: ${b.edge_pct > 0 ? '#00ff88' : 'inherit'}">${b.edge_pct > 0 ? '+' : ''}${b.edge_pct}%</span>`;
                    if (b.edge_pct <= -500.0) {
                        edgeStr = `<span style="color: var(--text-muted); font-size: 0.85rem;">N/A (Unlisted)</span>`;
                    }
                    
                    let timeRemaining = '-';
                    if (b.result === 'OPEN' && b.kickoff) {
                        const now = new Date();
                        const kickoff = new Date(b.kickoff);
                        const diffMs = kickoff - now;
                        if (diffMs > 0) {
                            const diffHrs = Math.floor(diffMs / 3600000);
                            const diffMins = Math.floor((diffMs % 3600000) / 60000);
                            timeRemaining = `<span style="color:var(--primary); font-weight:600;"><i class="fa-solid fa-clock"></i> ${diffHrs}h ${diffMins}m</span>`;
                        } else {
                            timeRemaining = `<span style="color:#00ff88; font-weight:600;"><i class="fa-solid fa-bolt"></i> LIVE / SETTLING</span>`;
                        }
                    } else if (b.result !== 'OPEN') {
                        timeRemaining = `<span style="color:var(--text-muted);">Resolved</span>`;
                    }

                    return `<tr>
                        <td><span style="font-size:0.8rem; padding: 2px 6px; border-radius: 4px; background: ${b.bet_source === 'AI' ? '#00ff8822' : '#ffffff22'}; color: ${b.bet_source === 'AI' ? '#00ff88' : '#fff'};">${b.bet_source || 'AI'}</span></td>
                        <td><strong>${b.player_id}</strong><br><span style="font-size:0.75rem; color:var(--text-muted)">${b.market_type}</span></td>
                        <td>${b.entry_odds}</td>
                        <td>$${(b.stake || 0).toFixed(2)}</td>
                        <td>${edgeStr}</td>
                        <td style="color: ${pnlColor}">${pnlStr}</td>
                        <td>${timeRemaining}</td>
                        <td>${statusTag}</td>
                    </tr>`;
                }).join('');
            } catch(e) {}
        }

        // Fetch Stair AI Bets
        async function loadStairBets() {
            try {
                const res = await fetch('/api/stair_bets');
                const data = await res.json();
                const tbody = document.querySelector('#stair-table-body');
                tbody.innerHTML = data.stair_bets.map(b => {
                    let statusColor = 'var(--text-main)';
                    if(b.status === 'OPEN') statusColor = 'var(--primary)';
                    if(b.status === 'SETTLED' && b.pnl > 0) statusColor = '#00ff88';
                    if(b.status === 'SETTLED' && b.pnl < 0) statusColor = '#ff4d4d';
                    
                    return `
                    <tr>
                        <td>${new Date(b.placed_at).toLocaleString()}</td>
                        <td style="font-weight:600;">${b.match_id}</td>
                        <td>${b.market_type}</td>
                        <td>${b.entry_odds}</td>
                        <td>$${b.stake.toFixed(2)}</td>
                        <td style="color:${statusColor}; font-weight:700;">${b.status}</td>
                        <td style="font-family:monospace;">${b.order_id || 'N/A'}</td>
                        <td style="color:${b.pnl > 0 ? '#00ff88' : (b.pnl < 0 ? '#ff4d4d' : 'var(--text-main)')}; font-weight:700;">
                            ${b.pnl > 0 ? '+' : ''}${b.pnl.toFixed(2)}
                        </td>
                    </tr>`;
                }).join('');
            } catch(e) {
                console.error("Failed to load stair bets", e);
            }
        }

        // Fetch Settings
        async function loadSettings() {
            try {
                const res = await fetch('/api/settings');
                const data = await res.json();
                document.getElementById('set-kelly').value = data.kelly_multiplier || 0.25;
                document.getElementById('set-ev').value = data.min_ev_threshold || 0.05;
                document.getElementById('set-exposure').value = data.max_exposure_pct || 0.05;
                document.getElementById('set-confidence').value = data.min_confidence_pct || 55;
                document.getElementById('set-datasource').value = data.data_source || 'sofascore_free';
                document.getElementById('set-leagues').value = data.target_leagues || 'All';
                document.getElementById('set-refresh').value = data.refresh_interval_sec || 30;
                document.getElementById('set-auto-bet').checked = data.auto_place_bets || false;
                
                document.getElementById('set-home-adv').value = data.home_adv_weight || 1.2;
                document.getElementById('set-fatigue').value = data.fatigue_penalty || 0.8;
                document.getElementById('set-loss').value = data.max_daily_loss_pct || 10.0;
                document.getElementById('set-win').value = data.stop_win_pct || 25.0;
                document.getElementById('set-bookie').value = data.preferred_bookie || 'Pinnacle';
                
                if(data.refresh_interval_sec && data.refresh_interval_sec > 0) {
                    refreshTimer = data.refresh_interval_sec;
                }
            } catch(e) {}
        }

        async function saveSettings() {
            const payload = {
                kelly_multiplier: parseFloat(document.getElementById('set-kelly').value),
                min_ev_threshold: parseFloat(document.getElementById('set-ev').value),
                max_exposure_pct: parseFloat(document.getElementById('set-exposure').value),
                min_confidence_pct: parseInt(document.getElementById('set-confidence').value),
                data_source: document.getElementById('set-datasource').value,
                target_leagues: document.getElementById('set-leagues').value,
                refresh_interval_sec: parseInt(document.getElementById('set-refresh').value),
                auto_place_bets: document.getElementById('set-auto-bet').checked,
                home_adv_weight: parseFloat(document.getElementById('set-home-adv').value),
                fatigue_penalty: parseFloat(document.getElementById('set-fatigue').value),
                max_daily_loss_pct: parseFloat(document.getElementById('set-loss').value),
                stop_win_pct: parseFloat(document.getElementById('set-win').value),
                preferred_bookie: document.getElementById('set-bookie').value,
                platt_scaling: true
            };
            await fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            showToast('Settings Saved Successfully!', 'success');
            refreshTimer = payload.refresh_interval_sec;
        }

        async function triggerPlatt() {
            if(confirm("Initiate Platt Scaler Recalibration? This requires historical data processing.")) {
                await fetch('/api/trigger_recalibration', {method: 'POST'});
                showToast("Platt Scaler triggered in the background.", "success");
            }
        }

        // Initialize and Route
        window.addEventListener('popstate', handleRouting);

        function handleRouting() {
            const path = window.location.pathname;
            const navItems = document.querySelectorAll('.nav-item');
            if (path === '/performance') {
                switchView('performance-view', navItems[3]);
            } else if (path === '/tracker') {
                switchView('tracker-view', navItems[2]);
            } else if (path === '/bankroll') {
                switchView('bankroll-view', navItems[1]);
            } else if (path === '/settings') {
                switchView('settings-view', navItems[6]);
            } else if (path === '/comparison') {
                switchView('comparison-view', navItems[4]);
            } else if (path === '/stair') {
                switchView('stair-view', navItems[5]);
            } else {
                switchView('live-view', navItems[0]);
                connectSSE();
            }
        }

        // Detailed Prediction Modal Handlers
        function openPredictionModal(match) {
            const p = match.prediction;
            const d = p.detailed_prediction;
            if (!d) return;
            
            document.getElementById('modal-league').innerText = match.league;
            document.getElementById('modal-title').innerText = match.match;
            
            // Tab 1: Summary
            document.getElementById('modal-summary-text').innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <strong><i class="fa-solid fa-brain"></i> TACTICAL SUMMARY & EXPECTED MATCH FLOW</strong>
                    <span style="background:rgba(229,193,88,0.15); color:var(--primary); padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.8rem;">CONFIDENCE: ${d.confidence || 7}/10</span>
                </div>
                <div>${d.tactical_summary}</div>
            `;
            
            const val = d.value_analysis;
            document.getElementById('modal-value-table').innerHTML = `
                <tr><td><strong>Best Match Result Pick</strong></td><td><span class="value-badge">${val.best_result}</span></td></tr>
                <tr><td><strong>Best Goals Market Pick</strong></td><td><span class="value-badge">${val.best_goals}</span></td></tr>
                <tr><td><strong>Best Cards Market Pick</strong></td><td><span class="value-badge">${val.best_cards}</span></td></tr>
                <tr><td><strong>Best Corners Market Pick</strong></td><td><span class="value-badge">${val.best_corners}</span></td></tr>
                <tr><td><strong>Best Player Prop Pick</strong></td><td><span class="value-badge">${val.best_player_prop}</span></td></tr>
                <tr><td><strong>Safest Prediction</strong></td><td><span class="value-badge" style="background:rgba(0,255,100,0.12); color:#00ff88;">${val.safest}</span></td></tr>
                <tr><td><strong>Highest-Risk/Highest-Reward</strong></td><td><span class="value-badge" style="background:rgba(255,77,77,0.12); color:#ff4d4d;">${val.high_risk_reward}</span></td></tr>
            `;
            
            // Tab 2: Result & Goals
            document.getElementById('modal-prob-home').innerText = `${d.home_prob}%`;
            document.getElementById('modal-prob-draw').innerText = `${d.draw_prob}%`;
            document.getElementById('modal-prob-away').innerText = `${d.away_prob}%`;
            
            document.getElementById('modal-goals-table').innerHTML = `
                <tr><td>Home Team xG</td><td style="font-weight:700;">${d.home_xg}</td></tr>
                <tr><td>Away Team xG</td><td style="font-weight:700;">${d.away_xg}</td></tr>
                <tr><td>Over 0.5 Goals</td><td>${d.over_05}%</td></tr>
                <tr><td>Over 1.5 Goals</td><td>${d.over_15}%</td></tr>
                <tr><td>Over 2.5 Goals</td><td>${d.over_25}%</td></tr>
                <tr><td>Over 3.5 Goals</td><td>${d.over_35}%</td></tr>
                <tr><td>Under 2.5 Goals</td><td>${d.under_25}%</td></tr>
                <tr><td>Both Teams To Score (BTTS)</td><td>${d.btts_yes}%</td></tr>
            `;
            
            // Tab 3: Player Props
            document.getElementById('modal-goalscorer-table').innerHTML = d.goalscorers.map(pl => `
                <tr>
                    <td><strong>${pl.name}</strong> (${pl.team})</td>
                    <td>${pl.anytime_goal_prob}%</td>
                    <td>${pl.first_goal_prob}%</td>
                    <td style="color:var(--secondary); font-weight:700;">${pl.rating}</td>
                </tr>
            `).join('');
            
            document.getElementById('modal-shots-table').innerHTML = d.shots_players.map(pl => `
                <tr>
                    <td><strong>${pl.name}</strong> (${pl.team})</td>
                    <td>${pl.exp_shots}</td>
                    <td>${pl.exp_sot}</td>
                    <td style="color:var(--secondary); font-weight:700;">${pl.rating}</td>
                </tr>
            `).join('');
            
            // Tab 4: Team Stats & Corners & Cards
            document.getElementById('modal-corners-table').innerHTML = `
                <tr><td>Total Match Corners</td><td style="font-weight:700;">${d.corners_total}</td></tr>
                <tr><td>Home Team Corners</td><td>${d.corners_home}</td></tr>
                <tr><td>Away Team Corners</td><td>${d.corners_away}</td></tr>
                <tr><td>Over 7.5 Corners</td><td>${d.corners_over_75}%</td></tr>
                <tr><td>Over 8.5 Corners</td><td>${d.corners_over_85}%</td></tr>
                <tr><td>Over 9.5 Corners</td><td>${d.corners_over_95}%</td></tr>
                <tr><td>Over 10.5 Corners</td><td>${d.corners_over_105}%</td></tr>
            `;
            
            document.getElementById('modal-cards-table').innerHTML = `
                <tr><td>Home Yellow Cards</td><td>${d.cards_yellow_home}</td></tr>
                <tr><td>Away Yellow Cards</td><td>${d.cards_yellow_away}</td></tr>
                <tr><td>Total Yellow Cards</td><td style="font-weight:700;">${d.cards_yellow_total}</td></tr>
                <tr><td>Total Red Cards</td><td>${d.cards_red_total}</td></tr>
            `;
            
            document.getElementById('modal-cards-table').innerHTML += `
                <tr><td colspan="2" style="font-weight:700; color:var(--primary); padding-top:10px; border-bottom:none;">Key Player Disciplinary Risk:</td></tr>
            ` + d.cards_players.map(pl => `
                <tr>
                    <td>${pl.name} (${pl.team})</td>
                    <td>Yellow: ${pl.yellow_prob}% | Red: ${pl.red_prob}%</td>
                </tr>
            `).join('');
            
            document.getElementById('modal-additional-table').innerHTML = `
                <tr><td>Possession %</td><td style="font-weight:700; color:var(--primary);">${d.possession_home}%</td><td style="font-weight:700; color:var(--secondary);">${d.possession_away}%</td></tr>
                <tr><td>Fouls Committed</td><td>${d.fouls_home}</td><td>${d.fouls_away}</td></tr>
                <tr><td>Offsides</td><td>${d.offsides_home}</td><td>${d.offsides_away}</td></tr>
                <tr><td>Saves</td><td>${d.saves_home}</td><td>${d.saves_away}</td></tr>
                <tr><td>Clean Sheet Probability</td><td>${d.clean_sheet_home}%</td><td>${d.clean_sheet_away}%</td></tr>
            `;
            
            // Switch tabs to default Tab 1
            const defaultTabBtn = document.querySelectorAll('.modal-tab')[0];
            switchModalTab('tab-summary', defaultTabBtn);
            
            document.getElementById('detail-modal').style.display = 'flex';
        }
        
        function closePredictionModal() {
            document.getElementById('detail-modal').style.display = 'none';
        }
        
        function switchModalTab(tabId, btn) {
            document.querySelectorAll('.modal-tab-content').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            
            document.querySelectorAll('.modal-tab').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');
        }

        async function loadComparisonList() {
            const listContainer = document.getElementById('comparison-list');
            listContainer.innerHTML = '<div style="text-align: center; padding: 20px;"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading...</div>';
            
            try {
                const res = await fetch('/api/comparisons');
                if (!res.ok) throw new Error("Failed to load");
                const matches = await res.json();
                
                if (matches.length === 0) {
                    listContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-muted);">No predicted matches available today.</div>';
                    return;
                }
                
                listContainer.innerHTML = '';
                matches.forEach(m => {
                    const btn = document.createElement('div');
                    btn.className = 'comparison-item-btn';
                    btn.style.cssText = `
                        padding: 12px 15px;
                        background: rgba(255,255,255,0.03);
                        border: 1px solid var(--border-color);
                        border-radius: 8px;
                        cursor: pointer;
                        transition: all 0.2s ease;
                        display: flex;
                        flex-direction: column;
                        gap: 5px;
                        margin-bottom: 8px;
                    `;
                    
                    const isKarlstad = m.fixture_id === 15458376;
                    if (isKarlstad) {
                        btn.style.borderColor = 'var(--primary)';
                        btn.style.background = 'rgba(229,193,88,0.04)';
                    }
                    
                    const statusText = m.status_code === 'FT' ? 'Finished' : (m.status_code === 'NS' ? 'Upcoming' : 'Live');
                    const statusColor = m.status_code === 'FT' ? '#00ff88' : (m.status_code === 'NS' ? '#a0a0a0' : '#ffaa00');
                    
                    btn.innerHTML = `
                        <div style="font-size: 0.72rem; color: var(--primary); font-weight: 700; text-transform: uppercase; display: flex; justify-content: space-between;">
                            <span>${m.league}</span>
                            <span style="color: ${statusColor}">${statusText}</span>
                        </div>
                        <div style="font-weight: 700; color: var(--text-main); font-size: 0.88rem; margin: 3px 0;">${m.match}</div>
                        <div style="font-size: 0.72rem; color: var(--text-muted);">Kickoff: ${new Date(m.kickoff).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
                    `;
                    
                    btn.addEventListener('mouseenter', () => {
                        btn.style.background = 'rgba(255,255,255,0.08)';
                    });
                    btn.addEventListener('mouseleave', () => {
                        btn.style.background = isKarlstad ? 'rgba(229,193,88,0.04)' : 'rgba(255,255,255,0.03)';
                    });
                    
                    btn.addEventListener('click', () => {
                        document.querySelectorAll('.comparison-item-btn').forEach(el => {
                            el.style.background = 'rgba(255,255,255,0.03)';
                            el.style.fontWeight = 'normal';
                        });
                        btn.style.background = 'rgba(229,193,88,0.12)';
                        btn.style.fontWeight = 'bold';
                        loadComparisonDetail(m.fixture_id, false);
                    });
                    
                    listContainer.appendChild(btn);
                });
                
                const karlstadMatch = matches.find(m => m.fixture_id === 15458376);
                if (karlstadMatch) {
                    loadComparisonDetail(15458376, false);
                } else if (matches.length > 0) {
                    loadComparisonDetail(matches[0].fixture_id, false);
                }
                
            } catch(e) {
                listContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #ff4d4d;">Error loading matches.</div>';
            }
        }

        async function loadComparisonDetail(fixtureId, isDemo) {
            const detailPanel = document.getElementById('comparison-detail-panel');
            detailPanel.innerHTML = '<div style="text-align: center; padding: 100px 20px;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i> Loading comparison...</div>';
            
            try {
                const url = `/api/comparison/${fixtureId}` + (isDemo ? '?demo=true' : '');
                const res = await fetch(url);
                if (!res.ok) throw new Error("Failed to load");
                const data = await res.json();
                
                const pred = data.prediction;
                const act = data.actuals;
                const dp = pred.detailed_prediction || {};
                
                if (!act) {
                    detailPanel.innerHTML = '<div style="text-align: center; padding: 100px 20px; color: var(--text-muted);">No reality data available for this match yet.</div>';
                    return;
                }
                
                const homeTeam = pred.match.split(' vs ')[0].trim();
                const awayTeam = pred.match.split(' vs ')[1].trim();
                
                const isHomeWin = act.home_score > act.away_score;
                const isAwayWin = act.away_score > act.home_score;
                const isDraw = act.home_score === act.away_score;
                
                const actualWinner = isHomeWin ? `${homeTeam} WIN` : (isAwayWin ? `${awayTeam} WIN` : 'DRAW');
                const predWinner = pred.prediction;
                
                const winnerCorrect = predWinner.trim() === actualWinner.trim();
                
                const checkWin = (type, val) => {
                    if (!val) return false;
                    const val_lower = val.toLowerCase();
                    const totalGoals = act.home_score + act.away_score;
                    
                    if (type === 'best_result') {
                        return val.trim() === actualWinner.trim();
                    }
                    if (type === 'best_goals') {
                        if (val_lower.includes('over 1.5')) return totalGoals > 1.5;
                        if (val_lower.includes('over 2.5')) return totalGoals > 2.5;
                        if (val_lower.includes('under 2.5')) return totalGoals < 2.5;
                    }
                    if (type === 'best_cards') {
                        const totalCards = act.cards_yellow_total;
                        if (val_lower.includes('over 3.5')) return totalCards > 3.5;
                        if (val_lower.includes('under 4.5')) return totalCards < 4.5;
                        if (val_lower.includes('over 4.5')) return totalCards > 4.5;
                    }
                    if (type === 'best_corners') {
                        const totalCorners = act.corners_total;
                        if (val_lower.includes('over 8.5')) return totalCorners > 8.5;
                        if (val_lower.includes('over 9.5')) return totalCorners > 9.5;
                        if (val_lower.includes('under 10.5')) return totalCorners < 10.5;
                    }
                    if (type === 'safest') {
                        if (val_lower.includes('1x') || val_lower.includes('double chance (1x)')) return act.home_score >= act.away_score;
                        if (val_lower.includes('x2') || val_lower.includes('double chance (x2)')) return act.away_score >= act.home_score;
                    }
                    if (type === 'high_risk_reward') {
                        const btts = act.home_score > 0 && act.away_score > 0;
                        const matchWin = val.trim().startsWith(actualWinner.trim());
                        return matchWin && btts;
                    }
                    if (type === 'best_player_prop') {
                        const pl = act.player_stats.find(p => val_lower.includes(p.name.toLowerCase()));
                        if (pl) {
                            if (val_lower.includes('over 1.5 shots')) return pl.shots > 1.5;
                            if (val_lower.includes('over 0.5 shots')) return pl.shots > 0.5;
                        }
                    }
                    return false;
                };

                let demoBtnHTML = '';
                if (fixtureId === 15458376) {
                    demoBtnHTML = `
                        <button onclick="loadComparisonDetail(15458376, ${!isDemo})" class="btn" style="background:${isDemo ? '#ff4d4d' : 'var(--primary)'}; color:var(--bg-color); font-weight:700; border:none; padding:8px 16px; border-radius:6px; cursor:pointer;">
                            ${isDemo ? '<i class="fa-solid fa-satellite-dish"></i> Exit Demo Mode' : '<i class="fa-solid fa-gamepad"></i> Activate Simulated Demo'}
                        </button>
                    `;
                }

                let headerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-color); padding-bottom:15px; margin-bottom:10px;">
                        <div>
                            <span style="background:rgba(229,193,88,0.15); color:var(--primary); padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem; text-transform:uppercase;">${pred.league}</span>
                            <h2 style="color:var(--text-main); margin-top:5px; font-size:1.4rem;">${pred.match}</h2>
                        </div>
                        <div style="display:flex; align-items:center; gap:15px;">
                            ${demoBtnHTML}
                            <span style="font-weight:700; font-size:1.1rem; color:${act.is_simulated ? '#ffaa00' : '#00ff88'}">${act.status}</span>
                        </div>
                    </div>
                `;

                let kpiHTML = `
                    <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:15px;">
                        <div class="kpi-card" style="border-left:4px solid ${winnerCorrect ? '#00ff88' : '#ff4d4d'}; padding:15px; background:rgba(255,255,255,0.01);">
                            <div class="kpi-title">Winner Prediction</div>
                            <div class="kpi-value" style="font-size:1.1rem; margin-top:5px; color:${winnerCorrect ? '#00ff88' : '#ff4d4d'}">
                                ${winnerCorrect ? '<i class="fa-solid fa-circle-check"></i> CORRECT' : '<i class="fa-solid fa-circle-xmark"></i> INCORRECT'}
                            </div>
                            <div style="font-size:0.8rem; color:var(--text-muted); margin-top:5px;">AI: ${predWinner} | Actual: ${actualWinner}</div>
                        </div>
                        <div class="kpi-card" style="border-left:4px solid var(--primary); padding:15px; background:rgba(255,255,255,0.01);">
                            <div class="kpi-title">Final Score</div>
                            <div class="kpi-value" style="font-size:1.4rem; margin-top:5px; color:var(--text-main);">${act.score}</div>
                            <div style="font-size:0.8rem; color:var(--text-muted); margin-top:5px;">AI Expected Score: ${pred.expected_score}</div>
                        </div>
                        <div class="kpi-card" style="border-left:4px solid var(--secondary); padding:15px; background:rgba(255,255,255,0.01);">
                            <div class="kpi-title">AI Engine Edge</div>
                            <div class="kpi-value" style="font-size:1.2rem; margin-top:5px; color:var(--secondary);">Confidence: ${dp.confidence || 7}/10</div>
                            <div style="font-size:0.8rem; color:var(--text-muted); margin-top:5px;">Predicted at kickoff with lineups</div>
                        </div>
                    </div>
                `;

                let valueBetsHTML = '';
                if (dp.value_analysis) {
                    const va = dp.value_analysis;
                    valueBetsHTML = `
                        <div style="background:var(--surface-color); border:1px solid var(--border-color); border-radius:12px; padding:20px; margin-top:10px;">
                            <h3 style="color:var(--primary); margin-bottom:15px; font-size:1.1rem; display:flex; align-items:center; gap:8px;">
                                <i class="fa-solid fa-sack-dollar"></i> AI Value Picks Evaluation
                            </h3>
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>Value Market</th>
                                        <th>AI Pick Recommendation</th>
                                        <th>Actual Reality Result</th>
                                        <th>Bet Outcome</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td><strong>Best Match Result</strong></td>
                                        <td><span class="value-badge">${va.best_result}</span></td>
                                        <td>${actualWinner}</td>
                                        <td>${checkWin('best_result', va.best_result) ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">WIN</span>' : '<span style="background:rgba(255,77,77,0.12); color:#ff4d4d; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">LOSS</span>'}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Best Goals Market</strong></td>
                                        <td><span class="value-badge">${va.best_goals}</span></td>
                                        <td>${act.score} (${act.home_score + act.away_score} Goals)</td>
                                        <td>${checkWin('best_goals', va.best_goals) ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">WIN</span>' : '<span style="background:rgba(255,77,77,0.12); color:#ff4d4d; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">LOSS</span>'}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Best Cards Market</strong></td>
                                        <td><span class="value-badge">${va.best_cards}</span></td>
                                        <td>${act.cards_yellow_total} Cards</td>
                                        <td>${checkWin('best_cards', va.best_cards) ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">WIN</span>' : '<span style="background:rgba(255,77,77,0.12); color:#ff4d4d; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">LOSS</span>'}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Best Corners Market</strong></td>
                                        <td><span class="value-badge">${va.best_corners}</span></td>
                                        <td>${act.corners_total} Corners</td>
                                        <td>${checkWin('best_corners', va.best_corners) ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">WIN</span>' : '<span style="background:rgba(255,77,77,0.12); color:#ff4d4d; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">LOSS</span>'}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Safest Recommendation</strong></td>
                                        <td><span class="value-badge" style="background:rgba(0,255,100,0.1); color:#00ff88;">${va.safest}</span></td>
                                        <td>${act.score}</td>
                                        <td>${checkWin('safest', va.safest) ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">WIN</span>' : '<span style="background:rgba(255,77,77,0.12); color:#ff4d4d; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">LOSS</span>'}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Highest Risk/Reward</strong></td>
                                        <td><span class="value-badge" style="background:rgba(255,77,77,0.1); color:#ff4d4d;">${va.high_risk_reward}</span></td>
                                        <td>Winner: ${actualWinner} & BTTS: ${act.home_score > 0 && act.away_score > 0 ? 'Yes' : 'No'}</td>
                                        <td>${checkWin('high_risk_reward', va.high_risk_reward) ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">WIN</span>' : '<span style="background:rgba(255,77,77,0.12); color:#ff4d4d; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">LOSS</span>'}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    `;
                }

                let statsTableHTML = `
                    <div style="background:var(--surface-color); border:1px solid var(--border-color); border-radius:12px; padding:20px; margin-top:10px;">
                        <h3 style="color:var(--primary); margin-bottom:15px; font-size:1.1rem; display:flex; align-items:center; gap:8px;">
                            <i class="fa-solid fa-chart-simple"></i> Core Team Match Stats: Predicted vs Actual
                        </h3>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Match Statistic</th>
                                    <th>AI Expected Prediction</th>
                                    <th>Actual Reality Outcome</th>
                                    <th>Difference / Match</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><strong>Possession % (Home/Away)</strong></td>
                                    <td>${dp.possession_home}% / ${dp.possession_away}%</td>
                                    <td>${act.possession_home}% / ${act.possession_away}%</td>
                                    <td>${Math.abs(dp.possession_home - act.possession_home)}% Diff</td>
                                </tr>
                                <tr>
                                    <td><strong>Total Match Corners</strong></td>
                                    <td>${dp.corners_total} (H: ${dp.corners_home} | A: ${dp.corners_away})</td>
                                    <td>${act.corners_total} (H: ${act.corners_home} | A: ${act.corners_away})</td>
                                    <td>${act.corners_total >= dp.corners_total ? '+' : ''}${act.corners_total - dp.corners_total} Corners</td>
                                </tr>
                                <tr>
                                    <td><strong>Fouls Committed</strong></td>
                                    <td>Home: ${dp.fouls_home} | Away: ${dp.fouls_away}</td>
                                    <td>Home: ${act.fouls_home} | Away: ${act.fouls_away}</td>
                                    <td>H: ${act.fouls_home - dp.fouls_home} | A: ${act.fouls_away - dp.fouls_away}</td>
                                </tr>
                                <tr>
                                    <td><strong>Yellow Cards (Home/Away)</strong></td>
                                    <td>H: ${dp.cards_yellow_home} | A: ${dp.cards_yellow_away}</td>
                                    <td>H: ${act.cards_yellow_home} | A: ${act.cards_yellow_away}</td>
                                    <td>Total: ${act.cards_yellow_total} vs Predicted: ${dp.cards_yellow_total}</td>
                                </tr>
                                <tr>
                                    <td><strong>Expected Goals (xG) vs Goals</strong></td>
                                    <td>H xG: ${dp.home_xg} | A xG: ${dp.away_xg}</td>
                                    <td>H Goals: ${act.home_score} | A Goals: ${act.away_score}</td>
                                    <td>H: ${act.home_score - dp.home_xg > 0 ? '+' : ''}${(act.home_score - dp.home_xg).toFixed(1)} | A: ${act.away_score - dp.away_xg > 0 ? '+' : ''}${(act.away_score - dp.away_xg).toFixed(1)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                `;

                let actualGoalsListHTML = '';
                if (act.goals && act.goals.length > 0) {
                    actualGoalsListHTML = act.goals.map(g => `
                        <div style="background:rgba(255,255,255,0.02); border:1px solid var(--border-color); border-radius:8px; padding:10px 15px; display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <i class="fa-solid fa-soccer-ball" style="color:#00ff88;"></i>
                                <span><strong>${g.player}</strong> (${g.team})</span>
                            </div>
                            <div style="color:var(--primary); font-weight:700; font-size:0.9rem;">${g.minute}'</div>
                        </div>
                    `).join('');
                } else {
                    actualGoalsListHTML = '<div style="color:var(--text-muted); font-size:0.9rem; text-align:center; padding:10px;">No goals scored in this match.</div>';
                }

                let playerGoalsHTML = `
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-top:10px;">
                        <div style="background:var(--surface-color); border:1px solid var(--border-color); border-radius:12px; padding:20px;">
                            <h3 style="color:var(--primary); margin-bottom:15px; font-size:1.1rem; display:flex; align-items:center; gap:8px;">
                                <i class="fa-solid fa-clock-rotate-left"></i> Real Match Goal Events
                            </h3>
                            <div style="display:flex; flex-direction:column; gap:5px;">
                                ${actualGoalsListHTML}
                            </div>
                        </div>
                        
                        <div style="background:var(--surface-color); border:1px solid var(--border-color); border-radius:12px; padding:20px;">
                            <h3 style="color:var(--primary); margin-bottom:15px; font-size:1.1rem; display:flex; align-items:center; gap:8px;">
                                <i class="fa-solid fa-bullseye"></i> AI Goalscorer Probabilities
                            </h3>
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>Player (Team)</th>
                                        <th>Anytime Prob</th>
                                        <th>Scored?</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${dp.goalscorers ? dp.goalscorers.slice(0, 4).map(pl => {
                                        const scored = act.goals ? act.goals.some(g => g.player.toLowerCase().includes(pl.name.toLowerCase()) || pl.name.toLowerCase().includes(g.player.toLowerCase())) : false;
                                        return `
                                            <tr>
                                                <td><strong>${pl.name}</strong> (${pl.team})</td>
                                                <td>${pl.anytime_goal_prob}%</td>
                                                <td>${scored ? '<span style="background:rgba(0,255,100,0.12); color:#00ff88; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;">YES</span>' : '<span style="color:var(--text-muted);">NO</span>'}</td>
                                            </tr>
                                        `;
                                    }).join('') : '<tr><td colspan="3">No goalscorer props predicted.</td></tr>'}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;

                let tacticalHTML = `
                    <div style="background:rgba(229,193,88,0.05); border:1px dashed var(--primary); border-radius:12px; padding:20px; margin-top:10px;">
                        <h4 style="color:var(--primary); margin-bottom:10px; font-size:1rem; display:flex; align-items:center; gap:8px;">
                            <i class="fa-solid fa-brain"></i> AI Pre-Match Tactical Summary
                        </h4>
                        <div style="font-size:0.9rem; line-height:1.5; color:var(--text-main); font-style:italic;">"${dp.tactical_summary}"</div>
                    </div>
                `;

                detailPanel.innerHTML = `
                    ${headerHTML}
                    ${kpiHTML}
                    ${tacticalHTML}
                    ${valueBetsHTML}
                    ${statsTableHTML}
                    ${playerGoalsHTML}
                `;

            } catch (e) {
                console.error(e);
                detailPanel.innerHTML = `<div style="text-align: center; padding: 100px 20px; color:#ff4d4d;"><i class="fa-solid fa-circle-xmark"></i> Failed to load match comparison. ${e.message}</div>`;
            }
        }

        handleRouting();
        loadSettings();
    